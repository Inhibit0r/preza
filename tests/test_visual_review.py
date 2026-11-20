from pathlib import Path
import sys
import tempfile
import unittest
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/preza/scripts"))
from check_visual_review import digest, series_errors, verify


class VisualTests(unittest.TestCase):
    def test_quarter_boundary(self):
        item = dict(
            name="SELFTEST",
            frequency="quarter",
            start="2024-Q4",
            end="2025-Q1",
            points=[["2024-Q4", 0, "S1"], ["2025-Q1", 12, "S2"]],
        )
        self.assertEqual(series_errors(item), [])
        item["end"] = item["points"][1][0] = "2025-Q2"
        self.assertTrue(series_errors(item))

    def test_native_series_and_final_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deck = Presentation()
            slide = deck.slides.add_slide(deck.slide_layouts[6])
            data = CategoryChartData()
            data.categories = ["2023", "2024", "2025"]
            data.add_series("SELFTEST", (0.3, 0.4, 0.5))
            slide.shapes.add_chart(
                XL_CHART_TYPE.COLUMN_CLUSTERED, 0, 0, Inches(4), Inches(3), data
            )
            file = root / "case.pptx"
            deck.save(file)
            png = root / "slide-1.png"
            png.write_bytes(b"SELFTEST image fingerprint")
            item = dict(
                slide=1,
                name="example",
                frequency="year",
                start="2023",
                end="2025",
                points=[["2023", 30, "S1"], ["2024", 40, "S2"], ["2025", 50, "S3"]],
                chart_multiplier=100,
            )
            row = dict(
                slide=1,
                png_sha256=digest(png),
                verdict="APPROVED",
                reviewer="ctx_SELFTEST",
                checks={
                    "composition": "Общая шкала",
                    "time_axis": "Все три года подписаны",
                },
            )
            receipt = dict(deck_sha256=digest(file), series=[item], slides=[row])
            self.assertEqual(verify(file, root, receipt), [])
            item["points"][1][1] = 42
            self.assertTrue(verify(file, root, receipt))
            item["points"].pop(1)
            self.assertTrue(series_errors(item))
            row["verdict"] = "REVISE"
            png.write_bytes(b"SELFTEST changed")
            errors = verify(file, root, receipt)
            self.assertTrue(any("PNG changed" in e for e in errors))
            self.assertTrue(any("approval" in e for e in errors))
