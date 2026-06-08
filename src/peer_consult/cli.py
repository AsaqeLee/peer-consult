import argparse

def parse_args():
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
    return ap.parse_args()
