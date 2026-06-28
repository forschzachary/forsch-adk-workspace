from forsch.adk_components.tools.landmine_rules import RULES, rule_hits


def test_dead_fleet_path_is_high():
    hits = rule_hits('authsome_bin = "/opt/data/home/.local/bin/authsome"')
    assert [h["id"] for h in hits] == ["dead-fleet-path"]
    assert hits[0]["severity"] == "high"


def test_tailnet_host_flagged():
    hits = rule_hits('FUNNEL = "https://hubert-cloud-sp6.tail818cf8.ts.net:10000"')
    assert any(h["id"] == "hardcoded-tailnet" for h in hits)


def test_clean_line_has_no_dead_path():
    assert all(h["id"] != "dead-fleet-path" for h in rule_hits('x = "/tmp/fine"'))


def test_every_rule_has_required_keys():
    for r in RULES:
        assert {"id", "severity", "pattern", "remedy"} <= set(r)
        assert r["severity"] in {"high", "medium", "low"}
