import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preza_doctor', ROOT / 'skills/setup/scripts/doctor.py')
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


class DoctorTests(unittest.TestCase):
    def test_mcp_is_scoped_to_active_host_and_current_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); codex = home / '.codex'; codex.mkdir()
            (codex / 'config.toml').write_text('[mcp_servers.codex_only]\nurl="https://example.com"\n[mcp_servers.disabled]\nenabled=false\n', encoding='utf-8')
            (home / '.claude.json').write_text(json.dumps({'mcpServers': {'claude_only': {}}, 'projects': {str(Path.cwd()): {'mcpServers': {'current_project': {}}}, str(home / 'other'): {'mcpServers': {'unrelated_project': {}}}}}), encoding='utf-8')
            with patch.multiple(doctor, HOME=home, CODEX=codex):
                self.assertEqual(doctor.mcp_names('codex'), {'codex_only'})
                self.assertEqual(doctor.mcp_names('claude'), {'claude_only', 'current_project'})

    def test_only_claude_host_checks_codex_login_for_images(self):
        for host, expected in [('codex', []), ('claude', [['/tools/codex.cmd', 'login', 'status']])]:
            calls = []
            def run(cmd, timeout=15):
                calls.append(cmd)
                return 0, 'Logged in using ChatGPT'
            with patch.object(doctor.shutil, 'which', side_effect=lambda name: '/tools/' + name + '.cmd'), patch.object(doctor, 'run', side_effect=run), patch.object(doctor, 'skill_dir', return_value=None), patch.object(doctor, 'mcp_names', return_value=set()):
                rows = doctor.checks(host)
            self.assertEqual(calls, expected)
            names = [r['name'] for r in rows]
            self.assertFalse(any('claudex' in n or 'рецензента' in n for n in names))
            if host == 'claude':
                self.assertTrue(next(r for r in rows if r['name'] == 'Codex: вход (картинки, Облик)')['ok'])

    def test_fork_source_is_core_only_for_claude_host(self):
        for host, group in (('claude', 'Ядро'), ('codex', 'По блокам')):
            with patch.object(doctor, 'run', return_value=(0, '')), patch.object(doctor, 'skill_dir', return_value=None), patch.object(doctor, 'mcp_names', return_value=set()), patch.object(doctor, 'installed_plugins', return_value={'ppt-master@ppt-master': {}}):
                rows = {r['name']: r for r in doctor.checks(host)}
            self.assertEqual(rows['ppt-master из маркетплейса preza (форк)']['group'], group)
            row = rows['без старого источника ppt-master']
            self.assertIn('claude plugin uninstall ppt-master@ppt-master', row['fix'] if host == 'claude' else row['manual'])

    def test_git_subdir_plugin_updates_compare_with_fork_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude = Path(tmp)
            market = claude / 'plugins/marketplaces/preza/.claude-plugin'
            market.mkdir(parents=True)
            (market / 'marketplace.json').write_text(json.dumps({'plugins': [{'name': 'ppt-master', 'source': {
                'source': 'git-subdir', 'url': 'Inhibit0r/ppt-master', 'path': 'skills', 'ref': 'preza'}}]}), encoding='utf-8')
            (claude / 'plugins/known_marketplaces.json').write_text(json.dumps({'preza': {'source': {'source': 'github', 'repo': 'Inhibit0r/preza'}}}), encoding='utf-8')
            (claude / 'plugins/installed_plugins.json').write_text(json.dumps({'plugins': {'ppt-master@preza': [{'gitCommitSha': 'old'}]}}), encoding='utf-8')
            calls = []
            def run(cmd, timeout=15):
                calls.append(cmd)
                return 0, 'new\trefs/heads/preza'
            with patch.object(doctor, 'CLAUDE', claude), patch.object(doctor, 'run', side_effect=run), patch.object(doctor.shutil, 'which', return_value='/usr/bin/git'):
                found = doctor.updates()
            self.assertEqual(calls, [['git', '-c', 'protocol.allow=never', '-c', 'protocol.https.allow=always', 'ls-remote', '--', 'https://github.com/Inhibit0r/ppt-master' + '.git', 'preza']])
            self.assertEqual([u['plugin'] for u in found], ['ppt-master@preza'])

if __name__ == '__main__':
    unittest.main()
