import json
import sys
from datetime import datetime, timezone
from .cli import parse_args
from .paths import find_project_root, peer_consult_dir, resolve_from_project_root, ensure_under_peer_consult_dir, SystemExitException
from .utils import safe_truncate, slugify, unique_path
from .providers import build_request_pack, call_claude, call_gemini, common_and_diff
from .engine import compact_peer, render_summary_markdown

def ensure_raw_gitignored(peer_dir):
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
    project_root,
    peer_dir,
    base_stem: str,
    reason: str,
    question: str,
    context_file_display: str,
    claude_raw: dict,
    gemini_raw: dict,
) -> list:
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
    args = parse_args()
    project_root = find_project_root(args.project_root)
    peer_dir = peer_consult_dir(project_root)

    if args.extra.strip():
        print("Error: --extra is disabled for security.")
        sys.exit(1)
    if args.include_diff or args.include_status:
        print("Error: --include-diff and --include-status are disabled.")
        sys.exit(1)

    extra_text = ""
    context_file_display = ""
    if args.extra_file:
        try:
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
        except SystemExitException as e:
            print(f"Error: {e}")
            sys.exit(1)

    prompt = build_request_pack(args.question, extra_text, git_text="")
    schema_json = json.dumps({
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
    }, ensure_ascii=False, separators=(",", ":"))

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
            sys.exit(2)
        return

    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    main()
