"""Frontend web (Flask) para configurar VLANs e hostname em um switch Cisco."""
from flask import Flask, render_template, request

from switch_automation import Vlan, run_automation, sanitize_vlan_name

app = Flask(__name__)

DEFAULT_FORM = {
    "host": "",
    "port": "",
    "protocol": "ssh",
    "username": "",
    "secret": "",
    "hostname": "SWITCH_AUTOMATIZADO",
    "vlans": [(10, "VLAN_DADOS"), (20, "VLAN_VOZ"), (50, "VLAN_SEGURANCA")],
}


@app.route("/", methods=["GET", "POST"])
def index():
    form, result, notes = dict(DEFAULT_FORM), None, []

    if request.method == "POST":
        f = request.form
        ids, names = f.getlist("vlan_id"), f.getlist("vlan_name")
        vlans, form_vlans = [], []
        for vid, vname in zip(ids, names):
            if not vid.strip() and not vname.strip():
                continue
                
            clean = sanitize_vlan_name(vname)
            if clean != vname.strip():
                notes.append(f"Nome '{vname}' ajustado para '{clean}' (o IOS aceita apenas ASCII).")
            form_vlans.append((vid, clean))
            try:
                vlans.append(Vlan(int(vid), clean))
            except ValueError:
                notes.append(f"ID de VLAN inválido: '{vid}'")

        form.update(host=f.get("host", "").strip(),
                    port=f.get("port", ""),
                    protocol=f.get("protocol", "ssh"),
                    username=f.get("username", ""),
                    secret=f.get("secret", ""),
                    hostname=f.get("hostname", "").strip(),
                    vlans=form_vlans or DEFAULT_FORM["vlans"])

        if len(vlans) == len(form_vlans):
            conn = {"host": form["host"],
                    "port": form["port"],
                    "protocol": form["protocol"],
                    "username": form["username"],
                    "password": f.get("password", ""),
                    "secret": form["secret"]}
            result = run_automation(conn, form["hostname"], vlans, dry_run=bool(f.get("dry_run")))

    return render_template("index.html", form=form, result=result, notes=notes)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
