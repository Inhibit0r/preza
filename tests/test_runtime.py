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

    def test_reviewer_is_host_subagent_and_images_stay_codex(self):
        for host in ('codex', 'claude'):
            r = runtime.roles(host)
            self.assertEqual((r['reviewer'], r['coordinator'], r['image_provider']), (f'{host}-subagent', host, 'codex'))
            self.assertEqual(r['review_skill'], 'doubt-driven-development')
        self.assertEqual(runtime.roles('codex')['image_mode'], 'native-tool-if-available')
        self.assertEqual(runtime.roles('claude')['image_mode'], 'codex-exec')
        ctx = runtime.context('claude')
        self.assertNotIn('claudex_runner', ctx)
        self.assertEqual(Path(ctx['deck_house_rules']).parts[-2:], ('deck-house-rules', 'SKILL.md'))

    def test_ppt_master_env_override_and_preza_marketplace_preferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve()  # macOS: /var -> /private/var
            roots = {}
            for key in ('ppt-master@ppt-master', 'ppt-master@preza'):
                root = home / key.replace('@', '_') / 'skills'
                (root / 'ppt-master').mkdir(parents=True)
                (root / 'ppt-master/SKILL.md').write_text('fixture', encoding='utf-8')
                roots[key] = root
            registry = home / '.claude/plugins/installed_plugins.json'
            registry.parent.mkdir(parents=True)
            registry.write_text(json.dumps({'plugins': {k: [{'scope': 'user', 'installPath': str(v)}] for k, v in roots.items()}}), encoding='utf-8')
            self.assertEqual(runtime.find_skill('ppt-master', 'claude', home), roots['ppt-master@preza'] / 'ppt-master')
            fork = home / 'fork/skills/ppt-master'
            fork.mkdir(parents=True); (fork / 'SKILL.md').write_text('fork', encoding='utf-8')
            with patch.dict(runtime.os.environ, {'PREZA_PPT_MASTER': str(fork)}):
                self.assertEqual(runtime.find_skill('ppt-master', 'claude', home), fork)

    def test_assets_use_registered_install_not_stale_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve()  # macOS: /var -> /private/var
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

    def test_write_refuses_foreign_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'runtime.json'
            for text in ('[1, 2]', 'не json'):
                path.write_text(text, encoding='utf-8')
                with self.assertRaises(ValueError):
                    runtime.write(path, {'host': 'claude'})
                self.assertEqual(path.read_text(encoding='utf-8'), text)

    def test_write_keeps_paths_from_scaffold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'runtime.json'
            path.write_text(json.dumps({'layout': '1.3.5', 'paths': {'work': '/w'}, 'host': 'codex'}), encoding='utf-8')
            runtime.write(path, {'host': 'claude', 'python': ['python3']})
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual((data['layout'], data['paths'], data['host']), ('1.3.5', {'work': '/w'}, 'claude'))


if __name__ == '__main__':
    unittest.main()
