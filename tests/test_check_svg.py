import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/preza/scripts/check_svg.py"
spec = importlib.util.spec_from_file_location("check_svg", SCRIPT)
check_svg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_svg)

PAGE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" font-size="20">{}</svg>'


class CheckSvgTest(unittest.TestCase):
    def test_skips_first_last_and_accepts_dense(self):
        with tempfile.TemporaryDirectory() as tmp:
            nums = "".join(f"<text>{i}%</text>" for i in range(30))
            for name, body in [("01_cover.svg", nums), ("02_ok.svg", "<text>Вывод</text>"),
                               ("03_dense.svg", nums), ("04_small.svg", '<text font-size="12">Источник</text>'),
                               ("05_sources.svg", '<text font-size="10">ссылки</text>')]:
                Path(tmp, name).write_text(PAGE.format(body), encoding="utf-8")
            result = check_svg.check(tmp)
            self.assertEqual(set(result), {"03_dense.svg", "04_small.svg"})
            self.assertNotIn("03_dense.svg", check_svg.check(tmp, accept={3}))


if __name__ == "__main__":
    unittest.main()
