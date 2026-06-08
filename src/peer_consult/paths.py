from pathlib import Path
from .utils import run

class SystemExitException(Exception):
    pass

def find_project_root(explicit_root: str) -> Path:
    if explicit_root:
        p = Path(explicit_root).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        return p.resolve()

    rc, out, _ = run(["git", "rev-parse", "--show-toplevel"])
    if rc == 0 and out.strip():
        p = Path(out.strip()).expanduser()
        if p.exists():
            return p.resolve()

    return Path.cwd().resolve()

def peer_consult_dir(project_root: Path) -> Path:
    return project_root / "docs" / "peer_consult"

def resolve_from_project_root(path_str: str, project_root: Path) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = project_root / p
    return p

def ensure_under_peer_consult_dir(p: Path, peer_dir: Path) -> Path:
    base = peer_dir.resolve()
    resolved = p.resolve()
    if not resolved.is_relative_to(base):
        raise SystemExitException(
            "为遵循协作边界：只允许读取 `docs/peer_consult/` 下的上下文文件；"
            "请把需要提供的日志/片段脱敏后复制到该目录。"
        )
    return resolved
