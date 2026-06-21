from pathlib import Path
from forsch.adk_components.tools.landmine_audit import propose_landmine_fixes, apply_landmine_fix


def test_propose_wraps_bare_env_default(tmp_path):
    f = tmp_path / "m.py"
    f.write_text('FUNNEL = "https://x.tail818cf8.ts.net:10000"\n')
    finding = {"file": str(f), "line": 1, "rule": "hardcoded-tailnet",
               "snippet": 'FUNNEL = "https://x.tail818cf8.ts.net:10000"'}
    props = propose_landmine_fixes([finding])
    assert props and props[0]["auto"] is True
    assert "__FUNNEL_BASE__" in props[0]["new_content"]
    assert props[0]["diff"].startswith("---")


def test_apply_writes_with_backup_and_dryrun(tmp_path):
    f = tmp_path / "m.py"
    f.write_text('OLD = 1\n')
    res = apply_landmine_fix(str(f), "NEW = 2\n", dry_run=True)
    assert res["applied"] is False and f.read_text() == "OLD = 1\n"
    res = apply_landmine_fix(str(f), "NEW = 2\n", dry_run=False)
    assert res["applied"] is True and f.read_text() == "NEW = 2\n"
    assert Path(res["backup"]).read_text() == "OLD = 1\n"
