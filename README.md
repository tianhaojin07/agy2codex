# agy2codex

Dispatch your locally authenticated OpenAI Codex CLI as a headless subagent from Google Antigravity (`agy`), complete with live two-way intercom, blocking worker questions, and zero-polling reactive wakeup.

[中文文档](./README.zh-CN.md)

## Overview

`agy2codex` packages the `claude2codex` file-mailbox intercom as a native Antigravity plugin (`~/.gemini/config/plugins/agy2codex`):

1. **Idle Reactive Wakeup**: Start `codex_task.sh` via `run_command` (`WaitMsBeforeAsync=2000`), then start `codex_msg.py wait <channel>` (`WaitMsBeforeAsync=500`). As soon as the Codex worker asks a question, posts a progress note, or finishes, the background watcher exits and Antigravity automatically wakes the main session.
2. **Busy-Turn Delivery (`PreInvocation` Hook)**: While the main session is actively running other steps, `agy_inbox_hook.py` checks active workspace channels before each model invocation and injects unread worker questions or reports via `injectSteps` (returning `{}` with zero token overhead when idle).

## Requirements

- Python 3.9+
- Bash (built-in on Linux/macOS; Git Bash on Windows)
- Authenticated Codex CLI (`codex login`), installed via `@openai/codex` (`PATH`, nvm, volta, conda) or bundled with the Windows Codex desktop app (`CODEX_CLI_PATH` in `~/.codex/config.toml` / `WindowsApps`).

## Installation

```bash
git clone https://github.com/tianhaojin07/agy2codex.git agy2codex
cd agy2codex
python3 install.py
```

On Windows PowerShell, run `python -X utf8 install.py`. Antigravity discovers `~/.gemini/config/plugins/agy2codex` immediately without restarting.

```bash
python3 install.py --check      # Verify installation and resolved Codex binary
python3 install.py --uninstall  # Remove installed plugin directory
```

## Running Tests

```bash
python3 -m unittest discover -s tests -v
```

## Credits & License

Adapted for Google Antigravity from [Napoleoncqf/claude2codex](https://github.com/Napoleoncqf/claude2codex) under the [MIT License](./LICENSE).
