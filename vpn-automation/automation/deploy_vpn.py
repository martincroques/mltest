#!/usr/bin/env python3
"""
Automação CONCEITUAL da VPN IPSec Fortigate <-> Palo Alto.
Não testado contra equipamentos reais: validar em laboratório.

Segredos via variáveis de ambiente:
  VPN_PSK, FGT_API_TOKEN, PAN_USER, PAN_PASS, ALERT_WEBHOOK (opcional)

Uso:
  python deploy_vpn.py --dry-run
  python deploy_vpn.py
Exit codes: 0 OK | 1 divergência | 2 falha de aplicação | 3 erro de execução
"""
import argparse, ipaddress, json, os, sys
from pathlib import Path

import requests
from netmiko import ConnectHandler

BASE = Path(__file__).resolve().parent
VPN_DIR = BASE.parent


def load_params():
    p = json.loads((BASE / "vpn_params.json").read_text())
    hosts = list(ipaddress.ip_network(p["tunnel_network"]).hosts())
    assert len(hosts) == 2, "rede de túnel deve ser /30"
    assert {ipaddress.ip_address(p["fortigate"]["tunnel_ip"]),
            ipaddress.ip_address(p["paloalto"]["tunnel_ip"])} == set(hosts), "IPs de túnel fora do /30"
    a = ipaddress.ip_network(p["fortigate"]["lan_subnet"])
    b = ipaddress.ip_network(p["paloalto"]["lan_subnet"])
    assert not a.overlaps(b), "LANs com overlap"
    return p


def net_mask(cidr):
    n = ipaddress.ip_network(cidr)
    return f"{n.network_address} {n.netmask}"


class Fortigate:
    """Fortigate via REST API (token)."""

    def __init__(self, url, token):
        self.url = url.rstrip("/") + "/api/v2"
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {token}"
        self.s.verify = False  # em produção: usar CA válida

    def upsert(self, path, name, body):
        """Idempotente: PUT se existe, POST se não existe."""
        r = self.s.get(f"{self.url}/cfg/{path}/{name}")
        if r.status_code == 200:
            r = self.s.put(f"{self.url}/cfg/{path}/{name}", json=body)
        else:
            r = self.s.post(f"{self.url}/cfg/{path}", json=body)
        r.raise_for_status()

    def apply(self, p, psk):
        f, pa = p["fortigate"], p["paloalto"]
        self.upsert("vpn.ipsec/phase1-interface", f["phase1_name"], {
            "name": f["phase1_name"], "interface": f["wan_interface"],
            "ike-version": "2", "proposal": "aes256-sha256",
            "dhgrp": str(p["ike"]["dh_group"]), "remote-gw": pa["wan_ip"],
            "psksecret": psk, "keylife": p["ike"]["lifetime_s"],
            "dpd": "on-idle", "dpd-retryinterval": "10"})
        self.upsert("vpn.ipsec/phase2-interface", f["phase2_name"], {
            "name": f["phase2_name"], "phase1name": f["phase1_name"],
            "proposal": "aes256-sha256", "pfs": "enable",
            "dhgrp": str(p["ipsec"]["pfs_group"]),
            "keylifeseconds": p["ipsec"]["lifetime_s"],
            "src-addr-type": "subnet", "dst-addr-type": "subnet",
            "src-subnet": net_mask(f["lan_subnet"]),
            "dst-subnet": net_mask(pa["lan_subnet"])})
        # Objetos de endereço, IP do túnel, rota e políticas: mesmo padrão
        # (campos em vpn/fortigate/ipsec_vpn.conf).

    def tunnel_up(self, name):
        r = self.s.get(f"{self.url}/monitor/vpn/ipsec")
        r.raise_for_status()
        for t in r.json().get("results", []):
            if t.get("name") == name:
                return any(sa.get("status") == "up" for sa in t.get("proxyid", []))
        return False


def apply_paloalto(p, psk, dry_run):
    """Palo Alto via SSH: envia os comandos 'set' e faz commit."""
    lines = (VPN_DIR / "paloalto" / "ipsec_vpn.set").read_text().splitlines()
    commands = [l.strip().replace("${PSK}", psk) for l in lines if l.strip() and not l.startswith("#")]
    if dry_run:
        print(f"[dry-run] {len(commands)} comandos PAN-OS seriam aplicados")
        return
    dev = ConnectHandler(device_type="paloalto_panos", host=p["paloalto"]["host"],
                         username=os.environ["PAN_USER"], password=os.environ["PAN_PASS"])
    try:
        dev.send_config_set(commands)
        dev.commit()
    finally:
        dev.disconnect()


def alert(msg, severity="critical"):
    """Alerta no stderr e, se configurado, em webhook (Slack/Teams)."""
    print(f"[ALERTA:{severity}] {msg}", file=sys.stderr)
    url = os.environ.get("ALERT_WEBHOOK")
    if url:
        requests.post(url, json={"text": f"[{severity}] VPN IPSec: {msg}"}, timeout=10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        p = load_params()
        if args.dry_run:
            print("Parâmetros válidos. Nenhuma alteração aplicada.")
            apply_paloalto(p, "***", True)
            return 0
        psk = os.environ["VPN_PSK"]
        # TODO: backup prévio dos dois equipamentos (rollback)
        fgt = Fortigate(p["fortigate"]["mgmt_url"], os.environ["FGT_API_TOKEN"])
        fgt.apply(p, psk)
        apply_paloalto(p, psk, False)
        if not fgt.tunnel_up(p["fortigate"]["phase1_name"]):
            alert("Túnel não subiu após o deploy (Fortigate)")
            return 2
        print("Deploy concluído e túnel UP.")
        return 0
    except Exception as e:
        alert(f"Erro de execução: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
