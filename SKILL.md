---
name: dispatch-codex
description: 用户说「派 codex」「让 codex 做 X」「让 codex OCR / 识别图里的字」「让 codex 生图」或 "delegate this to codex" 时用。分工：Codex 只接最基础、最不容易出错的活——OCR / 读图转写、生图、规则写死的批量机械活；规划和执行由 Claude 自己做，复审交 Kimi（dispatch-kimi）。把本机 Codex CLI 当无头 subagent 派活，并支持运行中双向对讲（捎话 / 反问 / 唤醒）。
---

# 派遣 Codex 当 subagent

分工：**Codex 只接最基础、最不容易出错的活**。规划和动手是我（Claude）自己的事，复审交 Kimi（dispatch-kimi）。
派给 Codex 的活要满足：输入明确、做法唯一、结果能被我一眼核对。

| 活 | 怎么派 | 收货 |
|---|---|---|
| **OCR / 读图转写**（截图、扫描件、表格图转文字或 Markdown） | `-i <图>`（可重复）+ brief 写清输出格式和落盘路径 | 抽几处和原图对照；数字、专名逐个核 |
| **生图**（单张或小批量） | 默认沙箱即可；brief 写清尺寸、风格、张数、每张的用途 | 图在 `~/.codex/generated_images/<SESSION>/`（目录名 = 派单 stderr 的 `SESSION=`），我拷进项目、逐张看过再用 |
| **规则写死的批量机械活**（格式转换、批量改名、按模板填充） | brief 写规则 + 完成判据 | `git diff` + 抽查 |

不派给 Codex：要取舍的设计、改业务逻辑、找 bug、写需要判断的文档。
一套图统一画风重出、原图切件补全这类大批生图单，走 dispatch-web-astra（网页版按次计费，不耗 Codex 额度）。

流程 = 写 brief → 派单 → 收尾消息 → 按 session id 追问/返工 → **我按上表收货**。
工人的产出是未审草稿，和对待自己 subagent 的报告同一怀疑度。

## 派单

```bash
S=~/.claude/skills/dispatch-codex/scripts
# 写 brief 文件派（主用法；用 Bash run_in_background:true，别前台干等）
bash $S/codex_task.sh -f .harness-tmp/brief-<name>.md --tag <name>
bash $S/codex_task.sh -i shot1.png -i shot2.png -p "两张图里的表格转成 Markdown，写进 out/table.md" --tag ocr
# 短任务内联：-p "..."。stdout = 最终答复；stderr 一行 SESSION=<id> LOG=<path> EXIT=<rc>
# 追问/返工（必须显式 session id，且重传 -m）：
bash $S/codex_task.sh --resume <session-id> -m <model> -p "第三张图第 2 行的数字转错了，重转。"
```

常用开关：`--ro` 只读沙箱 · `--net` 沙箱内放开网络 · `--nosearch` 关 web 检索 · `--full` 不沙箱（仅用户明说时）·
`--add-dir <d>` 多一个可写目录 · `-i <图>` 附图 · `-m <model>` · `-e <effort>`（默认 xhigh）·
`-C <dir>` 指到独立 git worktree 并行派单 · `--no-channel` 不开对讲。完整列表：`bash $S/codex_task.sh --help`。
这类基础活用不着 xhigh，可以 `-e medium` 省额度。

## 对讲（派单自动开频道）

无头工人一开跑就没有输入口，所以每次派单自动开一条频道，stderr 打 `CHANNEL=<频道>` 和 `WAKEUP=<频道>`。

```bash
M="$HOME/.claude/skills/dispatch-codex/scripts/codex_msg.py"   # 调用写 python3 "$M"：bash 与 zsh 都认
python3 "$M" send <频道> "改主意了：数到 4 就停"   # 捎话：工人下一条命令前送到（加 --stop = 回话前把它挂住）
python3 "$M" poll <频道>                           # 看工人问了什么 / 报了什么
python3 "$M" answer <频道> "答复"                  # 答它：工人 2 秒内拿到，在同一个回合里接着干
python3 "$M" wait <频道>                           # 守候器：挂 Bash run_in_background，工人一出声就叫醒我
```

派完单后**顺手挂一个 `wait`**；它退出时看退出码：0 = 工人在等答复（赶紧 answer）/ 10 = 只有报告 /
20 = 收工 / 30 = 超时 / 40 = 没这频道。`wait` 要**裸跑，别套管道**（套了就看不到真退出码）。
答完再挂一个。

Claude 侧的收件钩子（见 README 安装第 4 步）会在我每次调工具前，把未读提问 / 报告塞进上下文，所以埋头干活时也看得见。

## brief 写法（≤15 行）

只写：**目标 + 输入（图 / 文件路径）+ 输出格式和落盘路径 + 完成判据**。项目规矩放项目根 `AGENTS.md`（codex 自动读），不进 brief。
白名单不相交的两单可同 worktree 并行；工人在跑时我只读不写，要并行改就给它开独立 worktree。

## 铁则

1. **绝不 `resume --last`**——用户的交互 codex 客户端共用会话存储，`--last` 会接进他的活会话。脚本对它硬拒。
2. **收单后必核**：按上面的收货栏核对，才并进结论。
3. 联网/采集类 brief 末尾写死一行：「全程后台干活；禁用真实浏览器 / computer-use 等会动用户桌面或弹权限窗的东西」。
4. 把 `.harness-tmp/` 加进该项目 `.gitignore`（日志 / brief / 频道都落这儿，别提交）。
