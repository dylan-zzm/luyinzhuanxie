#!/usr/bin/env python3
"""管理“方案生成 prompt”的版本。

    python scripts/prompt_admin.py status            # 查看当前 prompt 是否已设置、版本号
    python scripts/prompt_admin.py set <文件>         # 用文件内容替换当前 prompt（旧版自动归档）
    python scripts/prompt_admin.py set -              # 从标准输入读取新 prompt
    python scripts/prompt_admin.py history           # 列出历史版本

当前生效的 prompt 永远是 prompts/plan_prompt.md；历史版本在 prompts/history/。
"""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRENT = ROOT / "prompts" / "plan_prompt.md"
HISTORY = ROOT / "prompts" / "history"
NOT_SET_MARKER = "<!-- PROMPT_NOT_SET -->"
VERSION_PREFIX = "<!-- version: "


def read_version(text):
    first = text.splitlines()[0] if text else ""
    if first.startswith(VERSION_PREFIX):
        return first[len(VERSION_PREFIX):].rstrip(" ->")
    return None


def is_set():
    return CURRENT.exists() and NOT_SET_MARKER not in CURRENT.read_text(encoding="utf-8")


def status():
    if not is_set():
        print("NOT_SET：还没有设置方案 prompt。请让使用者粘贴最新版 prompt，再运行 set。")
        return 1
    text = CURRENT.read_text(encoding="utf-8")
    print(f"OK：当前 prompt 版本 {read_version(text) or '未知'}，{len(text)} 字符，文件 {CURRENT.relative_to(ROOT)}")
    return 0


def set_prompt(src):
    new = sys.stdin.read() if src == "-" else Path(src).read_text(encoding="utf-8")
    new = new.strip()
    if not new:
        sys.exit("新 prompt 为空，未做修改。")
    if read_version(new):  # 去掉粘贴内容里可能带的旧版本头
        new = "\n".join(new.splitlines()[1:]).strip()

    HISTORY.mkdir(parents=True, exist_ok=True)
    if is_set():
        old = CURRENT.read_text(encoding="utf-8")
        archived = HISTORY / f"{read_version(old) or 'unknown'}.md"
        archived.write_text(old, encoding="utf-8")
        print(f"旧版已归档到 {archived.relative_to(ROOT)}")

    version = datetime.now().strftime("v%Y%m%d-%H%M%S")
    CURRENT.write_text(f"{VERSION_PREFIX}{version} -->\n\n{new}\n", encoding="utf-8")
    print(f"已更新 prompt → {version}（{len(new)} 字符）")


def history():
    files = sorted(HISTORY.glob("*.md"))
    if not files:
        print("暂无历史版本")
    for f in files:
        print(f.relative_to(ROOT))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in {"status", "set", "history"}:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "status":
        sys.exit(status())
    if cmd == "set":
        if len(sys.argv) < 3:
            sys.exit("用法：prompt_admin.py set <文件|->")
        set_prompt(sys.argv[2])
    else:
        history()
