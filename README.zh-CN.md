# agy2codex

将本机已登录的 OpenAI Codex CLI 作为 Google Antigravity（`agy`）的无头子代理调用，支持运行途中双向对讲、提问阻塞答复与后台自动唤醒。

[English](./README.md)

## 设计背景

在 Antigravity 中直接处理重度科研实验或批量文本检索时，内置子代理和 Swarm 往往面临模型版本受限或上下文共享导致的高额消耗。`agy2codex` 以原生 Antigravity 插件的形式把执行层交给官方 `codex exec`，保留 `Napoleoncqf/claude2codex` 的文件信箱双向通信机制，并适配 Antigravity 的两套唤醒路径：

1. **空闲自动唤醒**：主会话用 `run_command`（`WaitMsBeforeAsync=2000`）启动 `codex_task.sh`，再以 `WaitMsBeforeAsync=500` 挂起 `codex_msg.py wait <频道>`。工人一旦提问、阶段汇报或收工，后台进程退出，Antigravity 立即唤醒主会话，无需轮询。
2. **忙碌即时收件**：插件自带 `PreInvocation` 钩子（`agy_inbox_hook.py`）。主会话连续执行其他步骤时，钩子会在每次模型调用前扫描当前工作区的活频道，通过 `injectSteps` 注入未读提问与报告；无未读消息时仅返回 `{}`，不额外占用上下文。

## 环境要求

- Python 3.9+
- Bash（Linux / macOS 自带；Windows 使用 Git Bash）
- 已登录的 Codex CLI（`codex login`）：支持全局 `npm i -g @openai/codex`、用户目录安装（nvm / volta / conda），以及 Windows 商店版 Codex 桌面端内置 CLI（自动读取 `~/.codex/config.toml` 的 `CODEX_CLI_PATH` 或扫描 `WindowsApps`）。

## 安装与自检

克隆仓库后运行安装脚本，插件会部署到 `~/.gemini/config/plugins/agy2codex` 并自动被 Antigravity 发现（无需重启 IDE）：

```bash
git clone https://github.com/tianhaojin07/agy2codex.git agy2codex
cd agy2codex
python3 install.py
```

Windows PowerShell 下可直接执行 `python -X utf8 install.py`。常用维护命令：

| 命令 | 作用 |
| --- | --- |
| `python3 install.py` | 安装或更新插件、转换 `.sh` 为 LF 换行、检测可用 Python 与 Codex CLI |
| `python3 install.py --check` | 检查插件安装状态与当前解析到的 Codex CLI 路径 |
| `python3 install.py --uninstall` | 移除 `~/.gemini/config/plugins/agy2codex` |

## 目录结构

```text
agy2codex/
├── plugin.json                              # Antigravity 插件清单
├── hooks.json                               # PreInvocation 收件钩子配置
├── install.py                               # 跨平台安装与自检脚本
├── skills/
│   └── dispatch-codex/
│       ├── SKILL.md                         # Antigravity 派单与对讲技能说明
│       └── scripts/
│           ├── codex_task.sh                # 无头派单、看门狗与满载自动续跑
│           ├── codex_msg.py                 # 双向文件信箱与 Codex PreToolUse 钩子
│           ├── agy_inbox_hook.py            # Antigravity PreInvocation 收件钩子
│           └── resolve_codex.py             # 跨平台定位 Codex CLI 可执行文件
└── tests/                                   # 单元测试套件
```

## 基本用法

激活 `dispatch-codex` 技能后，Antigravity 主会话按四步协作：

1. 在项目 `.harness-tmp/briefs/<name>.md` 写明任务目标、输入边界、输出路径与验收命令（把 `/.harness-tmp/` 与 `/.codex/hooks.json*` 加入 `.git/info/exclude`）。
2. 通过 `run_command`（`WaitMsBeforeAsync=2000`）启动 `codex_task.sh`，从 stderr 拿到 `CHANNEL=<频道>`。
3. 通过 `run_command`（`WaitMsBeforeAsync=500`）挂起 `codex_msg.py wait <频道>` 守候唤醒；中途可用 `send` 捎话、用 `answer` 答复工人提问。
4. 工人收工后核对 `git status`、`git diff` 与测试结果，如需返工则传入显式 `--resume <session-id> -m <model>`（脚本硬拦截 `--resume --last`，防止误接交互式会话）。

## 运行测试

```bash
python3 -m unittest discover -s tests -v
```

Windows 下通过 Git Bash 运行测试以覆盖 `codex_task.sh`：

```powershell
& "D:/Scoop/apps/git/current/bin/bash.exe" -lc 'python -X utf8 -m unittest discover -s tests -v'
```

## 致谢与许可

本项目基于 [Napoleoncqf/claude2codex](https://github.com/Napoleoncqf/claude2codex) 改造适配至 Google Antigravity，遵循 [MIT License](./LICENSE)。
