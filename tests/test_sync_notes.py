import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "preza_sync_notes", ROOT / "skills/preza/scripts/sync_notes.py"
)
sync_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_notes)

SCRIPT = "# Речь\n\n## Слайд 1. Титул\nДобрый день.\n\n## Слайд 2. Рынок\nДвое держат половину рынка.\n"


class SyncNotesTests(unittest.TestCase):
    def project(self, tmp):
        root = Path(tmp)
        (root / "svg_output").mkdir()
        for name in ("01_title.svg", "02_market.svg", "02b_market-zoom.svg"):
            (root / "svg_output" / name).write_text("<svg/>", encoding="utf-8")
        (root / "notes").mkdir()
        (root / "notes/total.md").write_text("# 01_title\n\nстарое\n", encoding="utf-8")
        return root

    def test_sections_become_notes_of_clean_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.project(tmp)
            sync_notes.sync(root, SCRIPT)
            total = (root / "notes/total.md").read_text(encoding="utf-8")
            self.assertEqual(
                total,
                "# 01_title\n\nДобрый день.\n\n---\n\n# 02_market\n\nДвое держат половину рынка.\n"
                "\n---\n\n# 02b_market-zoom\n\nДвое держат половину рынка.\n",
            )
            self.assertIn(
                "старое", (root / "notes/total.md.bak").read_text(encoding="utf-8")
            )

    def test_count_mismatch_leaves_notes_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.project(tmp)
            with self.assertRaises(ValueError):
                sync_notes.sync(root, SCRIPT + "\n## Слайд 3. Лишний\nТекст.\n")
            self.assertEqual(
                (root / "notes/total.md").read_text(encoding="utf-8"),
                "# 01_title\n\nстарое\n",
            )


    def test_heading_inside_section_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.project(tmp)
            with self.assertRaises(ValueError):
                sync_notes.sync(root, SCRIPT.replace("Двое держат", "### 3 причины\nДвое держат"))
            self.assertEqual((root / "notes/total.md").read_text(encoding="utf-8"), "# 01_title\n\nстарое\n")

if __name__ == "__main__":
    unittest.main()
