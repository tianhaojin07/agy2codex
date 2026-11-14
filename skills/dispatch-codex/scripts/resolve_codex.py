#!/usr/bin/env python3
"""跨平台定位 Codex CLI 可执行文件（Linux / macOS / Windows）。

查找顺序：
1. 环境变量 CODEX_TASK_BIN（显式指定，最高优先）
2. 技能目录内固定的 codex-cli/node_modules/.bin/codex
3. 环境变量 CODEX_CLI_PATH
4. 当前 PATH 中的 codex
5. Unix 常见用户级安装位置（防止非登录 shell 漏加载 nvm / npm-global / local/bin）
6. Windows Codex 桌面端内置 CLI（读取 ~/.codex/config.toml 的 CODEX_CLI_PATH，或扫描 WindowsApps / AppData）
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path


def is_usable(path: Path) -> bool:
    try:
        return path.is_file() and (sys.platform == "win32" or os.access(path, os.X_OK))
    except OSError:
        return False


def newest(paths: list[Path]) -> Path | None:
    valid = [p for p in paths if is_usable(p)]
    if not valid:
        return None
    return max(valid, key=lambda p: p.stat().st_mtime_ns)


def from_codex_config(home: Path) -> Path | None:
    cfg = home / ".codex" / "config.toml"
    if not cfg.is_file():
        return None
    try:
        text = cfg.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    m = re.search(r'CODEX_CLI_PATH\s*=\s*[\'"]([^\'"]+)[\'"]', text)
    if m:
        cand = Path(m.group(1))
        if is_usable(cand):
            return cand
    return None


def resolve() -> Path:
    explicit = os.environ.get("CODEX_TASK_BIN")
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise SystemExit(f"CODEX_TASK_BIN does not point to a file: {explicit}")
        return p

    skill_root = Path(__file__).resolve().parent.parent
    bin_dir = skill_root / "codex-cli" / "node_modules" / ".bin"
    names = ("codex.cmd", "codex.exe", "codex") if sys.platform == "win32" else ("codex",)
    for name in names:
        pinned = bin_dir / name
        if is_usable(pinned):
            return pinned

    injected = os.environ.get("CODEX_CLI_PATH")
    if injected and is_usable(Path(injected)):
        return Path(injected)

    visible = shutil.which("codex")
    if visible:
        return Path(visible)

    home = Path.home()
    cfg_bin = from_codex_config(home)
    if cfg_bin:
        return cfg_bin

    if sys.platform == "win32":
        candidates: list[Path] = []
        win_apps = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "WindowsApps"
        if win_apps.exists():
            try:
                candidates.extend(win_apps.glob("OpenAI.Codex_*/app/resources/codex.exe"))
            except OSError:
                pass
        local_app = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        old_bin = local_app / "OpenAI" / "Codex" / "bin"
        if old_bin.exists():
            try:
                candidates.extend(old_bin.glob("*/codex.exe"))
            except OSError:
                pass
        hit = newest(candidates)
        if hit:
            return hit
        raise SystemExit("未找到 Codex CLI；请安装 @openai/codex、打开 Codex 桌面端或设置 CODEX_TASK_BIN")

    unix_fixed = [
        home / ".local" / "bin" / "codex",
        home / ".npm-global" / "bin" / "codex",
        home / ".volta" / "bin" / "codex",
        Path("/usr/local/bin/codex"),
        Path("/opt/homebrew/bin/codex"),
    ]
    for cand in unix_fixed:
        if is_usable(cand):
            return cand

    unix_globs: list[Path] = []
    for pattern in (
        ".nvm/versions/node/*/bin/codex",
        "miniconda3/bin/codex",
        "anaconda3/bin/codex",
        "miniforge3/bin/codex",
    ):
        try:
            unix_globs.extend(home.glob(pattern))
        except OSError:
            pass
    hit = newest(unix_globs)
    if hit:
        return hit

    raise SystemExit("codex: command not found (install @openai/codex or set CODEX_TASK_BIN)")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = resolve()
    print(p.as_posix() if sys.platform == "win32" else str(p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
