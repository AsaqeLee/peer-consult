import shutil
import subprocess
import re

def run(cmd, input_text=None):
    p = subprocess.run(
        cmd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()

def has_cmd(cmd_name: str) -> bool:
    return shutil.which(cmd_name) is not None

def safe_truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]..."

def slugify(text: str, max_len: int = 32) -> str:
    text = (text or "").strip()
    if not text:
        return "peer-consult"
    text = text.splitlines()[0].strip()

    out = []
    last_dash = False
    for ch in text.lower():
        is_cjk = "\u4e00" <= ch <= "\u9fff"
        if ch.isalnum() or is_cjk:
            out.append(ch)
            last_dash = False
            continue
        if not last_dash:
            out.append("-")
            last_dash = True

    s = re.sub(r"-{2,}", "-", "".join(out)).strip("-")
    if not s:
        s = "peer-consult"
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "peer-consult"

def unique_path(dir_path, filename: str):
    candidate = dir_path / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    for i in range(1, 1000):
        alt = dir_path / f"{stem}-{i}{suffix}"
        if not alt.exists():
            return alt
    from .paths import SystemExitException
    raise SystemExitException(f"too many conflicting files in {dir_path}")

def bullets(items):
    if not items:
        return "-（无）"
    return "\n".join([f"- {x}" for x in items])

def compact_text(s: str, max_len: int) -> str:
    if not isinstance(s, str):
        return ""
    s = " ".join(s.split())
    if len(s) <= max_len:
        return s
    if max_len <= 3:
        return s[:max_len]
    return s[: max_len - 3] + "..."

def compact_list(items, max_items: int, max_len: int):
    if not isinstance(items, list):
        return []
    out = []
    for x in items:
        s = compact_text(x, max_len)
        if s:
            out.append(s)
        if len(out) >= max_items:
            break
    return out

def compact_options(options, max_options: int, max_items_each: int, max_len: int):
    if not isinstance(options, list):
        return []
    out = []
    for opt in options:
        if not isinstance(opt, dict):
            continue
        out.append(
            {
                "name": compact_text(opt.get("name", ""), max_len),
                "summary": compact_text(opt.get("summary", ""), max_len),
                "pros": compact_list(opt.get("pros"), max_items_each, max_len),
                "cons": compact_list(opt.get("cons"), max_items_each, max_len),
                "tests": compact_list(opt.get("tests"), max_items_each, max_len),
                "risks": compact_list(opt.get("risks"), max_items_each, max_len),
            }
        )
        if len(out) >= max_options:
            break
    return out

def render_options_compact(options):
    if not options:
        return "-（无）"
    lines = []
    for idx, opt in enumerate(options, start=1):
        name = (opt or {}).get("name") or f"Option {idx}"
        summary = (opt or {}).get("summary") or ""
        lines.append(f"{idx}) {name}：{summary}".strip())
        pros = (opt or {}).get("pros") or []
        cons = (opt or {}).get("cons") or []
        tests = (opt or {}).get("tests") or []
        risks = (opt or {}).get("risks") or []
        if pros:
            lines.append("   - 优点：" + "；".join(pros))
        if cons:
            lines.append("   - 缺点：" + "；".join(cons))
        if tests:
            lines.append("   - 测试：" + "；".join(tests))
        if risks:
            lines.append("   - 风险：" + "；".join(risks))
    return "\n".join(lines).strip()

def join_inline(items):
    items = [x for x in (items or []) if isinstance(x, str) and x.strip()]
    if not items:
        return "（无）"
    return "；".join(items)
