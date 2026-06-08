import json
import re
from .utils import compact_text, compact_list, compact_options, bullets, render_options_compact, join_inline
from .providers import has_schema_keys, normalize_for_compare, common_and_diff, recommended_option_snapshot

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
