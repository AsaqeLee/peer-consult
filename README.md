# `peer-consult`

这个仓库当前主要提供一个 Codex Skill：`peer-consult`。

它的作用是：在需要头脑风暴、多方案权衡或定位卡住时，由 Codex 调用 `Claude Code` 和 `Gemini CLI` 收集独立建议，再汇总为一份摘要供后续裁决使用。

## 仓库里当前有什么

当前公开文件主要是：

- `.codex/skills/peer-consult/SKILL.md`
- `.codex/skills/peer-consult/assets/request_template.md`
- `.codex/skills/peer-consult/scripts/peer_consult.py`
- `reference.md`
- `reference/skills/`

其中：

- `.codex/skills/peer-consult/` 是实际可安装、可运行的 Skill
- `reference.md` 是本仓库的设计参考说明
- `reference/skills/` 是参考材料与上游脚本，不是本仓库当前交付的运行入口

## `peer-consult` 做什么

根据 `.codex/skills/peer-consult/SKILL.md`，这个 Skill 的职责是：

- 在问题定位卡住时征询 `Claude Code` 和 `Gemini CLI`
- 汇总两侧输出的优缺点、候选方案和问题列表
- 由 Codex 继续做裁决与后续行动

它面向的典型场景包括：

- 连续两轮定位或修复仍无进展
- 需要在多个方案之间做取舍
- 任务涉及安全敏感面

## 依赖条件

仓库当前写明的依赖只有：

- `claude`
- `gemini`
- `python3`

见 `.codex/skills/peer-consult/SKILL.md:4`。

## 安装

推荐把 Skill 安装到用户级 Codex 目录：

```bash
mkdir -p ~/.codex/skills
cp -R .codex/skills/peer-consult ~/.codex/skills/
```

也可以直接从仓库里运行脚本：

```bash
python3 .codex/skills/peer-consult/scripts/peer_consult.py --help
```

## 使用方式

`peer-consult` 要求先准备问题摘要和上下文文件，再运行脚本。

示例：

```bash
python3 ~/.codex/skills/peer-consult/scripts/peer_consult.py \
  --question "pytest 中 test_login 失败：期望 302，实际 500" \
  --context-file docs/peer_consult/request.md
```

脚本约束如下：

- `--context-file` 必须位于目标项目的 `docs/peer_consult/` 下
- 不允许直接通过 `--extra` 传大段内容
- `--include-diff` 和 `--include-status` 已禁用

这些行为由 `.codex/skills/peer-consult/scripts/peer_consult.py` 明确实现。

## 输出

脚本会把输出写到目标项目的本地工作区：

```text
docs/peer_consult/
```

正常情况下生成一份 Markdown 摘要文件；文件名基于时间戳和问题摘要 slug。

当任一侧调用失败、解析失败，或显式传入 `--save-raw` 时，还会写入：

```text
docs/peer_consult/raw/
```

原始输出默认不会保存。

## 边界

这个 Skill 当前明确的边界是：

- 只采集意见，不直接改代码
- 只读取 `docs/peer_consult/` 下的上下文文件
- 不自动读取 `git diff/status`
- 要求上下文先脱敏再提供

这些约束写在 `.codex/skills/peer-consult/SKILL.md` 和 `.codex/skills/peer-consult/scripts/peer_consult.py` 里。

## 仓库结构

```text
.codex/skills/peer-consult/
  SKILL.md
  assets/request_template.md
  scripts/peer_consult.py
reference.md
reference/skills/
.gitignore
README.md
```

## 本地工作区说明

根 `.gitignore` 当前忽略了：

- `docs/`
- `evidence/`

这意味着运行产生的工作区和本地审计记录默认不作为仓库公开内容的一部分。

## 参考

如果你想看这个 Skill 的设计来源，可以再读：

- `reference.md`
- `reference/skills/README.md`
