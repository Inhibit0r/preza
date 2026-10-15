import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preza_runtime', ROOT / 'skills/preza/scripts/runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeTests(unittest.TestCase):
    def test_host_is_runtime_not_installed_cli(self):
        with patch.object(runtime.shutil, 'which', return_value='both-clis-installed'):
            self.assertEqual(runtime.resolve_host(environ={'CODEX_THREAD_ID': 'test'}), 'codex')
            self.assertEqual(runtime.resolve_host(environ={'CLAUDECODE': '1'}), 'claude')
            for env in [{}, {'CODEX_THREAD_ID': 'test', 'CLAUDECODE': '1'}]:
                with self.assertRaises(ValueError):
                    runtime.resolve_host(environ=env)
            self.assertEqual(runtime.resolve_host('claude', {'CODEX_THREAD_ID': 'inherited'}), 'claude')

    def test_review_roles_are_symmetric_and_images_stay_codex(self):
        for host, reviewer in [('codex', 'claude'), ('claude', 'codex')]:
            self.assertEqual(runtime.roles(host)['reviewer'], reviewer)
            self.assertEqual(runtime.roles(host)['coordinator'], host)
            self.assertEqual(runtime.roles(host)['image_provider'], 'codex')

    def test_assets_use_registered_install_not_stale_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            current = home / 'registered/plugin/ppt-master'
            stale = home / '.codex/plugins/cache/unused/ppt-master/999/ppt-master'
            for p in [current, stale]:
                p.mkdir(parents=True); (p / 'SKILL.md').write_text('fixture', encoding='utf-8')
            registry = home / '.claude/plugins/installed_plugins.json'
            registry.parent.mkdir(parents=True)
            registry.write_text(json.dumps({'plugins': {'ppt-master@pm': [{'scope': 'user', 'installPath': str(current.parent)}]}}), encoding='utf-8')
            self.assertEqual(runtime.find_skill('ppt-master', 'codex', home), current)
            shared = home / '.agents/skills/ppt-master'
            shared.mkdir(parents=True); (shared / 'SKILL.md').write_text('local adaptation', encoding='utf-8')
            self.assertEqual(runtime.find_skill('ppt-master', 'codex', home), shared)


if __name__ == '__main__':
    unittest.main()
