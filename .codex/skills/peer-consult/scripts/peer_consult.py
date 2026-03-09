#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


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


def unique_path(dir_path: Path, filename: str) -> Path:
    candidate = dir_path / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    for i in range(1, 1000):
        alt = dir_path / f"{stem}-{i}{suffix}"
        if not alt.exists():
            return alt
    raise SystemExit(f"too many conflicting files in {dir_path}")


def resolve_from_project_root(path_str: str, project_root: Path) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = project_root / p
    return p


def ensure_under_peer_consult_dir(p: Path, peer_dir: Path) -> Path:
    base = peer_dir.resolve()
    resolved = p.resolve()
    if not resolved.is_relative_to(base):
        raise SystemExit(
            "为遵循协作边界：只允许读取 `docs/peer_consult/` 下的上下文文件；"
            "请把需要提供的日志/片段脱敏后复制到该目录。"
        )
    return resolved


def expected_schema():
    return {
        "type": "object",
        "properties": {
            "root_causes": {"type": "array", "items": {"type": "string"}},
            "options": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "summary": {"type": "string"},
                        "pros": {"type": "array", "items": {"type": "string"}},
                        "cons": {"type": "array", "items": {"type": "string"}},
                        "tests": {"type": "array", "items": {"type": "string"}},
                        "risks": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "summary", "pros", "cons", "tests", "risks"],
                },
            },
            "recommended_option": {"type": "string"},
            "questions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["root_causes", "options", "recommended_option", "questions"],
    }


def schema_example_minified() -> str:
    return json.dumps(
        {
            "root_causes": [],
            "options": [
                {
                    "name": "Option A",
                    "summary": "Do X to fix Y",
                    "pros": [],
                    "cons": [],
                    "tests": [],
                    "risks": [],
                }
            ],
            "recommended_option": "",
            "questions": [],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def build_request_pack(question: str, extra_text: str, git_text: str) -> str:
    pack = []
    pack.append("# Problem\n" + (question or "").strip())
    if extra_text:
        pack.append("# Evidence / Logs\n" + extra_text.strip())

    pack.append(
        "# Operating Constraints\n"
        "- You cannot access tools, network, or local files.\n"
        "- Do NOT propose running commands or reading files.\n"
        "- Base your answer ONLY on the text above.\n"
    )

    pack.append(
        "# Output Contract\n"
        "Return ONLY minified JSON (no markdown, no code fences). The JSON MUST match this shape:\n"
        f"{schema_example_minified()}\n"
        "Constraints:\n"
        "- Arrays MUST exist (can be empty).\n"
        "- Keep each item concise and actionable.\n"
        "- If context is insufficient, still return valid JSON and put clarifying questions in `questions`.\n"
    )
    return "\n\n".join(pack).strip()


def parse_json_maybe(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None


def has_schema_keys(obj) -> bool:
    return isinstance(obj, dict) and all(
        k in obj for k in ("root_causes", "options", "recommended_option", "questions")
    )


def call_claude(prompt: str, schema_json: str):
    raw = {"stdout_json": None, "stdout_text_truncated": "", "stderr": "", "returncode": None}
    if not has_cmd("claude"):
        return {"error": "Missing required command on PATH: claude"}, raw

    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--json-schema",
        schema_json,
    ]
    rc, out, err = run(cmd)
    raw["returncode"] = rc
    raw["stderr"] = err
    raw_obj = parse_json_maybe(out)
    if raw_obj is not None:
        raw["stdout_json"] = raw_obj
    else:
        raw["stdout_text_truncated"] = safe_truncate(out, 20000)
    if rc != 0:
        return {"error": err or "claude failed"}, raw

    wrapper = raw_obj
    if isinstance(wrapper, dict):
        structured = wrapper.get("structured_output")
        if isinstance(structured, dict):
            if has_schema_keys(structured):
                return structured, raw
        result = wrapper.get("result")
        if isinstance(result, str):
            parsed = parse_json_maybe(result)
            if has_schema_keys(parsed):
                return parsed, raw
        if has_schema_keys(wrapper):
            return wrapper, raw

        subtype = wrapper.get("subtype")
        permission_denials = wrapper.get("permission_denials") or []
        if subtype and subtype != "success":
            return {"error": f"claude returned no structured_output (subtype={subtype})"}, raw
        if permission_denials:
            return {"error": "claude permission denied"}, raw

    return {"error": "failed to parse claude json"}, raw


def gemini_repair_prompt(raw_text: str) -> str:
    raw_text = safe_truncate(raw_text or "", 6000)
    return (
        "# Task\n"
        "Convert the following text into STRICT minified JSON. Return ONLY JSON.\n\n"
        "# Output Contract\n"
        "The JSON MUST match this exact shape (arrays must exist):\n"
        f"{schema_example_minified()}\n\n"
        "# Text to convert\n"
        f"{raw_text}\n"
    ).strip()


def call_gemini(prompt: str):
    raw = {"stdout_json": None, "stdout_text_truncated": "", "stderr": "", "returncode": None}
    if not has_cmd("gemini"):
        return {"error": "Missing required command on PATH: gemini"}, raw

    def _call(p: str):
        cmd = ["gemini", "-p", p, "--output-format", "json"]
        rc, out, err = run(cmd)
        return rc, out, err

    rc, out, err = _call(prompt)
    raw["returncode"] = rc
    raw["stderr"] = err
    raw_obj = parse_json_maybe(out)
    if raw_obj is not None:
        raw["stdout_json"] = raw_obj
    else:
        raw["stdout_text_truncated"] = safe_truncate(out, 20000)
    if rc != 0:
        return {"error": err or "gemini failed"}, raw

    wrapper = raw_obj
    if isinstance(wrapper, dict) and "response" in wrapper:
        response = wrapper.get("response")
        if isinstance(response, dict):
            if has_schema_keys(response):
                return response, raw
        if isinstance(response, str):
            parsed = parse_json_maybe(response)
            if has_schema_keys(parsed):
                return parsed, raw

            repair = gemini_repair_prompt(response)
            rc2, out2, err2 = _call(repair)
            if rc2 == 0:
                wrapper2 = parse_json_maybe(out2)
                if isinstance(wrapper2, dict) and "response" in wrapper2:
                    resp2 = wrapper2.get("response")
                    if isinstance(resp2, dict):
                        if has_schema_keys(resp2):
                            return resp2, raw
                    if isinstance(resp2, str):
                        parsed2 = parse_json_maybe(resp2)
                        if has_schema_keys(parsed2):
                            return parsed2, raw

            return {"error": "failed to parse gemini response json (repair failed)"}, raw

    if has_schema_keys(wrapper):
        return wrapper, raw

    return {"error": "failed to parse gemini json"}, raw


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


def compact_peer(peer, max_items: int, max_options: int, max_items_each: int, max_len: int):
    if not isinstance(peer, dict):
        return {"error": "invalid peer output"}
    if "error" in peer:
        return {"error": compact_text(peer.get("error", ""), 240) or "unknown error"}
    if not has_schema_keys(peer):
        return {"error": "peer output missing required keys"}
    return {
        "root_causes": compact_list(peer.get("root_causes"), max_items, max_len),
        "options": compact_options(peer.get("options"), max_options, max_items_each, max_len),
        "recommended_option": compact_text(peer.get("recommended_option", ""), max_len),
        "questions": compact_list(peer.get("questions"), max_items, max_len),
    }


def normalize_for_compare(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "", s)
    return s


def common_and_diff(a, b):
    a_items = [x for x in (a or []) if isinstance(x, str) and x.strip()]
    b_items = [x for x in (b or []) if isinstance(x, str) and x.strip()]
    a_map = {normalize_for_compare(x): x for x in a_items if normalize_for_compare(x)}
    b_map = {normalize_for_compare(x): x for x in b_items if normalize_for_compare(x)}
    common_keys = [k for k in a_map.keys() if k in b_map]
    common = [a_map[k] for k in common_keys]
    only_a = [v for k, v in a_map.items() if k not in b_map]
    only_b = [v for k, v in b_map.items() if k not in a_map]
    return common, only_a, only_b


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


def recommended_option_snapshot(peer):
    if not isinstance(peer, dict) or "error" in peer:
        return {
            "name": "",
            "pros": [],
            "cons": [],
            "tests": [],
            "risks": [],
        }

    rec_name = peer.get("recommended_option") or ""
    rec_norm = normalize_for_compare(rec_name)
    options = peer.get("options") or []
    picked = None
    if rec_norm:
        for opt in options:
            if normalize_for_compare((opt or {}).get("name", "")) == rec_norm:
                picked = opt
                break
    if picked is None and options:
        picked = options[0]

    picked = picked or {}
    return {
        "name": (picked.get("name") or rec_name or "").strip(),
        "pros": list(picked.get("pros") or []),
        "cons": list(picked.get("cons") or []),
        "tests": list(picked.get("tests") or []),
        "risks": list(picked.get("risks") or []),
    }


def decision_draft(summary):
    claude = summary.get("claude", {}) or {}
    gemini = summary.get("gemini", {}) or {}
    auto = summary.get("codex_auto", {}) or {}

    consensus_items = []
    rc_common = auto.get("root_causes_common") or []
    opt_common = auto.get("option_names_common") or []
    if rc_common:
        consensus_items.append("根因共识：" + join_inline(rc_common))
    if opt_common:
        consensus_items.append("方案共识：" + join_inline(opt_common))

    diff_items = []
    if "error" in claude:
        diff_items.append(f"Claude 失败：{claude.get('error')}")
    if "error" in gemini:
        diff_items.append(f"Gemini 失败：{gemini.get('error')}")
    if auto.get("root_causes_claude_only"):
        diff_items.append("Claude-only 根因：" + join_inline(auto.get("root_causes_claude_only")))
    if auto.get("root_causes_gemini_only"):
        diff_items.append("Gemini-only 根因：" + join_inline(auto.get("root_causes_gemini_only")))
    if auto.get("option_names_claude_only"):
        diff_items.append("Claude-only 方案：" + join_inline(auto.get("option_names_claude_only")))
    if auto.get("option_names_gemini_only"):
        diff_items.append("Gemini-only 方案：" + join_inline(auto.get("option_names_gemini_only")))

    c_rec = recommended_option_snapshot(claude)
    g_rec = recommended_option_snapshot(gemini)
    c_name = c_rec.get("name", "")
    g_name = g_rec.get("name", "")

    choice = "（待确认）"
    choice_reason = "（待确认）"
    tests = []

    if "error" in claude and "error" in gemini:
        choice = "（无法裁决：两侧均失败）"
        choice_reason = "先修复输入/环境（例如上下文文件、CLI 可用性），再重跑。"
    elif "error" in claude and "error" not in gemini:
        choice = g_name or "Gemini 推荐方案"
        choice_reason = "Claude 侧失败，优先采用可执行的一侧建议，并用测试兜底。"
    elif "error" in gemini and "error" not in claude:
        choice = c_name or "Claude 推荐方案"
        choice_reason = "Gemini 侧失败，优先采用可执行的一侧建议，并用测试兜底。"
    else:
        if normalize_for_compare(c_name) and normalize_for_compare(c_name) == normalize_for_compare(g_name):
            choice = c_name
            choice_reason = "两侧推荐一致，优先采用以降低回归风险。"
        else:
            c_tests = len(c_rec.get("tests") or [])
            g_tests = len(g_rec.get("tests") or [])
            c_risks = len(c_rec.get("risks") or [])
            g_risks = len(g_rec.get("risks") or [])
            if c_tests != g_tests:
                pick = "Claude" if c_tests > g_tests else "Gemini"
                choice = c_name if c_tests > g_tests else g_name
                choice_reason = f"以可验证性优先（{pick} 给出的测试项更多）。"
            elif c_risks != g_risks:
                pick = "Claude" if c_risks < g_risks else "Gemini"
                choice = c_name if c_risks < g_risks else g_name
                choice_reason = f"以风险最小优先（{pick} 推荐方案列出的风险更少）。"
            else:
                choice = "先写测试仲裁分歧，再选最小改动"
                choice_reason = "两侧分歧且难以仅凭摘要裁决；先把分歧点转成测试，再用结果决定。"

    tests = list(dict.fromkeys((c_rec.get("tests") or []) + (g_rec.get("tests") or [])))
    if not tests:
        tests = ["为每个分歧点补 1 个回归测试/断言（先覆盖失败路径与边界条件）"]

    return {
        "consensus_items": consensus_items,
        "diff_items": diff_items,
        "claude_compare": (
            f"{c_name or '（无）'}（测试:{len(c_rec.get('tests') or [])} 风险:{len(c_rec.get('risks') or [])} "
            f"优:{join_inline(c_rec.get('pros'))} 缺:{join_inline(c_rec.get('cons'))}）"
        ),
        "gemini_compare": (
            f"{g_name or '（无）'}（测试:{len(g_rec.get('tests') or [])} 风险:{len(g_rec.get('risks') or [])} "
            f"优:{join_inline(g_rec.get('pros'))} 缺:{join_inline(g_rec.get('cons'))}）"
        ),
        "choice": choice,
        "choice_reason": choice_reason,
        "tests": tests,
    }


def render_summary_markdown(summary):
    def indented_bullets(items, indent: str = "  "):
        items = [x for x in (items or []) if isinstance(x, str) and x.strip()]
        if not items:
            return f"{indent}-（无）"
        return "\n".join([f"{indent}- {x}" for x in items])

    md = []
    md.append("# Peer Consult 摘要\n")
    md.append(f"- 生成时间：{summary.get('generated_at_local','')}\n")
    md.append(f"- 问题：{summary.get('question','')}\n")
    context_file = summary.get("context_file", "")
    md.append(f"- 上下文文件：{context_file or '（无）'}\n")
    raw_paths = summary.get("raw_paths") or []
    if raw_paths:
        md.append("- 原文留存（仅失败或手动启用时）：\n")
        md.append("\n".join([f"  - {p}" for p in raw_paths]) + "\n")

    claude = summary.get("claude", {})
    md.append("## Claude Code（摘要）\n")
    if "error" in claude:
        md.append(f"- 调用失败：{claude.get('error')}\n")
    else:
        md.append("### 根因假设\n" + bullets(claude.get("root_causes")) + "\n")
        md.append("### 方案（摘录）\n" + render_options_compact(claude.get("options")) + "\n")
        md.append(f"### 推荐方案\n- {claude.get('recommended_option') or '（无）'}\n")
        md.append("### 追问\n" + bullets(claude.get("questions")) + "\n")

    gemini = summary.get("gemini", {})
    md.append("## Gemini CLI（摘要）\n")
    if "error" in gemini:
        md.append(f"- 调用失败：{gemini.get('error')}\n")
    else:
        md.append("### 根因假设\n" + bullets(gemini.get("root_causes")) + "\n")
        md.append("### 方案（摘录）\n" + render_options_compact(gemini.get("options")) + "\n")
        md.append(f"### 推荐方案\n- {gemini.get('recommended_option') or '（无）'}\n")
        md.append("### 追问\n" + bullets(gemini.get("questions")) + "\n")

    md.append("## Codex 自动归纳（候选）\n")
    codex_auto = summary.get("codex_auto", {})
    md.append("### 根因共识候选\n" + bullets(codex_auto.get("root_causes_common")) + "\n")
    md.append("### 根因分歧候选\n")
    md.append("- Claude-only：\n" + bullets(codex_auto.get("root_causes_claude_only")) + "\n")
    md.append("- Gemini-only：\n" + bullets(codex_auto.get("root_causes_gemini_only")) + "\n")

    md.append("### 方案名共识候选\n" + bullets(codex_auto.get("option_names_common")) + "\n")
    md.append("### 方案名分歧候选\n")
    md.append("- Claude-only：\n" + bullets(codex_auto.get("option_names_claude_only")) + "\n")
    md.append("- Gemini-only：\n" + bullets(codex_auto.get("option_names_gemini_only")) + "\n")

    d = decision_draft(summary)
    md.append("## Codex 裁决（你需要填写）\n")
    md.append("> 注：以下为 Codex 自动回填草案，可直接修改；上线前务必用测试验证。\n\n")
    md.append("- 共识点：\n" + indented_bullets(d["consensus_items"]) + "\n")
    md.append("- 分歧点：\n" + indented_bullets(d["diff_items"]) + "\n")
    md.append("- 方案对比（优/缺/风险/可验证性）：\n")
    md.append(f"  - Claude：{d['claude_compare']}\n")
    md.append(f"  - Gemini：{d['gemini_compare']}\n")
    md.append("- 我的选择与理由（最小改动 + 可验证性 + 风险最小）：\n")
    md.append(f"  - {d['choice']}；{d['choice_reason']}\n")
    md.append("- 测试计划（用测试把分歧写进去）：\n" + indented_bullets(d["tests"]) + "\n")
    return "\n".join(md).strip() + "\n"


def ensure_raw_gitignored(peer_dir: Path):
    gitignore_path = peer_dir / ".gitignore"
    line = "/raw/"
    if not gitignore_path.exists():
        gitignore_path.write_text(line + "\n", encoding="utf-8")
        return

    try:
        existing = gitignore_path.read_text(encoding="utf-8")
    except Exception:
        return

    existing_lines = {x.strip() for x in existing.splitlines() if x.strip()}
    if line in existing_lines:
        return
    gitignore_path.write_text(existing.rstrip() + "\n" + line + "\n", encoding="utf-8")


def save_raw_outputs(
    *,
    project_root: Path,
    peer_dir: Path,
    base_stem: str,
    reason: str,
    question: str,
    context_file_display: str,
    claude_raw: dict,
    gemini_raw: dict,
) -> list[str]:
    raw_dir = peer_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    ensure_raw_gitignored(peer_dir)

    payload_common = {
        "saved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "reason": reason,
        "question": question,
        "context_file": context_file_display,
        "notice": "raw 输出可能包含敏感信息；建议仅用于调试，问题解决后及时删除，且不要提交到仓库历史。",
    }

    paths = []
    for tool, raw in (("claude", claude_raw), ("gemini", gemini_raw)):
        payload = dict(payload_common)
        payload["tool"] = tool
        payload["raw"] = raw

        p = unique_path(raw_dir, f"{base_stem}-{tool}.json")
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            paths.append(str(p.relative_to(project_root)))
        except Exception:
            paths.append(str(p))

    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", required=True)
    ap.add_argument(
        "--project-root",
        "--cd",
        dest="project_root",
        default="",
        help="项目根目录（默认：git 顶层；无 git 则当前目录）",
    )
    ap.add_argument(
        "--extra",
        default="",
        help="(已禁用) 为保证可审计与边界，请把内容写入 docs/peer_consult/ 下文件并使用 --extra-file",
    )
    ap.add_argument(
        "--extra-file",
        "--context-file",
        dest="extra_file",
        default="",
        help="从文件读取日志/上下文（必须位于 docs/peer_consult/ 下）",
    )
    ap.add_argument(
        "--include-diff",
        action="store_true",
        help="(已禁用) 请把必要 diff 片段手动粘贴到 docs/peer_consult/ 的上下文文件中",
    )
    ap.add_argument(
        "--include-status",
        action="store_true",
        help="(已禁用) 请把必要 status 片段手动粘贴到 docs/peer_consult/ 的上下文文件中",
    )
    ap.add_argument("--max-chars", type=int, default=12000)
    ap.add_argument(
        "--save-raw",
        action="store_true",
        help="将 Claude/Gemini 原文输出保存到 docs/peer_consult/raw（默认仅在失败时保存）",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when any peer call fails (default: false)",
    )
    args = ap.parse_args()

    project_root = find_project_root(args.project_root)
    peer_dir = peer_consult_dir(project_root)

    if args.extra.strip():
        raise SystemExit(
            "为遵循协作边界：禁止直接用 --extra 传入内容；"
            "请把内容写入 `docs/peer_consult/` 下文件并用 --extra-file/--context-file 指定。"
        )
    if args.include_diff or args.include_status:
        raise SystemExit(
            "为遵循协作边界：本脚本不再自动读取 git diff/status；"
            "请将必要片段脱敏后粘贴到 `docs/peer_consult/` 下的上下文文件。"
        )

    extra_text = ""
    context_file_display = ""
    if args.extra_file:
        extra_path = ensure_under_peer_consult_dir(
            resolve_from_project_root(args.extra_file, project_root),
            peer_dir,
        )
        extra_text = extra_path.read_text(encoding="utf-8")
        extra_text = safe_truncate(extra_text, args.max_chars)
        try:
            context_file_display = str(extra_path.relative_to(project_root))
        except Exception:
            context_file_display = str(extra_path)

    prompt = build_request_pack(args.question, extra_text, git_text="")

    schema_json = json.dumps(expected_schema(), ensure_ascii=False, separators=(",", ":"))

    now_local = datetime.now().astimezone()
    timestamp = now_local.strftime("%y-%m-%d-%H%M")
    slug = slugify(args.question)
    base_stem = f"{timestamp}-{slug}"

    out_dir = peer_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = unique_path(out_dir, f"{base_stem}.md").resolve()

    claude_result, claude_raw = call_claude(prompt, schema_json)
    gemini_result, gemini_raw = call_gemini(prompt)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "generated_at_local": now_local.isoformat(),
        "question": args.question,
        "context_file": context_file_display,
        "claude": compact_peer(claude_result, max_items=6, max_options=3, max_items_each=3, max_len=180),
        "gemini": compact_peer(gemini_result, max_items=6, max_options=3, max_items_each=3, max_len=180),
    }
    root_common, root_claude_only, root_gemini_only = common_and_diff(
        summary["claude"].get("root_causes", []), summary["gemini"].get("root_causes", [])
    )
    opt_common, opt_claude_only, opt_gemini_only = common_and_diff(
        [o.get("name", "") for o in summary["claude"].get("options", [])],
        [o.get("name", "") for o in summary["gemini"].get("options", [])],
    )
    summary["codex_auto"] = {
        "root_causes_common": root_common,
        "root_causes_claude_only": root_claude_only,
        "root_causes_gemini_only": root_gemini_only,
        "option_names_common": opt_common,
        "option_names_claude_only": opt_claude_only,
        "option_names_gemini_only": opt_gemini_only,
    }

    has_error = ("error" in claude_result) or ("error" in gemini_result)
    if has_error or args.save_raw:
        reason = "peer_error" if has_error else "manual_save_raw"
        summary["raw_paths"] = save_raw_outputs(
            project_root=project_root,
            peer_dir=peer_dir,
            base_stem=out_path.stem,
            reason=reason,
            question=args.question,
            context_file_display=context_file_display,
            claude_raw=claude_raw,
            gemini_raw=gemini_raw,
        )

    out_path.write_text(render_summary_markdown(summary), encoding="utf-8")

    if has_error:
        print(f"Wrote (with errors): {out_path}")
        if args.strict:
            raise SystemExit(2)
        return

    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
