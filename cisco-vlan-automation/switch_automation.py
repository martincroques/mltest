"""
Backend de automação para switches Cisco IOS.

Funcionalidades:
  - Configuração de VLANs e hostname via Netmiko (SSH ou Telnet)
  - Salvar configuração na NVRAM (write memory)
  - Backup da running-config em arquivo local (hostname + data/hora no nome)
  - Validação pós-configuração (VLANs e hostname) com alertas de divergência

As funções de parsing/validação são puras (não dependem de rede) e possuem testes
unitários em tests/test_validation.py.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

BACKUP_DIR = Path(__file__).parent / "backups"
DEFAULT_VLANS = {1, 1002, 1003, 1004, 1005}  # VLANs padrão do IOS (não geram alerta)


@dataclass
class Vlan:
    id: int
    name: str


@dataclass
class ValidationReport:
    checks: list = field(default_factory=list)    # (ok: bool, mensagem: str)
    warnings: list = field(default_factory=list)  # configurações fora do padrão

    @property
    def ok(self):
        return all(c[0] for c in self.checks) and not self.warnings


@dataclass
class AutomationResult:
    success: bool = False
    error: str = ""
    log: list = field(default_factory=list)
    commands: list = field(default_factory=list)
    backups: list = field(default_factory=list)
    report: ValidationReport = None
    dry_run: bool = False


# --------------------------------------------------------------------------- #
# Funções puras: entrada, geração de comandos, parsing e validação
# --------------------------------------------------------------------------- #
def sanitize_vlan_name(name: str) -> str:
    """O IOS só aceita ASCII em nomes de VLAN: remove acentos/cedilha, troca espaços por _ ."""
    name = unicodedata.normalize("NFKD", name.strip())
    name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^A-Za-z0-9_\-]", "", name)
    return name[:32]


def validate_inputs(vlans, hostname):
    """Retorna lista de erros de entrada (vazia se tudo OK)."""
    errors = []
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_\-]{0,62}", hostname or ""):
        errors.append("Hostname inválido: use letras, números, '_' ou '-', começando por letra.")
    if not vlans:
        errors.append("Informe ao menos uma VLAN.")
    seen = set()
    for v in vlans:
        if not 2 <= v.id <= 4094 or v.id in DEFAULT_VLANS:
            errors.append(f"VLAN {v.id}: ID inválido ou reservado (use 2-4094, exceto 1002-1005).")
        if v.id in seen:
            errors.append(f"VLAN {v.id} informada mais de uma vez.")
        seen.add(v.id)
        if not v.name:
            errors.append(f"VLAN {v.id}: nome vazio.")
    return errors


def build_vlan_commands(vlans):
    cmds = []
    for v in vlans:
        cmds += [f"vlan {v.id}", f"name {v.name}"]
    return cmds


def parse_show_vlan_brief(output: str) -> dict:
    """Converte 'show vlan brief' em {id: nome}. Linhas de continuação (portas) são ignoradas."""
    vlans = {}
    for line in output.splitlines():
        m = re.match(r"^(\d{1,4})\s+(\S+)\s+\S+", line)
        if m:
            vlans[int(m.group(1))] = m.group(2)
    return vlans


def parse_hostname(running_config: str):
    m = re.search(r"^hostname\s+(\S+)", running_config, re.MULTILINE)
    return m.group(1) if m else None


def validate_config(expected_vlans, expected_hostname, actual_vlans: dict, actual_hostname) -> ValidationReport:
    """Compara configuração desejada x atual do switch."""
    rep = ValidationReport()

    if actual_hostname == expected_hostname:
        rep.checks.append((True, f"Hostname correto: {actual_hostname}"))
    else:
        rep.checks.append((False, f"Hostname divergente: esperado '{expected_hostname}', encontrado '{actual_hostname}'"))

    for v in expected_vlans:
        actual = actual_vlans.get(v.id)
        if actual is None:
            rep.checks.append((False, f"VLAN {v.id} ausente no switch (esperado nome '{v.name}')"))
        elif actual != v.name:
            rep.checks.append((False, f"VLAN {v.id} com nome divergente: esperado '{v.name}', encontrado '{actual}'"))
        else:
            rep.checks.append((True, f"VLAN {v.id} correta: {actual}"))

    expected_ids = {v.id for v in expected_vlans}
    for vid, name in sorted(actual_vlans.items()):
        if vid not in expected_ids and vid not in DEFAULT_VLANS:
            rep.warnings.append(f"ALERTA: VLAN {vid} ('{name}') existe no switch mas não faz parte da configuração desejada")
    return rep


# --------------------------------------------------------------------------- #
# Funções que interagem com o equipamento (Netmiko)
# --------------------------------------------------------------------------- #
def _connect(conn: dict):
    from netmiko import ConnectHandler  # import tardio: permite testar o resto sem Netmiko
    device_type = "cisco_ios_telnet" if conn.get("protocol") == "telnet" else "cisco_ios"
    params = {
        "device_type": device_type,
        "host": conn["host"],
        "port": int(conn.get("port") or (23 if device_type.endswith("telnet") else 22)),
        "username": conn["username"],
        "password": conn["password"],
        "secret": conn.get("secret", ""),
        "timeout": 20,
    }
    nc = ConnectHandler(**params)
    if params["secret"]:
        nc.enable()
    return nc


def backup_config(nc, tag: str) -> str:
    """Salva a running-config em backups/<hostname>_<tag>_<AAAAMMDD-HHMMSS>.cfg"""
    BACKUP_DIR.mkdir(exist_ok=True)
    hostname = nc.base_prompt
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = BACKUP_DIR / f"{hostname}_{tag}_{ts}.cfg"
    path.write_text(nc.send_command("show running-config"), encoding="utf-8")
    return str(path)


def run_automation(conn: dict, hostname: str, vlans: list, dry_run: bool = False) -> AutomationResult:
    res = AutomationResult(dry_run=dry_run)
    log = res.log.append

    errors = validate_inputs(vlans, hostname)
    if errors:
        res.error = " | ".join(errors)
        return res

    res.commands = build_vlan_commands(vlans) + [f"hostname {hostname}"]

    if dry_run:
        log("Modo simulação: nenhum comando foi enviado ao switch.")
        log("Comandos que seriam aplicados:\n  " + "\n  ".join(res.commands))
        res.success = True
        return res

    try:
        # 1) Conexão, backup prévio, VLANs e hostname
        log(f"Conectando a {conn['host']} via {conn.get('protocol', 'ssh').upper()}...")
        with _connect(conn) as nc:
            log(f"Conectado. Prompt atual: {nc.base_prompt}")
            res.backups.append(backup_config(nc, "antes"))
            log(f"Backup prévio salvo: {res.backups[-1]}")

            log("Aplicando VLANs...")
            nc.send_config_set(build_vlan_commands(vlans))

            log(f"Alterando hostname para {hostname}...")
            nc.config_mode()
            nc.send_command_timing(f"hostname {hostname}")  # o prompt muda aqui, por isso 'timing'
            nc.send_command_timing("end")

        # 2) Nova sessão (prompt atualizado): salvar, backup e validar
        with _connect(conn) as nc:
            log("Salvando configuração na NVRAM (write memory)...")
            log(nc.save_config().strip())

            res.backups.append(backup_config(nc, "depois"))
            log(f"Backup pós-configuração salvo: {res.backups[-1]}")

            log("Validando configuração...")
            actual_vlans = parse_show_vlan_brief(nc.send_command("show vlan brief"))
            actual_host = parse_hostname(nc.send_command("show running-config | include ^hostname"))
            res.report = validate_config(vlans, hostname, actual_vlans, actual_host)

        res.success = res.report.ok
        log("Validação concluída: configuração conforme o esperado." if res.success
            else "Validação concluída: DIVERGÊNCIAS ENCONTRADAS (veja os alertas).")

    except Exception as exc:  # autenticação, timeout, comando rejeitado, etc.
        res.error = f"{type(exc).__name__}: {exc}"
    return res
