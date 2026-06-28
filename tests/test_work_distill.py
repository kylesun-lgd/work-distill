import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class WorkDistillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.repo = Path(__file__).resolve().parents[1]
        self.work = self.root / "work-distill"
        shutil.copytree(
            self.repo,
            self.work,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
        self.env = self.home / "Documents" / "Zcode" / "work-distill"

    def tearDown(self):
        self.tmp.cleanup()

    def run_py(self, args, input_text=""):
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        return subprocess.run(
            [sys.executable, *args],
            cwd=self.work,
            env=env,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )

    def init_env(self):
        result = self.run_py(
            [
                "scripts/setup.py",
                "init",
                "--env",
                str(self.env),
                "--port",
                "7799",
                "--agent",
                "codex/default",
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def load_serve_module(self):
        spec = importlib.util.spec_from_file_location("serve_under_test", self.work / "scripts" / "serve.py")
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(module)
        return module

    def test_sediment_uses_configured_default_agent(self):
        self.init_env()

        result = self.run_py(
            [
                "scripts/sediment.py",
                "--project",
                "默认Agent项目",
                "--project-slug",
                "default-agent",
                "--type",
                "progress",
                "--summary",
                "默认 agent 生效",
            ],
            input_text="默认 agent smoke",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        index_file = self.env / "data" / "index" / "2026-06.jsonl"
        rows = [json.loads(line) for line in index_file.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[0]["agent"], "codex/default")

    def test_sediment_rejects_invalid_next_shape(self):
        self.init_env()

        result = self.run_py(
            [
                "scripts/sediment.py",
                "--project",
                "坏数据项目",
                "--project-slug",
                "bad-next",
                "--type",
                "progress",
                "--summary",
                "坏 next",
                "--next",
                '["字符串待办"]',
            ]
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("--next 每项必须是对象且含 t 字段", result.stderr)

    def test_reveal_allows_env_relative_paths(self):
        self.init_env()
        serve = self.load_serve_module()
        index = self.env / "index.html"

        full, error = serve.resolve_reveal_path(str(self.env), "index.html")

        self.assertEqual(error, "")
        self.assertEqual(Path(full), index.resolve())

    def test_reveal_rejects_relative_path_escape(self):
        self.init_env()
        serve = self.load_serve_module()

        full, error = serve.resolve_reveal_path(str(self.env), "../secret.txt")

        self.assertEqual(full, "")
        self.assertIn("运行环境之外", error)

    def test_reveal_allows_recorded_absolute_artifact(self):
        self.init_env()
        serve = self.load_serve_module()
        artifact = self.root / "artifact.txt"
        artifact.write_text("ok", encoding="utf-8")
        index_file = self.env / "data" / "index" / "2026-06.jsonl"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text(json.dumps({"artifacts": [str(artifact)]}, ensure_ascii=False) + "\n", encoding="utf-8")

        full, error = serve.resolve_reveal_path(str(self.env), str(artifact))

        self.assertEqual(error, "")
        self.assertEqual(Path(full), artifact.resolve())

    def test_reveal_rejects_unregistered_absolute_path(self):
        self.init_env()
        serve = self.load_serve_module()
        secret = self.root / "secret.txt"
        secret.write_text("no", encoding="utf-8")

        full, error = serve.resolve_reveal_path(str(self.env), str(secret))

        self.assertEqual(full, "")
        self.assertIn("未登记", error)


if __name__ == "__main__":
    unittest.main()
