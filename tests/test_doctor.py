import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "preza_doctor", ROOT / "skills/setup/scripts/doctor.py"
)
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


class DoctorTests(unittest.TestCase):
    def test_mcp_is_scoped_to_active_host_and_current_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex = home / ".codex"
            codex.mkdir()
            (codex / "config.toml").write_text(
                '[mcp_servers.codex_only]\nurl="https://example.com"\n[mcp_servers.disabled]\nenabled=false\n',
                encoding="utf-8",
            )
            (home / ".claude.json").write_text(
                json.dumps(
                    {
                        "mcpServers": {"claude_only": {}},
                        "projects": {
                            str(Path.cwd()): {"mcpServers": {"current_project": {}}},
                            str(home / "other"): {
                                "mcpServers": {"unrelated_project": {}}
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch.multiple(doctor, HOME=home, CODEX=codex):
                self.assertEqual(doctor.mcp_names("codex"), {"codex_only"})
                self.assertEqual(
                    doctor.mcp_names("claude"), {"claude_only", "current_project"}
                )

    def test_capabilities_remain_unverified_and_no_other_client_is_called(self):
        for host in ("manual", "claude", "codex"):
            with (
                patch.object(doctor.shutil, "which", return_value=None),
                patch.object(doctor, "run") as run,
                patch.object(doctor, "skill_dir", return_value=None),
                patch.object(doctor, "mcp_names", return_value=set()),
            ):
                rows = {r["name"]: r for r in doctor.checks(host)}
            run.assert_not_called()
            self.assertFalse(rows["Генерация изображений в текущем хосте"]["ok"])
            self.assertFalse(rows["Независимая проверка в текущем хосте"]["ok"])
            self.assertEqual("Orca для исполнителей Codex" in rows, host == "codex")
            self.assertFalse(any("Codex: вход" in n for n in rows))
            if host == "manual":
                self.assertFalse(
                    any("claude " in cmd for row in rows.values() for cmd in row["fix"])
                )

    def test_packages_are_checked_in_selected_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / "requirements.txt"
            req.write_text("python-pptx>=0.6.21\nmissing\n", encoding="utf-8")
            with patch.object(
                doctor, "run", return_value=(0, '["Python_PPTX"]')
            ) as run:
                self.assertEqual(
                    doctor.missing_packages(req, "/other/python"), ["missing"]
                )
            self.assertEqual(run.call_args.args[0][:3], ["/other/python", "-X", "utf8"])

    def test_git_subdir_plugin_updates_compare_with_fork_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude = Path(tmp)
            market = claude / "plugins/marketplaces/preza/.claude-plugin"
            market.mkdir(parents=True)
            (market / "marketplace.json").write_text(
                json.dumps(
                    {
                        "plugins": [
                            {
                                "name": "ppt-master",
                                "source": {
                                    "source": "git-subdir",
                                    "url": "Inhibit0r/ppt-master",
                                    "path": "skills",
                                    "ref": "preza",
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (claude / "plugins/known_marketplaces.json").write_text(
                json.dumps(
                    {
                        "preza": {
                            "source": {"source": "github", "repo": "Inhibit0r/preza"}
                        }
                    }
                ),
                encoding="utf-8",
            )
            (claude / "plugins/installed_plugins.json").write_text(
                json.dumps(
                    {"plugins": {"ppt-master@preza": [{"gitCommitSha": "old"}]}}
                ),
                encoding="utf-8",
            )
            calls = []

            def run(cmd, timeout=15):
                calls.append(cmd)
                return 0, "new\trefs/heads/preza"

            with (
                patch.object(doctor, "CLAUDE", claude),
                patch.object(doctor, "run", side_effect=run),
                patch.object(doctor.shutil, "which", return_value="/usr/bin/git"),
            ):
                found = doctor.updates()
            self.assertEqual(
                calls,
                [
                    [
                        "git",
                        "-c",
                        "protocol.allow=never",
                        "-c",
                        "protocol.https.allow=always",
                        "ls-remote",
                        "--",
                        "https://github.com/Inhibit0r/ppt-master" + ".git",
                        "preza",
                    ]
                ],
            )
            self.assertEqual([u["plugin"] for u in found], ["ppt-master@preza"])


if __name__ == "__main__":
    unittest.main()
