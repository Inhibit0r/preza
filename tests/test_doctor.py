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

    def test_reviewer_and_auth_commands_follow_host(self):
        for host, reviewer in [('codex', 'claude'), ('claude', 'codex')]:
            calls = []
            def run(cmd, timeout=15):
                calls.append(cmd)
                return 0, '{"loggedIn":true}' if reviewer == 'claude' else 'Logged in using ChatGPT'
            with patch.object(doctor.shutil, 'which', side_effect=lambda name: str(Path('/tools') / (name + '.cmd'))), patch.object(doctor, 'run', side_effect=run), patch.object(doctor, 'skill_dir', return_value=None), patch.object(doctor, 'mcp_names', return_value=set()):
                rows = doctor.checks(host)
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0][0].endswith(reviewer + '.cmd'))
            self.assertEqual(calls[0][1:], ['auth', 'status'] if reviewer == 'claude' else ['login', 'status'])
            self.assertTrue(next(r for r in rows if r['name'] == f'{reviewer}: вход рецензента')['ok'])


if __name__ == '__main__':
    unittest.main()
