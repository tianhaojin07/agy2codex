#!/usr/bin/env python3
"""将 agy2codex 安装 / 更新到 ~/.gemini/config/plugins/agy2codex（兼容 Linux / macOS / Windows）。

用法：
    python3 install.py              # 安装或更新全局插件，并自检 Codex CLI
    python3 install.py --check      # 仅检查当前安装状态与 Codex CLI 路径
    python3 install.py --uninstall  # 移除已安装的插件目录（不触碰 ~/.gemini/config/config.json）
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
PLUGIN_NAME = "agy2codex"
TARGET_DIR = Path.home() / ".gemini" / "config" / "plugins" / PLUGIN_NAME

COPY_FILES = ("plugin.json", "hooks.json", "README.md", "README.zh-CN.md", "LICENSE")
COPY_DIRS = ("skills",)


def pick_hook_command() -> str:
    rel_script = "skills/dispatch-codex/scripts/agy_inbox_hook.py"
    if sys.executable and Path(sys.executable).is_file():
        py = Path(sys.executable).as_posix()
        py_tok = f'"{py}"' if " " in py else py
        return f"{py_tok} -X utf8 {rel_script}"
    for cand in ("python3", "python"):
        if shutil.which(cand):
            return f"{cand} -X utf8 {rel_script}"
    return f"python3 -X utf8 {rel_script}"


def check_codex_bin(plugin_dir: Path) -> tuple[bool, str]:
    resolver = plugin_dir / "skills" / "dispatch-codex" / "scripts" / "resolve_codex.py"
    if not resolver.is_file():
        return False, f"缺少 {resolver}"
    r = subprocess.run([sys.executable, "-X", "utf8", str(resolver)], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()
    return True, r.stdout.strip()


def do_install() -> int:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    for fn in COPY_FILES:
        src = REPO / fn
        if src.is_file():
            shutil.copy2(src, TARGET_DIR / fn)

    for dn in COPY_DIRS:
        src = REPO / dn
        dst = TARGET_DIR / dn
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    # 确保 shell 脚本在 Unix 下具备可执行权限，且为 LF 换行
    for sh_file in (TARGET_DIR / "skills").rglob("*.sh"):
        data = sh_file.read_bytes().replace(b"\r\n", b"\n")
        sh_file.write_bytes(data)
        try:
            sh_file.chmod(0o755)
        except OSError:
            pass

    # 若当前机器的默认 shell 下没有 python3，则自动将 hooks.json 里的命令固定为可用解释器
    hooks_path = TARGET_DIR / "hooks.json"
    hook_cmd = pick_hook_command()
    hooks_doc = {
        "codex-inbox": {
            "PreInvocation": [
                {
                    "type": "command",
                    "command": hook_cmd,
                    "timeout": 10,
                }
            ]
        }
    }
    hooks_path.write_text(json.dumps(hooks_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ok, info = check_codex_bin(TARGET_DIR)
    print(f"[agy2codex] 已安装至: {TARGET_DIR}")
    print(f"[agy2codex] 收件钩子命令: {hook_cmd}")
    if ok:
        print(f"[agy2codex] Codex CLI 已就绪: {info}")
    else:
        print(f"[agy2codex] 提示 - 当前尚未定位到 Codex CLI: {info}", file=sys.stderr)
    return 0


def do_check() -> int:
    print(f"[agy2codex] 目标目录: {TARGET_DIR} ({'已存在' if TARGET_DIR.is_dir() else '未安装'})")
    probe_dir = TARGET_DIR if TARGET_DIR.is_dir() else REPO
    ok, info = check_codex_bin(probe_dir)
    print(f"[agy2codex] Codex CLI: {info}" if ok else f"[agy2codex] Codex CLI 未找到: {info}")
    return 0 if (TARGET_DIR.is_dir() and ok) else 1


def do_uninstall() -> int:
    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)
        print(f"[agy2codex] 已移除: {TARGET_DIR}")
    else:
        print(f"[agy2codex] 未发现已安装目录: {TARGET_DIR}")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Install or manage the agy2codex Antigravity plugin.")
    parser.add_argument("--check", action="store_true", help="Check installation and Codex CLI resolution")
    parser.add_argument("--uninstall", action="store_true", help="Remove installed plugin files")
    args = parser.parse_args()
    if args.uninstall:
        return do_uninstall()
    if args.check:
        return do_check()
    return do_install()


if __name__ == "__main__":
    raise SystemExit(main())
