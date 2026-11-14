#!/usr/bin/env python3
"""Antigravity PreInvocation 收件钩子：把 Codex 工人的未读提问 / 报告塞进主会话。

为什么挂在 PreInvocation：
  1. 主会话闲着等通知时，`codex_msg.py wait <频道>`（由 run_command 挂后台）一退出就会自动唤醒主会话；
  2. 主会话正忙着连续做别的步骤、或用户刚发来一句话时，PreInvocation 会在调模型前把各活频道里的
     未读提问与进度报告通过 `injectSteps` 注入上下文，无需打断或拒绝任何工具调用。

契约（见 Antigravity Lifecycle Hooks 文档）：
  - 输入 stdin JSON 使用 camelCase：`conversationId`、`workspacePaths` 等。
  - 钩子进程的当前目录是包含 `hooks.json` 的插件目录，因此必须从 `workspacePaths`（或测试传入的
    `CODEX_MSG_ROOT` / `cwd`）定位项目根，绝不能误扫插件自身的 `.git`。
  - 无未读消息或发生任何异常时一律输出 `{}` 并以退出码 0 结束（fail-open，零额外 token）。
  - 有未读消息时输出 `{"injectSteps": [{"systemMessage": {"systemMessage": "..."}}]}`。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
PLUGIN_DIR = HERE.parent.parent.parent
PYX = Path(sys.executable).as_posix() if sys.executable else "python3"
SKILL_TOOL = (HERE / "codex_msg.py").as_posix()

STALE_SEC = 24 * 3600     # live 还在、发件箱却 24h 没动 = 崩掉没关的死频道
ASK_RENAG = 180.0         # 未答提问隔 3 分钟再提醒一次
ASK_RENAG_UNTIL = 1200.0  # 首次送达 20 分钟后不再催（ask 默认 900s 已超时自便）
MAX_ITEMS = 6
MAX_TEXT = 600
LEDGER_KEEP_IDS = 200
LEDGER_KEEP_SEC = 7 * 24 * 3600


def parse_workspace_path(raw: str) -> Path | None:
    if not raw:
        return None
    s = str(raw).strip()
    if s.startswith("file://"):
        parsed = urlparse(s)
        path_part = unquote(parsed.path or "")
        if os.name == "nt" and path_part.startswith("/") and len(path_part) >= 3 and path_part[2] == ":":
            path_part = path_part[1:]
        s = path_part
    try:
        return Path(s).resolve()
    except Exception:
        return None


def find_root(start: Path) -> Path | None:
    try:
        cur = start.resolve()
    except Exception:
        return None
    for cand in [cur, *cur.parents]:
        try:
            if (cand / ".git").exists():
                return cand
        except Exception:
            continue
    return None


def is_inside_plugin(path: Path) -> bool:
    try:
        p = path.resolve()
        plug = Path(os.environ.get("PLUGIN_ROOT") or PLUGIN_DIR).resolve()
        return p == plug or plug in p.parents
    except Exception:
        return False


def candidate_roots(payload: dict) -> list[Path]:
    raw_candidates: list[Path] = []
    env_root = os.environ.get("CODEX_MSG_ROOT")
    if env_root:
        p = parse_workspace_path(env_root)
        if p:
            raw_candidates.append(p)

    ws_paths = payload.get("workspacePaths")
    if isinstance(ws_paths, list):
        for item in ws_paths:
            p = parse_workspace_path(item)
            if p:
                raw_candidates.append(p)

    cwd_field = payload.get("cwd")
    if cwd_field:
        p = parse_workspace_path(cwd_field)
        if p:
            raw_candidates.append(p)

    if not raw_candidates:
        try:
            cwd_now = Path.cwd().resolve()
            if not is_inside_plugin(cwd_now):
                raw_candidates.append(cwd_now)
        except Exception:
            pass

    roots: list[Path] = []
    seen: set[str] = set()
    for p in raw_candidates:
        r = find_root(p) or p
        if is_inside_plugin(r):
            continue
        key = str(r)
        if key not in seen:
            seen.add(key)
            roots.append(r)
    return roots


def load_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def read_rows(path: Path) -> list:
    if not path.is_file():
        return []
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except Exception:
        return []
    return rows


def clip(text: str) -> str:
    text = str(text).replace("\r", "")
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + " …（截断）"


def session_key(payload: dict) -> str:
    cid = str(payload.get("conversationId") or payload.get("session_id") or "default")
    aid = str(payload.get("agentId") or payload.get("agent_id") or "")
    return f"{cid}/{aid}"


def scan(registry_path: Path, ledger_ch: dict, now_ts: float) -> tuple[list, bool]:
    reg = load_json(registry_path, None)
    if not isinstance(reg, dict) or not reg:
        return [], False
    hits = []
    dirty = False
    for ch, info in reg.items():
        try:
            chdir_str = (info or {}).get("dir")
            if not chdir_str:
                continue
            chdir = Path(chdir_str)
            if not (chdir / "live").exists():
                continue
            outbox = chdir / "outbox.jsonl"
            if not outbox.is_file():
                continue
            mtime = outbox.stat().st_mtime
            if now_ts - mtime > STALE_SEC:
                continue
            book = ledger_ch.setdefault(ch, {})
            ids = book.setdefault("ids", {})
            if book.get("mt") == mtime and now_ts < book.get("next", 0.0):
                continue
            rows = read_rows(outbox)
            seen = set()
            answered = set()
            for r in rows:
                if r.get("kind") == "seen":
                    seen.add(r.get("of"))
                elif r.get("kind") in ("answer", "expired"):
                    answered.add(r.get("of"))
            next_due = 0.0
            for r in rows:
                kind, rid = r.get("kind"), r.get("id")
                if not rid:
                    continue
                if kind == "ask" and not r.get("answer") and rid not in answered:
                    stamp = ids.get(rid)
                    if stamp is None:
                        ids[rid] = [now_ts, now_ts]
                        dirty = True
                        hits.append((ch, r, True))
                    elif (now_ts - stamp[1] >= ASK_RENAG
                          and now_ts - stamp[0] <= ASK_RENAG_UNTIL):
                        stamp[1] = now_ts
                        dirty = True
                        hits.append((ch, r, True))
                    first = ids[rid][0]
                    if now_ts - first <= ASK_RENAG_UNTIL:
                        due = ids[rid][1] + ASK_RENAG
                        next_due = due if next_due == 0.0 else min(next_due, due)
                elif kind == "say" and rid not in seen and rid not in ids:
                    ids[rid] = [now_ts, now_ts]
                    dirty = True
                    hits.append((ch, r, False))
            if book.get("mt") != mtime or book.get("next", 0.0) != next_due:
                book["mt"] = mtime
                book["next"] = next_due
                dirty = True
        except Exception:
            continue
    return hits, dirty


def prune(ledger: dict, now_ts: float) -> None:
    for key in list(ledger.keys()):
        sess = ledger.get(key) or {}
        if now_ts - float(sess.get("ts") or 0) > LEDGER_KEEP_SEC:
            del ledger[key]
            continue
        for ch, book in list((sess.get("ch") or {}).items()):
            ids = book.get("ids") or {}
            if len(ids) > LEDGER_KEEP_IDS:
                keep = sorted(ids.items(), key=lambda kv: kv[1][0])[-LEDGER_KEEP_IDS:]
                book["ids"] = dict(keep)


def render(all_hits: list[tuple[Path, str, dict, bool]]) -> str:
    lines = ["【Codex 工人来话（非报错；仅由主会话处理 answer / send，子代理看到请忽略）】"]
    asked: list[tuple[Path, str]] = []
    for root, ch, row, is_ask in all_hits[:MAX_ITEMS]:
        if is_ask:
            asked.append((root, ch))
            lines.append(
                f"[{ch}] {row.get('at', '?')} 提问 {row.get('id', '?')}（工人原地阻塞等答复）：\n  {clip(row.get('text', ''))}"
            )
        else:
            lines.append(
                f"[{ch}] {row.get('at', '?')} 报告：\n  {clip(row.get('text', ''))}"
            )
    if len(all_hits) > MAX_ITEMS:
        root0 = all_hits[0][0].as_posix()
        lines.append(f"（还有 {len(all_hits) - MAX_ITEMS} 条，跑 \"{PYX}\" \"{SKILL_TOOL}\" --root \"{root0}\" poll 查看）")
    seen_ch: set[str] = set()
    for root, ch in asked:
        if ch in seen_ch:
            continue
        seen_ch.add(ch)
        lines.append(
            f"→ 答复工人（2 秒内送达）：\"{PYX}\" \"{SKILL_TOOL}\" --root \"{root.as_posix()}\" answer {ch} \"你的答复\""
        )
    return "\n\n".join(lines)


def build() -> dict:
    if os.environ.get("CODEX_MSG_CH") or os.environ.get("CLAUDE_MSG_CH"):
        return {}
    raw = sys.stdin.buffer.read().decode("utf-8-sig") if not sys.stdin.isatty() else ""
    payload = json.loads(raw or "{}")
    if not isinstance(payload, dict):
        return {}

    roots = candidate_roots(payload)
    if not roots:
        return {}

    now_ts = time.time()
    key = session_key(payload)
    all_hits: list[tuple[Path, str, dict, bool]] = []

    for root in roots:
        msgroot = root / ".harness-tmp" / "codex-msg"
        if not msgroot.is_dir():
            continue
        registry_path = msgroot / "registry.json"
        ledger_path = msgroot / "hook-delivered.json"
        ledger = load_json(ledger_path, {})
        if not isinstance(ledger, dict):
            ledger = {}
        sess = ledger.setdefault(key, {})
        sess["ts"] = now_ts
        hits, dirty = scan(registry_path, sess.setdefault("ch", {}), now_ts)
        if dirty or hits:
            prune(ledger, now_ts)
            tmp = ledger_path.with_suffix(".json.tmp")
            try:
                tmp.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
                tmp.replace(ledger_path)
            except Exception:
                pass
        for ch, row, is_ask in hits:
            all_hits.append((root, ch, row, is_ask))

    if not all_hits:
        return {}
    return {
        "injectSteps": [
            {
                "systemMessage": {
                    "systemMessage": render(all_hits)
                }
            }
        ]
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    out = {}
    try:
        out = build()
    except Exception:
        out = {}
    try:
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    except Exception:
        sys.stdout.write("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
