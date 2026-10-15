from pathlib import Path

import pytest

from peer_consult import providers
from peer_consult.paths import (
    SystemExitException,
    ensure_under_peer_consult_dir,
    find_project_root,
    peer_consult_dir,
    resolve_from_project_root,
)
from peer_consult.utils import compact_text, safe_truncate, slugify, unique_path


def test_safe_truncate():
    assert safe_truncate("abc", 0) == ""
    assert safe_truncate("abc", 5) == "abc"
    assert safe_truncate("abcdef", 3) == "abc\n...[truncated]..."


def test_slugify():
    assert slugify("") == "peer-consult"
    assert slugify("Fix Login Bug!\nsecond line") == "fix-login-bug"
    assert slugify("修复 登录") == "修复-登录"
    assert len(slugify("x" * 100)) == 32


def test_compact_text():
    assert compact_text("a   b\n c", 50) == "a b c"
    assert compact_text("abcdefgh", 6) == "abc..."
    assert compact_text(None, 10) == ""


def test_unique_path(tmp_path):
    assert unique_path(tmp_path, "a.md") == tmp_path / "a.md"
    (tmp_path / "a.md").write_text("x")
    assert unique_path(tmp_path, "a.md") == tmp_path / "a-1.md"


def test_paths_boundary(tmp_path):
    root = find_project_root(str(tmp_path))
    peer_dir = peer_consult_dir(root)
    assert peer_dir == root / "docs" / "peer_consult"
    peer_dir.mkdir(parents=True)

    inside = resolve_from_project_root("docs/peer_consult/ctx.md", root)
    assert ensure_under_peer_consult_dir(inside, peer_dir) == inside.resolve()

    with pytest.raises(SystemExitException):
        ensure_under_peer_consult_dir(resolve_from_project_root("docs/peer_consult/../../secret", root), peer_dir)
    with pytest.raises(SystemExitException):
        ensure_under_peer_consult_dir(Path("/etc/passwd"), peer_dir)


def test_common_and_diff_normalizes():
    common, only_a, only_b = providers.common_and_diff(["Fix Bug A", "Retry"], ["fix bug-a", "Cache"])
    assert common == ["Fix Bug A"]
    assert only_a == ["Retry"]
    assert only_b == ["Cache"]


def test_build_request_pack_contains_contract():
    pack = providers.build_request_pack("Why does X fail?", "log line", git_text="")
    assert pack.startswith("# Problem\nWhy does X fail?")
    assert "# Evidence / Logs\nlog line" in pack
    assert "# Output Contract" in pack


def test_has_schema_keys():
    assert providers.has_schema_keys({"root_causes": [], "options": [], "recommended_option": "", "questions": []})
    assert not providers.has_schema_keys({"options": []})


def test_missing_cli_returns_error(monkeypatch):
    monkeypatch.setattr(providers, "has_cmd", lambda name: False)
    result, _ = providers.call_claude("p", "{}")
    assert "claude" in result["error"]
    result, _ = providers.call_gemini("p")
    assert "gemini" in result["error"]


def test_recommended_option_snapshot():
    peer = {"recommended_option": "B", "options": [{"name": "A"}, {"name": "B", "tests": ["t"]}]}
    assert providers.recommended_option_snapshot(peer)["tests"] == ["t"]
    assert providers.recommended_option_snapshot({"error": "x"})["name"] == ""
