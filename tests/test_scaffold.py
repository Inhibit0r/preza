import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/preza/scripts/scaffold.py"
spec = importlib.util.spec_from_file_location("preza_scaffold", SCRIPT)
scaffold = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scaffold)


def run(*args):
    # как в hosts.md: Python-команды с -X utf8, иначе на Windows вывод в cp1252
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class ScaffoldTests(unittest.TestCase):
    def test_selftest(self):
        scaffold.selftest()

    def test_codex_host_writes_agents_md_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            scaffold.init(tmp, "company", host="codex")
            scaffold.init(tmp, "company", host="codex")
            root = Path(tmp)
            self.assertEqual(
                (root / "AGENTS.md").read_text(encoding="utf-8").count(scaffold.START),
                1,
            )
            self.assertIn(
                "$preza:preza", (root / "AGENTS.md").read_text(encoding="utf-8")
            )
            self.assertFalse((root / "CLAUDE.md").exists())
            self.assertTrue((root / "БРЕНД.md").is_file() and (root / "Бренд").is_dir())

    def test_existing_memory_keeps_text_and_gets_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = Path(tmp) / "КУРС.md"
            memory.write_text(
                "# Курс\n\n## Известные ошибки\n- своё\n", encoding="utf-8"
            )
            scaffold.init(tmp, "subject")
            text = memory.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("# Курс\n\n## Известные ошибки\n- своё\n"))
            self.assertEqual(text.count(scaffold.SECTION), 1)

    def test_cli_work_prints_paths_and_check_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            run("init", tmp, "--kind", "subject")
            paths = json.loads(
                run("work", tmp, "--series", "Мое", "--task", "ДЗ-1").stdout
            )
            self.assertEqual(set(paths), {"work", "src", *scaffold.KEYS})
            self.assertEqual(run("check", paths["work"]).returncode, 0)
            (Path(paths["work"]) / "черновик.md").write_text("", encoding="utf-8")  # файл пользователя
            self.assertEqual(run("check", paths["work"]).returncode, 0)
            (Path(paths["work"]) / "render").mkdir()  # папка preza не на месте
            self.assertEqual(run("check", paths["work"]).returncode, 1)
            self.assertEqual(run("work", tmp).returncode, 2)


if __name__ == "__main__":
    unittest.main()
