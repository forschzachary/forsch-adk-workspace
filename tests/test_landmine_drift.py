import textwrap
from pathlib import Path
from forsch.adk_components.tools.landmine_audit import check_env_contract


def test_env_contract_flags_dead_default(tmp_path, monkeypatch):
    (tmp_path / "m.py").write_text(textwrap.dedent('''
        import os
        a = os.environ.get("FORSCH_ADK_WORKSPACE", "/opt/data/workspace/adk")
        b = os.environ.get("LITELLM_BASE", "http://127.0.0.1:4000")
    '''))
    monkeypatch.setenv("LITELLM_BASE", "http://127.0.0.1:4000")
    monkeypatch.delenv("FORSCH_ADK_WORKSPACE", raising=False)
    rows = {r["var"]: r for r in check_env_contract(str(tmp_path))}
    assert rows["FORSCH_ADK_WORKSPACE"]["set"] is False
    assert rows["FORSCH_ADK_WORKSPACE"]["default_looks_dead"] is True
    assert rows["LITELLM_BASE"]["set"] is True
    assert rows["LITELLM_BASE"]["default_looks_dead"] is False
