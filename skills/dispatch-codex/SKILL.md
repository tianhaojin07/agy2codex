---
name: dispatch-codex
description: >-
  将明确的代码实现、实验运行、数据处理、资料检索、设定与格式核对等任务派发给本机无头 Codex CLI 子代理（agy2codex），
  支持运行途中双向通信（捎话、提问阻塞答复与后台自动唤醒）。当用户要求「派 codex」「用 agy2codex」或项目规则要求将代码与重度核对委派给子代理时激活。
---

# 派遣 Codex CLI 作为无头子代理（`agy2codex`）

主会话负责全局方向、架构与故事判断、任务拆解与最终验收；Codex 工人负责按明确 brief 编写实验/业务代码、跑脚本验证、检索一手资料或执行规则明确的核对。工人的产出视为待审初稿，主会话必须核对 `git diff`、日志或原文引用后再采纳。

脚本目录固定在插件内：`~/.gemini/config/plugins/agy2codex/skills/dispatch-codex/scripts`。

## 1. 写 brief（简短明确）

在当前仓库的 `.harness-tmp/briefs/<name>.md` 写明四项即可（项目通用规则已在仓库 `AGENTS.md` 中，无需重复抄写）：
1. **目标**：要解决的具体问题或要产出的报告。
2. **输入与边界**：必读文件路径、允许修改的文件范围（只读检索或核对任务写明「不改任何项目文件，只输出报告」）。
3. **输出位置与格式**：代码路径或报告路径（如 `.harness-tmp/reports/<name>.md`）。
4. **完成判据**：必须跑通的测试命令、指标核验或检查项。

确保仓库已将 `/.harness-tmp/` 与 `/.codex/hooks.json*` 加入 `.git/info/exclude` 或 `.gitignore`，绝不提交临时文件。

## 2. 派单与后台唤醒（无需轮询）

使用 `run_command` 启动派单，将 **`WaitMsBeforeAsync` 设为 `2000`**。派单脚本会在 1 秒内向 stderr 打印 `CHANNEL=<频道>` 并自动转入后台运行；工人收工退出时，Antigravity 会自动唤醒主会话并送达最终答复与 `SESSION=<id>`。

- **Linux / macOS**：
  ```bash
  S="$HOME/.gemini/config/plugins/agy2codex/skills/dispatch-codex/scripts"
  bash "$S/codex_task.sh" -f .harness-tmp/briefs/<name>.md --tag <name>
  ```
- **Windows（`run_command` 默认 `pwsh`，通过 Git Bash 调 `.sh`）**：
  ```powershell
  & "D:/Scoop/apps/git/current/bin/bash.exe" -lc 'S="$HOME/.gemini/config/plugins/agy2codex/skills/dispatch-codex/scripts"; bash "$S/codex_task.sh" -f .harness-tmp/briefs/<name>.md --tag <name>'
  ```

常用参数：
- `-m <model>` / `-e <effort>`：覆盖模型与思考档位（不传则沿用 `~/.codex/config.toml` 默认配置；机械核对可传 `-e medium` 省额度，复杂实现传 `-e high`）。
- `--ro`：严格只读沙箱（注意 `--ro` 下工人无法写发件箱 `ask` 提问，仅单向接收；需要双向问答时保持默认 `workspace-write` 并在 brief 中约束写入范围）。
- `--net`：放开沙箱内命令联网（默认断网）。
- `--search`：开启 Codex 原生网页搜索（默认关闭）。
- `-i <img_path>`：附带图片输入（可重复）。
- `-C <dir>`：指定独立 `git worktree` 目录（多工人并行改不同模块时使用）。

## 3. 运行中双向对讲

拿到 `CHANNEL=<频道>` 后，顺手用 `run_command`（设 **`WaitMsBeforeAsync: 500`**）挂一个后台守候器，然后若无其他并行工作即可结束当前回合等待唤醒，**绝不写循环轮询**：

```bash
M="$HOME/.gemini/config/plugins/agy2codex/skills/dispatch-codex/scripts/codex_msg.py"
python3 "$M" wait <频道>                  # 守候器：工人一提问/报告/收工即退出并自动唤醒主会话
python3 "$M" send <频道> "补充要求"        # 捎话：工人执行下一条命令前收到（加 --stop 则回话前挂住）
python3 "$M" poll <频道>                  # 查看未读提问与报告
python3 "$M" answer <频道> "你的答复"      # 答复工人提问（工人 2 秒内收到并在同一轮继续）
```

（Windows 下若在 `pwsh` 直接跑对讲命令，把 `python3 "$M"` 写成 `python -X utf8 "$env:USERPROFILE/.gemini/config/plugins/agy2codex/skills/dispatch-codex/scripts/codex_msg.py"` 即可。）

`wait` 退出码含义：
- `0`：工人调用了 `ask`，正原地阻塞等答复（若涉及需要用户拍板的设计或创作取舍，先问用户拿到结论后再 `answer`；技术细节主会话可直接答复，答完再挂一个 `wait`）。
- `10`：工人发来阶段性 `say` 报告，仍在继续工作（需继续守候则再挂一个 `wait`）。
- `20`：工人已正常收工关闭频道。
- `30`：守候超时，工人仍在运行。
- `40`：频道不存在（检查名字或派单日志）。

若主会话正在连续调用其他工具，`agy2codex` 插件自带的 `PreInvocation` 钩子也会在下一轮模型调用前自动注入工人的未读提问与报告。

## 4. 追问返工与安全铁律

1. **严禁 `--resume --last`**：交互式 Codex 共用同一会话库，`--last` 会劫持用户的活会话（脚本已硬拦截）。返工必须传派单结束时打印的显式 `SESSION=<id>` 且重传 `-m <model>`：
   ```bash
   bash "$S/codex_task.sh" --resume <session-id> -m <model> -p "返工说明"
   ```
2. **禁止静默 `--full`**：除非用户当面明确要求放开全盘权限，绝不传 `--full`。
3. **收单必查**：检查 `git status`、`git diff` 与测试输出，确认无越界改动后再汇报或提交。
