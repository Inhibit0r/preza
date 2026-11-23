import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class NumbersTests(unittest.TestCase):
    def test_clock_evidence_is_atomic_and_ratios_remain_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            checker = data / "check_numbers.py"
            shutil.copyfile(
                Path(__file__).resolve().parents[1]
                / "skills/preza/scripts/check_numbers.py",
                checker,
            )
            (data / "sources.md").write_text("| S | SELFTEST |\n", encoding="utf-8")
            (data / "claims.csv").write_text(
                "id;value;unit;period;source;context;claim\n"
                "H;17;час;2025;S;смена;начало смены\n"
                "T;09:30;время;2025;S;смена;первая смена\n"
                "A;1;шт;2025;S;соотношение;числитель\n"
                "B;10;шт;2025;S;соотношение;знаменатель\n"
                "N;45;мин;2025;S;смена;длительность\n",
                encoding="utf-8",
            )
            (data / "usage.csv").write_text(
                "slide;claims\n1;H,T,A,B,N\n", encoding="utf-8"
            )
            speech = root / "speech.md"
            report = root / "report.md"

            def run(body):
                speech.write_text("## Слайд 1. SELFTEST\n" + body, encoding="utf-8")
                return subprocess.run(
                    [
                        sys.executable,
                        str(checker),
                        "--script",
                        str(speech),
                        "--report",
                        str(report),
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    env={**os.environ, "PYTHONIOENCODING": "cp1252"},
                )

            valid = run("Смена в 9:30. Следующая смена с 17:00. Соотношение 1:10.")
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            self.assertIn("чисел сопоставлено", valid.stdout)
            rows = report.read_text(encoding="utf-8")
            self.assertIn("| 17:00 | H |", rows)
            self.assertIn("| 9:30 | T |", rows)
            self.assertIn("| 10 | B |", rows)
            for invalid in (
                "Смена в 17:45.",
                "Мы пришли в 17:00.",
                "Смена с 17:00 длится 99 минут.",
            ):
                with self.subTest(body=invalid):
                    self.assertNotEqual(run(invalid).returncode, 0)
            claims = data / "claims.csv"
            claims.write_text(
                claims.read_text(encoding="utf-8").replace(
                    ";смена;начало", ";17 ч;начало"
                ),
                encoding="utf-8",
            )
            self.assertEqual(run("До 17:00 ждали меньше.").returncode, 0)

    def test_empty_claim_list_is_valid_but_unregistered_numbers_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'data'
            data.mkdir()
            script = data / 'check_numbers.py'
            shutil.copyfile(Path(__file__).resolve().parents[1] / 'skills/preza/scripts/check_numbers.py', script)
            (data / 'sources.md').write_text('| fixture | synthetic |\n', encoding='utf-8')
            (data / 'claims.csv').write_text('id;value;unit;period;source;context;claim\nA;25;units;demo;fixture;group;group A\n', encoding='utf-8')
            (data / 'usage.csv').write_text('slide;claims\n1;\n2;A\n', encoding='utf-8')
            args = [sys.executable, '-X', 'utf8', str(script)]
            result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            speech = root / 'script.md'
            speech.write_text('## Слайд 1. Без чисел\nUnexpected 99.\n', encoding='utf-8')
            result = subprocess.run(args + ['--script', str(speech)], capture_output=True, text=True, encoding='utf-8')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('99', result.stdout)


if __name__ == '__main__':
    unittest.main()
