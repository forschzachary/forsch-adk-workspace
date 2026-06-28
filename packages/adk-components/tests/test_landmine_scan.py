import textwrap
from pathlib import Path
from forsch.adk_components.tools.landmine_audit import scan_hardcoded_paths


def _ws(tmp_path: Path, rel: str, body: str) -> Path:
    f = tmp_path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(textwrap.dedent(body))
    return tmp_path


def test_flags_raw_dead_path_but_not_env_default(tmp_path):
    root = _ws(tmp_path, "pkg/m.py", '''
        import os
        DEAD = "/opt/data/workspace/adk"            # flagged
        OK = os.environ.get("X", "/opt/data/home")  # NOT flagged (env-first default)
    ''')
    hits = scan_hardcoded_paths(str(root))
    flagged = {(h["line"], h["rule"]) for h in hits}
    assert any(r == "dead-fleet-path" for _, r in flagged)
    assert sum(1 for _, r in flagged if r == "dead-fleet-path") == 1  # only the raw literal


def test_skips_venv_and_git(tmp_path):
    _ws(tmp_path, ".venv/lib/x.py", 'D = "/opt/data/x"')
    _ws(tmp_path, "real.py", 'D = "/tmp/fine"')
    assert scan_hardcoded_paths(str(tmp_path)) == []
