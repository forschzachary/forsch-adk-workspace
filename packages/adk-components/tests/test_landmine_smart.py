import textwrap
from pathlib import Path
from forsch.adk_components.tools.landmine_audit import scan_hardcoded_paths


def _ws(tmp_path: Path, rel: str, body: str) -> Path:
    f = tmp_path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(textwrap.dedent(body))
    return tmp_path


def test_comment_only_dead_path_not_flagged(tmp_path):
    root = _ws(tmp_path, "m.py", '# references /opt/data/x for docs\nGOOD = "/tmp/ok"\n')
    assert scan_hardcoded_paths(str(root)) == []


def test_inline_comment_does_not_hide_real_hardcode(tmp_path):
    root = _ws(tmp_path, "m.py", 'BAD = "/opt/data/x"  # trailing note\n')
    hits = [h for h in scan_hardcoded_paths(str(root)) if h["rule"] == "dead-fleet-path"]
    assert len(hits) == 1


def test_suppression_marker_skips_line(tmp_path):
    root = _ws(tmp_path, "m.py", 'PAT = "/opt/data/x"  # landmine: allow\n')
    assert scan_hardcoded_paths(str(root)) == []
