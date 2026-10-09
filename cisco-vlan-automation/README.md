# Automação de Switch Cisco com Frontend (Python + Flask + Netmiko)

Projeto que automatiza a configuração de **VLANs** e **hostname** em um switch Cisco IOS a partir de uma
interface web, incluindo **salvamento na NVRAM**, **backup da configuração** e **validação** do resultado
com alertas de divergência.

## Funcionalidades

| Requisito | Implementação |
|---|---|
| Frontend de VLANs | Interface web Flask (`app.py` + `templates/index.html`), VLANs 10/20/50 pré-preenchidas e editáveis, com botão para adicionar mais |
| Configuração de VLANs | `build_vlan_commands()` + Netmiko `send_config_set()` |
| Hostname | Campo no frontend (padrão `SWITCH_AUTOMATIZADO`) |
| Salvar configuração | `save_config()` do Netmiko (`write memory`) |
| Backup | `backup_config()` salva `backups/<hostname>_<antes\|depois>_<AAAAMMDD-HHMMSS>.cfg` |
| Validação | Compara `show vlan brief` e `show running-config \| include ^hostname` com o desejado; exibe ✔/✘ e alertas para VLANs fora do padrão |
| Testes | `tests/test_validation.py` (parsing e validação, sem necessidade de switch) |

## Estrutura

```
.
├── app.py                  # Frontend Flask
├── switch_automation.py    # Backend: conexão, configuração, backup e validação
├── templates/index.html    # Interface web
├── tests/test_validation.py
├── backups/                # Backups gerados (evidência)
├── docs/                   # Capturas de tela (evidências)
└── requirements.txt
```

## Instalação e execução

Pré-requisitos: Python 3.9+ e acesso SSH (ou Telnet em laboratório) ao switch.

```bash
git clone <URL_DO_REPOSITORIO>
cd <pasta>
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abra **http://127.0.0.1:5000** no navegador.

### Preparando o switch (laboratório)

```
hostname SW1
ip domain-name lab.local
crypto key generate rsa modulus 2048
ip ssh version 2
username admin privilege 15 secret Admin@123
enable secret Enable@123
interface vlan 1
 ip address 192.168.1.10 255.255.255.0
 no shutdown
line vty 0 4
 login local
 transport input ssh
```

Ambientes de teste: GNS3 / EVE-NG / Cisco CML com imagem IOSvL2, ou Cisco DevNet Sandbox.

## Como usar o frontend

1. Informe IP, protocolo (SSH/Telnet), usuário, senha e, se houver, o enable secret.
2. Confirme o hostname e as VLANs (padrão: 10 `VLAN_DADOS`, 20 `VLAN_VOZ`, 50 `VLAN_SEGURANCA`). Use **+ Adicionar VLAN** para incluir outras.
3. Clique em **Aplicar configuração**. (Marque *Modo simulação* para ver apenas os comandos que seriam enviados.)
4. A tela mostra o log, os backups gerados e o resultado da validação.

## Fluxo de execução

1. Conecta ao switch e gera **backup prévio** (`*_antes_*.cfg`)
2. Aplica as VLANs e altera o hostname
3. Reconecta (o prompt mudou), executa `write memory`
4. Gera **backup pós-configuração** (`*_depois_*.cfg`)
5. **Valida**: hostname e cada VLAN (ID + nome). VLANs existentes que não fazem parte do desejado (exceto 1 e 1002-1005) geram alerta

## Testes

```bash
pytest -v
```

## Notas de implementação

- **Nome "VLAN_SEGURANÇA"**: o IOS não aceita caracteres não ASCII em nomes de VLAN. O sistema converte automaticamente para `VLAN_SEGURANCA` e avisa na tela.
- A senha é usada apenas em memória durante a execução e não é gravada em disco ou log.
- Telnet é oferecido apenas para laboratório (ex.: Packet Tracer/GNS3); em produção use SSH.
- Backups podem conter dados sensíveis (hashes de senha); em produção, não os versione em repositório público.

## Evidências

> Adicione aqui as capturas de tela (pasta `docs/`):
>
> - `docs/frontend.png` – formulário do frontend
> - `docs/resultado.png` – resultado e validação no frontend
> - `docs/cli_show_vlan.png` – `show vlan brief` no switch
> - `docs/cli_hostname.png` – prompt/`show running-config | include hostname`
> - `docs/validacao_alerta.png` – alerta de divergência (ex.: VLAN 99 criada manualmente)
>
> Backups de exemplo: pasta `backups/`.
