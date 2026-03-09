---
name: peer-consult
description: 当需要头脑风暴/多方案决策/卡住时/peer_consult，调用 Claude Code 与 Gemini CLI 给出独立建议；Codex 负责汇总并分析优缺点，输出裁决与下一步行动清单。
compatibility: 需要本机可执行命令 claude 与 gemini；需要 python3；所有上下文与产物统一落盘在 docs/peer_consult/（便于审计与脱敏）。
---

# 目标
你是 Codex 主执行者。遇到需要头脑风暴或多方案权衡时，必须征询 **Claude Code** 与 **Gemini CLI** 的独立意见，避免单模型盲点；随后你必须基于两者输出做 **优缺点分析** 并给出可验证的裁决与测试计划，同时Codex也可发表意见。

## 触发条件（满足任一即触发）
- 连续两轮定位/修复仍无进展，或关键测试失败且根因不清晰
- 需要在多个方案间做取舍（性能/兼容/侵入性/可维护性）
- 涉及安全敏感面：鉴权/权限/反序列化/命令执行/依赖升级等

## 输入（你需要准备）
- `question`：问题摘要（期望 vs 实际，尽量一句话到三句话）
- 上下文文件（推荐）：把关键日志/证据/必要片段（已脱敏、只保留关键段）写入 `docs/peer_consult/` 下的一个文件（例如 `docs/peer_consult/request-xxxx.md`），`xxxx` 取 `--question` 首行摘要的 slug（同名冲突追加 `-1/-2`）

> 约束：为保证边界可控与可审计，脚本不再自动读取 `git diff/status`，也禁止直接用参数传入大段日志；必须先落盘到 `docs/peer_consult/`。

## 输出（脚本生成）
- 仅生成一份摘要文件：`docs/peer_consult/YY-MM-DD-HHMM-xxxx.md`
  - 内容：Claude/Gemini 的要点摘要（截断/限量）+ 自动归纳的共识/分歧候选 + Codex 裁决（自动回填草案，可编辑）
  - 命名：`xxxx` 取 `--question` 首行摘要的 slug（同名冲突追加 `-1/-2`）
  - 默认 **不落盘** Claude/Gemini 原始回答（raw 或完整 JSON）
  - 按策略2：当任一侧调用失败/解析失败，或你显式传入 `--save-raw` 时，会额外保存原文到 `docs/peer_consult/raw/`（用于调试；问题解决后建议删除，且不要提交到仓库历史）

## 安装到 `~/.codex/skills/peer-consult`（推荐）
> 目的：把 Skill 从项目仓库移出，作为本机全局能力复用；产物仍写入目标项目的 `docs/peer_consult/`。

```bash
mkdir -p ~/.codex/skills
cp -R .codex/skills/peer-consult ~/.codex/skills/
```

### JSON 契约（用于“优缺点/方案对比”）
脚本在调用两侧时会要求返回 **仅 JSON**（无 markdown），并在内存中用于生成摘要（不会把原 JSON 结果写入仓库）。结构如下（数组可为空但必须存在）：

```json
{
  "root_causes": ["..."],
  "options": [
    {
      "name": "方案名",
      "summary": "一句话描述怎么做",
      "pros": ["..."],
      "cons": ["..."],
      "tests": ["..."],
      "risks": ["..."]
    }
  ],
  "recommended_option": "方案名（可为空）",
  "questions": ["..."]
}
```

## 工作流（必须按顺序）
1) 生成“咨询包”：将上下文写入 `docs/peer_consult/` 下文件（建议复制 `~/.codex/skills/peer-consult/assets/request_template.md`；或项目内 `.codex/skills/peer-consult/assets/request_template.md`）。  
2) 运行脚本收集两方意见：  
   - 项目级安装：`python3 .codex/skills/peer-consult/scripts/peer_consult.py --question "<摘要>" --context-file docs/peer_consult/request.md`
   - 用户级安装：`python3 ~/.codex/skills/peer-consult/scripts/peer_consult.py --question "<摘要>" --context-file docs/peer_consult/request.md`
   - （可选）需要保留原文用于调试：追加 `--save-raw`
   - （可选）如果不在项目根目录执行：追加 `--project-root <path>`（或 `--cd <path>`）
3) 打开脚本生成的摘要文件（路径会打印在 stdout），检查并完善 “Codex 裁决” 部分（脚本已自动回填草案，需你确认/修改）：  
   - 共识点（两方一致的 root causes / 方案）  
   - 分歧点（各自方案的 trade-off）  
   - 你的选择：选哪个方案，为什么（最小改动 + 可验证性 + 风险最小）  
   - 测试计划：新增/修改哪些测试用例来“仲裁分歧”  
4) 落地修复、跑测试、更新结论。

## 安全边界（强制）
- 该 Skill 只做“意见采集”，不允许外部代理直接改代码。
- 默认只保留 `docs/peer_consult/` 下的摘要文件（便于审计与分享）；外部模型原始输出仅在失败或显式启用 `--save-raw` 时保存（见上）。
- 仅在失败或显式启用 `--save-raw` 时，才会写入 `docs/peer_consult/raw/`；该目录建议 gitignore，并在问题解决后清理。
- 上下文文件禁止包含任何密钥/令牌/个人数据；必要时先脱敏再提供。
