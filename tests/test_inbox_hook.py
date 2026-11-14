"""Antigravity PreInvocation 收件钩子回归测试。

运行：python3 -m unittest discover -s tests
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "skills" / "dispatch-codex" / "scripts"


class InboxHook(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / ".git").mkdir()
        self.msg = [sys.executable, str(SCRIPTS / "codex_msg.py"), "--root", str(self.root)]
        subprocess.run([*self.msg, "register", "c", str(self.root)], capture_output=True, check=True)
        subprocess.run([*self.msg, "say", "c", "codex 工人的报告"], capture_output=True, check=True,
                       cwd=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def hook(self, payload_dict=None, cwd=None, **extra_env) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_MSG_CH", "CODEX_MSG_CH", "CODEX_MSG_ROOT")}
        env.update(extra_env)
        if payload_dict is None:
            payload_dict = {
                "conversationId": "conv-main",
                "workspacePaths": [str(self.root)],
            }
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "agy_inbox_hook.py")],
            input=json.dumps(payload_dict),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=cwd or REPO,  # 模拟 Antigravity 在插件目录（含自身 .git）下执行钩子
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def injected_text(self, res: dict) -> str:
        steps = res.get("injectSteps") or []
        if not steps:
            return ""
        return steps[0].get("systemMessage", {}).get("systemMessage", "")

    def test_main_line_sees_worker_report_once_per_conversation(self):
        res1 = self.hook()
        self.assertIn("codex 工人的报告", self.injected_text(res1))
        # 同一会话第二次调用不再重复塞入同一条 say
        res2 = self.hook()
        self.assertEqual(res2, {})
        # 另一独立会话仍可看到自己的未读记录
        res_other = self.hook({"conversationId": "conv-other", "workspacePaths": [str(self.root)]})
        self.assertIn("codex 工人的报告", self.injected_text(res_other))

    def test_file_uri_workspace_path_is_parsed(self):
        uri = self.root.as_uri()
        res = self.hook({"conversationId": "conv-uri", "workspacePaths": [uri]})
        self.assertIn("codex 工人的报告", self.injected_text(res))

    def test_plugin_own_git_root_is_never_scanned(self):
        res = self.hook({"conversationId": "conv-empty", "workspacePaths": []}, cwd=REPO)
        self.assertEqual(res, {})

    def test_worker_process_is_skipped(self):
        self.assertEqual(self.hook(CODEX_MSG_CH="task-1"), {})
        self.assertEqual(self.hook(CLAUDE_MSG_CH="claude-task-1"), {})


if __name__ == "__main__":
    unittest.main()
