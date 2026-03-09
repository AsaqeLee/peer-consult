下面给出一套可落地的“三方协作”机制：以 **Codex（主执行）** 为中心，通过 **Agent Skills** 在遇到卡点时自动/半自动征询 **Claude Code** 与 **Gemini CLI** 的独立意见，并将两者结论结构化汇总，供 Codex 继续推进实现与验证。

> 本仓库的落地版本收敛为“默认只存摘要”的工作方式：每次征询生成一份摘要文件 `docs/peer_consult/YY-MM-DD-HHMM-xxxx.md`；按策略2，仅在失败或显式启用 `--save-raw` 时把原文输出写入 `docs/peer_consult/raw/`（用于调试，建议 gitignore 与及时清理）。本文下方出现的 `peer_consult_report.*` 落盘示例仅作说明；如与实现不一致，以 `.codex/skills/peer-consult/SKILL.md` 与 `docs/peer_consult/README.md` 为准。

---

## 一、协作原则与分工

### 1) 分工建议

* **Codex：主执行与集成者**

  * 负责复现问题、最小化改动、落地修复、跑测试、生成最终 diff/PR。
  * 用 Skills 把“什么时候要请外援、怎么提问、怎么汇总”固化成可重复流程。([OpenAI Developers][1])
* **Claude Code：独立审阅者（偏代码审查/诊断）**

  * 以“审阅者视角”给出根因假设、风险点、代码层面的修复建议与审查清单。
  * 支持用 `claude -p` 非交互运行，并可用 `--output-format json`、`--json-schema` 强制结构化输出。([Claude Code][2])
* **Gemini CLI：第二审阅者（偏对照方案/边界覆盖）**

  * 给出替代解法、边界条件、回归风险与测试补强建议。
  * 支持 Headless（`-p/--prompt`）与 `--output-format json` 便于自动化收集。([Gemini CLI][3])

### 2) 触发“征询意见”的典型条件（建议写进 Skill）

* 连续两轮定位/修复后仍无法稳定复现或无法通过关键测试。
* 需要在多个方案间做取舍（性能/兼容/侵入性/可维护性）。
* 涉及安全敏感面：鉴权、权限、加密、支付、反序列化、命令执行、供应链依赖更新等。
* 变更范围较大（跨模块重构、数据迁移、协议变更）。

---

## 二、用 Agent Skills 把流程“固化”为可重复工作流

三者都支持（或基于）Agent Skills 的 **SKILL.md** 开放标准：Skill 是一个目录，至少包含 `SKILL.md`（YAML frontmatter + Markdown 指令），可附带 `scripts/`、`references/`、`assets/`。([OpenAI Developers][1])

### 1) 三个工具的 Skills 放置位置（仓库级 vs 用户级）

* **Codex**

  * 仓库级：`$REPO_ROOT/.codex/skills/`（推荐，随代码库共享）([OpenAI Developers][1])
  * 用户级：`~/.codex/skills/`([OpenAI Developers][1])
  * 重要注意：Codex 会跳过符号链接目录（不建议用 symlink 共享同一份技能目录）。([OpenAI Developers][4])
* **Claude Code**

  * 仓库级：`.claude/skills/`
  * 用户级：`~/.claude/skills/`([Claude Code][5])
* **Gemini CLI**

  * 项目级：`.gemini/skills/`
  * 用户级：`~/.gemini/skills/`([Gemini CLI][6])

结论：**同一个 Skill（同一份 `SKILL.md` + scripts）可以按需复制到三个目录体系中**，实现“同标准，多运行时”的协作；Codex 侧建议以仓库级 `.codex/skills` 为主，方便团队复用。([Agent Skills][7])

---

## 三、推荐落地：在 Codex 里做一个“征询 Claude + Gemini”的 Skill

### 1) 目录结构示例（仓库内）

```text
.codex/skills/peer-consult/
  SKILL.md
  scripts/
    peer_consult.py
  assets/
    request_template.md
```

> Codex 技能的基本定义与显式调用方式（`/skills`、输入 `$` 选择技能）见官方说明。([OpenAI Developers][1])

### 2) `SKILL.md` 示例（可直接改名套用）

```md
---
name: peer-consult
description: 当调试卡住、测试失败原因不明、或存在多方案权衡时，调用 Claude Code 与 Gemini CLI 给出独立诊断与建议，并输出对比汇总与下一步行动清单。
compatibility: 需要本机可执行命令 claude 与 gemini；需要 python3；建议在 git 仓库内运行以便采集 diff。
metadata:
  owner: your-team
  version: "0.1"
---

# 目标
你是 Codex 主执行者。当满足触发条件时，必须征询 Claude Code 与 Gemini 的独立意见，避免单模型盲点，并形成可执行的下一步计划。

## 触发条件
- 连续两轮定位仍无进展；或关键测试无法通过且根因不清晰
- 需要在多个修复方案中做取舍
- 触及安全敏感逻辑/接口/依赖

## 工作流（必须按顺序）
1) 生成“咨询包”：
   - 问题摘要（期望 vs 实际）
   - 复现步骤/失败日志（截取关键段）
   - 相关文件路径与关键代码片段（必要时）
   - 当前改动 diff（若已有尝试修复）
2) 运行脚本收集两方意见：
   - `python3 scripts/peer_consult.py --question "<摘要>" --include-diff --include-status --out peer_consult_report.md`
3) 阅读报告并输出：
   - 共识点（两方都同意的根因/修复）
   - 分歧点（各自建议与权衡）
   - 你选择的方案 + 选择理由
   - 需要新增/修改的测试清单
4) 落地修复、跑测试、更新结论。
```

Skill 的 `name/description`、可选 `compatibility/metadata/allowed-tools` 等字段约束与规范来自 Agent Skills 标准；`scripts/`、`assets/` 也属于推荐约定。([Agent Skills][7])

---

## 四、脚本实现：一键调用 `claude -p` 与 `gemini -p` 并生成对比报告

下面脚本的设计目标是“只收集意见，不让外部代理改代码”，因此把代码上下文（diff、status、关键日志）直接作为输入喂给两个 CLI，以减少它们访问本地文件系统/工具的必要性。

### `scripts/peer_consult.py`（示例，可直接用）

```python
#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

def run(cmd, input_text=None):
    p = subprocess.run(
        cmd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def must_have(cmd_name: str):
    if shutil.which(cmd_name) is None:
        raise SystemExit(f"Missing required command on PATH: {cmd_name}")

def git_snippet(args):
    parts = []
    if args.include_status:
        rc, out, err = run(["git", "status", "--porcelain=v1"])
        if rc == 0 and out:
            parts.append("## git status --porcelain\n" + out)
    if args.include_diff:
        # 仅抓工作区 diff（可按需改为 --staged）
        rc, out, err = run(["git", "diff", "--no-color"])
        if rc == 0 and out:
            # 防止上下文过大
            out = out[: args.max_chars]
            parts.append("## git diff\n" + out)
    return "\n\n".join(parts).strip()

def build_request_pack(question, extra_text, git_text):
    pack = []
    pack.append("# Problem\n" + question.strip())
    if extra_text:
        pack.append("# Evidence / Logs\n" + extra_text.strip())
    if git_text:
        pack.append("# Repo Context\n" + git_text.strip())
    pack.append("# Output Contract\n"
                "Return ONLY minified JSON (no markdown) with keys:\n"
                "{\"root_causes\":[],\"recommended_changes\":[],\"tests\":[],\"risks\":[],\"questions\":[]}\n"
                "Keep items concise and actionable.")
    return "\n\n".join(pack).strip()

def call_claude(prompt, schema):
    # Claude Code supports -p/--print and structured output with --json-schema
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--json-schema",
        schema,
    ]
    rc, out, err = run(cmd)
    if rc != 0:
        return {"error": err or "claude failed", "raw": out}
    # claude --output-format json includes metadata; structured output lives in structured_output
    try:
        obj = json.loads(out)
        return obj.get("structured_output") or {"raw_result": obj.get("result", ""), "meta": obj}
    except Exception:
        return {"error": "failed to parse claude json", "raw": out, "stderr": err}

def call_gemini(prompt):
    # Gemini CLI supports headless -p/--prompt and --output-format json
    cmd = ["gemini", "-p", prompt, "--output-format", "json"]
    rc, out, err = run(cmd)
    if rc != 0:
        return {"error": err or "gemini failed", "raw": out}
    try:
        wrapper = json.loads(out)  # has "response" field
        response = wrapper.get("response", "")
        # response itself should be the JSON we asked for
        return json.loads(response)
    except Exception:
        return {"error": "failed to parse gemini json", "raw": out, "stderr": err}

def render_markdown(report):
    def bullets(items):
        if not items:
            return "-（无）"
        return "\n".join([f"- {x}" for x in items])

    claude = report.get("claude", {})
    gemini = report.get("gemini", {})

    md = []
    md.append(f"# Peer Consult Report\n\nGenerated: {report['generated_at']}\n")
    md.append("## Input\n")
    md.append(f"- Question: {report['question']}\n")
    md.append("## Claude Code\n")
    if "error" in claude:
        md.append(f"- ERROR: {claude['error']}\n")
    else:
        md.append("### Root causes\n" + bullets(claude.get("root_causes")) + "\n")
        md.append("### Recommended changes\n" + bullets(claude.get("recommended_changes")) + "\n")
        md.append("### Tests\n" + bullets(claude.get("tests")) + "\n")
        md.append("### Risks\n" + bullets(claude.get("risks")) + "\n")
        md.append("### Questions\n" + bullets(claude.get("questions")) + "\n")

    md.append("## Gemini CLI\n")
    if "error" in gemini:
        md.append(f"- ERROR: {gemini['error']}\n")
    else:
        md.append("### Root causes\n" + bullets(gemini.get("root_causes")) + "\n")
        md.append("### Recommended changes\n" + bullets(gemini.get("recommended_changes")) + "\n")
        md.append("### Tests\n" + bullets(gemini.get("tests")) + "\n")
        md.append("### Risks\n" + bullets(gemini.get("risks")) + "\n")
        md.append("### Questions\n" + bullets(gemini.get("questions")) + "\n")

    md.append("## Next step (for Codex)\n"
              "- 对两方共识点优先落地\n"
              "- 对分歧点按“最小改动 + 可验证性(测试) + 风险最小”裁决\n"
              "- 必须补齐测试后再进入下一轮\n")
    return "\n".join(md).strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", required=True)
    ap.add_argument("--extra", default="", help="paste logs/evidence here (or point Codex to fill)")
    ap.add_argument("--include-diff", action="store_true")
    ap.add_argument("--include-status", action="store_true")
    ap.add_argument("--max-chars", type=int, default=12000)
    ap.add_argument("--out", default="peer_consult_report.md")
    ap.add_argument("--out-json", default="peer_consult_report.json")
    args = ap.parse_args()

    must_have("claude")
    must_have("gemini")

    git_text = git_snippet(args) if (args.include_diff or args.include_status) else ""
    prompt = build_request_pack(args.question, args.extra, git_text)

    # Claude JSON schema (enforced by CLI)
    schema = json.dumps({
        "type": "object",
        "properties": {
            "root_causes": {"type": "array", "items": {"type": "string"}},
            "recommended_changes": {"type": "array", "items": {"type": "string"}},
            "tests": {"type": "array", "items": {"type": "string"}},
            "risks": {"type": "array", "items": {"type": "string"}},
            "questions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["root_causes", "recommended_changes", "tests", "risks", "questions"]
    })

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "question": args.question,
        "claude": call_claude(prompt, schema),
        "gemini": call_gemini(prompt),
    }

    Path(args.out_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.out).write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote: {args.out}\nWrote: {args.out_json}")

if __name__ == "__main__":
    main()
```

上述脚本使用的关键 CLI 能力依据各自官方文档：

* Claude Code：`-p/--print` 非交互、`--output-format json`、`--json-schema` 结构化输出。([Claude Code][2])
* Gemini CLI：Headless `-p/--prompt`、`--output-format json`（JSON wrapper 含 `response` 字段）。([Gemini CLI][3])

### 运行方式示例

```bash
python3 .codex/skills/peer-consult/scripts/peer_consult.py \
  --question "pytest 中 test_login 失败：期望 302，实际 500；怀疑 auth 中间件回归" \
  --include-status --include-diff \
  --out peer_consult_report.md
```

---

## 五、Codex 侧的使用方式（建议写进团队约定）

* 显式调用：在 Codex CLI/IDE 里用 `/skills` 查列表，或输入 `$peer-consult` 触发该 Skill。([OpenAI Developers][1])
* 隐式触发：把 `description` 写得足够“像用户/你自己会说的话”，Codex 可在匹配任务时自行调用 Skill。([OpenAI Developers][1])

---

## 六、汇总与裁决规则（两方意见不一致时怎么做）

建议 Codex 在拿到 `peer_consult_report.md/json` 后，按如下顺序裁决：

1. **以可验证性为王**：谁给出的建议能用最少新增测试/断言快速证伪/证实，优先走谁的路径。
2. **优先最小修复**：在满足需求前提下，优先侵入性最小、回归面最小的改动。
3. **遇到安全/鉴权/序列化**：宁可更保守、更显式；并补齐负向测试与边界测试。
4. **把分歧“写进测试”**：将两个方案各自担心的风险点转成测试用例，让 CI 做最终仲裁。

---

## 七、工程化建议（可选，但强烈推荐）

* 把 Skill 目录当作“可审计资产”纳入代码评审：`SKILL.md` 的触发条件、输出格式、脚本行为都应可读可测。([OpenAI Developers][4])
* 对外部 CLI 保持“只读诊断”默认：

  * Claude Code 支持通过 CLI flags 控制行为与输出；尽量用 print 模式做诊断，必要时再放开工具权限。([Claude Code][2])
  * Gemini CLI 同样提供 headless 与结构化输出，适合用作“第二意见采集器”。([Gemini CLI][3])

---

如果你希望我把上面这套方案进一步“收敛成你们团队可直接复制的仓库骨架”（包含 `.codex/skills` + `.claude/skills` + `.gemini/skills` 三份同步、以及一个 `make consult` 命令），我也可以给出一份更完整的目录布局与同步脚本规范。

[1]: https://developers.openai.com/codex/skills "Agent Skills"
[2]: https://code.claude.com/docs/en/headless "Run Claude Code programmatically - Claude Code Docs"
[3]: https://geminicli.com/docs/cli/headless/ "Headless mode | Gemini CLI"
[4]: https://developers.openai.com/codex/skills/create-skill "Create skills"
[5]: https://code.claude.com/docs/en/skills "Agent Skills - Claude Code Docs"
[6]: https://geminicli.com/docs/cli/skills/ "Agent Skills | Gemini CLI"
[7]: https://agentskills.io/specification "Specification - Agent Skills"
