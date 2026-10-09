#!/usr/bin/env python3
"""
Teste de conectividade através do túnel IPSec.
Executar a partir de um host da LAN do Fortigate (192.168.10.0/24).

Uso:
  python test_tunnel.py --remote-host 192.168.20.10 --tcp-port 443
Exit codes: 0 OK | 1 degradado | 2 túnel down
"""
import argparse, platform, re, socket, subprocess, sys


def ping(host, count=4):
    flag = "-n" if platform.system().lower() == "windows" else "-c"
    out = subprocess.run(["ping", flag, str(count), host], capture_output=True, text=True, timeout=count * 3 + 10)
    m = re.search(r"(\d+(?:\.\d+)?)% (?:packet )?loss", out.stdout)
    loss = float(m.group(1)) if m else (0.0 if out.returncode == 0 else 100.0)
    return out.returncode == 0, loss


def tcp(host, port, timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, 0.0
    except OSError:
        return False, 100.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tunnel-peer", default="169.255.1.2", help="IP do túnel do peer")
    ap.add_argument("--remote-host", required=True, help="host na LAN remota (192.168.20.x)")
    ap.add_argument("--tcp-port", type=int)
    ap.add_argument("--max-loss", type=float, default=10.0)
    a = ap.parse_args()

    results = {
        "ping_tunnel_peer": ping(a.tunnel_peer),
        "ping_remote_host": ping(a.remote_host),
    }
    if a.tcp_port:
        results["tcp_remote_host"] = tcp(a.remote_host, a.tcp_port)

    for name, (ok, loss) in results.items():
        print(f"{'OK  ' if ok else 'FAIL'} {name} (perda: {loss}%)")

    if not results["ping_remote_host"][0]:
        print("ALERTA: sem conectividade pelo túnel", file=sys.stderr)
        return 2
    if any(not ok or loss > a.max_loss for ok, loss in results.values()):
        print("ALERTA: túnel degradado", file=sys.stderr)
        return 1
    print("Túnel operacional.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
