import json
from .utils import run, has_cmd, safe_truncate

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

def normalize_for_compare(s: str) -> str:
    import re
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
