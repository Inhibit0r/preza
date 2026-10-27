from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class NumbersTests(unittest.TestCase):
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
