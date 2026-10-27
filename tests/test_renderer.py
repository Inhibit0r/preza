import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('preza_renderer', Path(__file__).resolve().parents[1] / 'skills/preza/scripts/render_pptx.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class RendererTests(unittest.TestCase):
    def test_existing_results_and_input_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'deck.pptx'
            source.write_bytes(b'input fixture')
            output = root / 'render'
            output.mkdir()
            marker = output / 'existing.png'
            marker.write_bytes(b'previous result')
            with self.assertRaises(ValueError):
                renderer.render(source, output)
            self.assertEqual(marker.read_bytes(), b'previous result')
            self.assertEqual(source.read_bytes(), b'input fixture')
            with self.assertRaises(ValueError):
                renderer.validate_paths(root / 'missing.pptx', root / 'new')

    def test_mac_keeps_legacy_renderer_without_windows_com(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()  # macOS: /var -> /private/var
            source = root / 'deck.pptx'
            source.write_bytes(b'fixture')
            output = root / 'new'
            with patch.object(renderer.sys, 'platform', 'darwin'), patch.object(renderer, 'render_mac', return_value={'slides': 1}) as mac, patch.object(renderer.shutil, 'which', side_effect=AssertionError('Windows path used')):
                self.assertEqual(renderer.render(source, output), {'slides': 1})
                mac.assert_called_once_with(source, output)


if __name__ == '__main__':
    unittest.main()
