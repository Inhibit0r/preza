"""Regression cases for the Codex candidate. No model or worker is started."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/preza/scripts"))
from dispatch import command
from memory import recall, remember


class WorkerTests(unittest.TestCase):
    def test_profile_applies_only_to_new_worker_and_reuses_run(self):
        args = command("Полный дизайн", "critic", "Review", "run_SELFTEST")
        self.assertEqual(args[args.index("--model") + 1], "gpt-6.2-sol")
        self.assertEqual(args[args.index("--effort") + 1], "max")
        self.assertEqual(args[args.index("--run") + 1], "run_SELFTEST")
        self.assertNotIn("--terminal", args)

    def test_unsupported_role_fails_before_dispatch(self):
        with self.assertRaises(ValueError):
            command("Срочный", "unknown", "SELFTEST")


class MemoryTests(unittest.TestCase):
    def test_record_is_idempotent_and_search_returns_only_matching_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = (
                root,
                "range",
                "example",
                "Ставки",
                ["диапазон"],
                "SELFTEST принято",
                "Сравнить границы.",
            )
            expected = remember(*args)
            self.assertEqual(remember(*args), expected)
            self.assertEqual(
                recall(root, "диапазон", "example"),
                [{"title": "Ставки", "path": str(expected)}],
            )
            self.assertEqual(recall(root, "другая тема", None), [])
            with self.assertRaises(ValueError):
                remember(*args[:-1], "Другая запись.")
            self.assertIn(args[-1], expected.read_text(encoding="utf-8"))
