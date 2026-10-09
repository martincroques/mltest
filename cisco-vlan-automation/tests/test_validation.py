import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from switch_automation import (Vlan, build_vlan_commands, parse_hostname, parse_show_vlan_brief,
                               sanitize_vlan_name, validate_config, validate_inputs)

SHOW_VLAN = """
VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active    Gi0/1, Gi0/2
                                                Gi0/3
10   VLAN_DADOS                       active
20   VLAN_VOZ                         active
50   VLAN_SEGURANCA                   active
99   TESTE                            active
1002 fddi-default                     act/unsup
"""
EXPECTED = [Vlan(10, "VLAN_DADOS"), Vlan(20, "VLAN_VOZ"), Vlan(50, "VLAN_SEGURANCA")]


def test_sanitize_remove_acentos():
    assert sanitize_vlan_name("VLAN_SEGURANÇA") == "VLAN_SEGURANCA"
    assert sanitize_vlan_name("Minha Vlan") == "Minha_Vlan"


def test_parse_show_vlan():
    v = parse_show_vlan_brief(SHOW_VLAN)
    assert v[10] == "VLAN_DADOS" and v[50] == "VLAN_SEGURANCA" and 1 in v


def test_parse_hostname():
    assert parse_hostname("hostname SWITCH_AUTOMATIZADO\n") == "SWITCH_AUTOMATIZADO"


def test_commands():
    assert build_vlan_commands(EXPECTED[:1]) == ["vlan 10", "name VLAN_DADOS"]


def test_validacao_ok():
    actual = {k: v for k, v in parse_show_vlan_brief(SHOW_VLAN).items() if k != 99}
    assert validate_config(EXPECTED, "SW", actual, "SW").ok


def test_validacao_diverge():
    rep = validate_config(EXPECTED, "SW", parse_show_vlan_brief(SHOW_VLAN), "OUTRO")
    assert not rep.ok
    assert any("Hostname divergente" in m for ok, m in rep.checks if not ok)
    assert any("VLAN 99" in w for w in rep.warnings)


def test_validacao_vlan_ausente_e_nome_errado():
    rep = validate_config(EXPECTED, "SW", {10: "ERRADO"}, "SW")
    msgs = [m for ok, m in rep.checks if not ok]
    assert any("VLAN 10 com nome divergente" in m for m in msgs)
    assert any("VLAN 20 ausente" in m for m in msgs)


def test_inputs_invalidos():
    assert validate_inputs([Vlan(1, "x")], "ok")
    assert validate_inputs(EXPECTED, "host name!")
    assert not validate_inputs(EXPECTED, "SWITCH_AUTOMATIZADO")
