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

    def test_gap_requires_real_empty_cell_spoken_reason_and_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deck = Presentation()
            slide = deck.slides.add_slide(deck.slide_layouts[6])
            data = CategoryChartData()
            labels = ["2021-Q4", "2022-Q1", "2022-Q2", "2022-Q3"]
            data.categories = labels
            data.add_series("SELFTEST", [12, None, 0, 35])
            chart = slide.shapes.add_chart(
                XL_CHART_TYPE.LINE, 0, 0, Inches(4), Inches(3), data
            ).chart
            slide.shapes.add_table(2, 2, Inches(4), 0, Inches(3), Inches(3))
            png = root / "slide-01.png"
            png.write_bytes(b"SELFTEST")
            reason = "В таблице за первый квартал 2022 года показатель не опубликован."
            item = dict(
                slide=1,
                name="SELFTEST",
                frequency="quarter",
                start=labels[0],
                end=labels[-1],
                points=[
                    [label, val, "S1"] for label, val in zip(labels, (12, None, 0, 35))
                ],
                gap_notes={labels[1]: reason},
            )
            checks = dict(
                composition="Сравнение",
                time_axis="Календарная ось",
                table="Шапка и строки на одной сетке",
            )
            row = dict(
                slide=1,
                png_sha256=digest(png),
                reviewer="ctx_SELFTEST",
                verdict="APPROVED",
                checks=checks,
            )

            def inspect():
                path = root / "chart.pptx"
                deck.save(path)
                return verify(
                    path,
                    root,
                    dict(deck_sha256=digest(path), series=[item], slides=[row]),
                )

            self.assertTrue(any("speaker notes" in e for e in inspect()))
            slide.notes_slide.notes_text_frame.text = reason
            self.assertEqual(inspect(), [])
            for kind in ("host-subagent", "separate-session", "human"):
                row["reviewer"] = {
                    "kind": kind,
                    "id": "SELFTEST-2",
                    "evidence": "review/notes.md",
                }
                self.assertEqual(inspect(), [])
            for reviewer in (
                None,
                "manual",
                {"kind": "lead", "id": "SELFTEST", "evidence": "self"},
            ):
                row["reviewer"] = reviewer
                self.assertTrue(
                    any("independent approval" in error for error in inspect())
                )
            row["reviewer"] = "ctx_SELFTEST"
            row["verdict"] = "PENDING"
            self.assertTrue(any("independent approval" in error for error in inspect()))
            row["verdict"] = "APPROVED"
            del checks["table"]
            self.assertTrue(any("table" in e for e in inspect()))
            checks["table"] = "Шапка покрывает все строки"
            item["points"][1][2] = ""
            self.assertTrue(any("source" in e for e in inspect()))
            item["points"][1][2] = "S1"
            mode = chart._chartSpace.xpath(".//c:dispBlanksAs")[0]
            mode.set("val", "span")
            self.assertTrue(any("display as gaps" in e for e in inspect()))
            mode.set("val", "gap")
            # A real reported zero moves into the missing slot while the cache still has three values.
            chart._chartSpace.xpath('.//c:val//c:pt[@idx="2"]')[0].set("idx", "1")
            self.assertTrue(any("match" in e for e in inspect()))
            del item["gap_notes"][labels[1]]
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
