import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "preza_runtime", ROOT / "skills/preza/scripts/runtime.py"
)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeTests(unittest.TestCase):
    def test_host_is_runtime_not_installed_cli(self):
        with patch.object(runtime.shutil, "which", return_value="both-clis-installed"):
            self.assertEqual(
                runtime.resolve_host(environ={"CODEX_THREAD_ID": "test"}), "codex"
            )
            self.assertEqual(
                runtime.resolve_host(environ={"CLAUDECODE": "1"}), "claude"
            )
            self.assertEqual(runtime.resolve_host(environ={}), "manual")
            with self.assertRaises(ValueError):
                runtime.resolve_host(
                    environ={"CODEX_THREAD_ID": "test", "CLAUDECODE": "1"}
                )
            with self.assertRaisesRegex(ValueError, "Unsupported host"):
                runtime.resolve_host("unknown", {})
            self.assertEqual(
                runtime.resolve_host("claude", {"CODEX_THREAD_ID": "inherited"}),
                "claude",
            )

    def test_roles_follow_leading_host(self):
        legacy = runtime.roles("claude")
        self.assertEqual(legacy["reviewer"], "claude-subagent")
        self.assertEqual(legacy["image_provider"], "current-host")
        self.assertEqual(legacy["image_mode"], "native-tool-if-available")
        manual = runtime.roles("manual", "Обычный")
        self.assertEqual(manual["reviewer"], "separate-session-or-human")
        self.assertEqual(manual["worker_profiles"], {})
        self.assertIsNone(manual["review_skill"])
        native = runtime.roles("codex", "Усиленный")
        self.assertEqual(native["reviewer"], "orca-codex-worker")
        self.assertEqual(native["worker_profiles"]["critic"]["effort"], "max")
        self.assertEqual(
            runtime.roles("codex", "Обычный")["worker_profiles"]["design"]["effort"],
            "xhigh",
        )
        self.assertNotIn("model", native)
        ctx = runtime.context("claude")
        self.assertNotIn("claudex_runner", ctx)
        self.assertEqual(
            Path(ctx["deck_house_rules"]).parts[-2:], ("deck-house-rules", "SKILL.md")
        )

    def test_ppt_master_env_override_and_preza_marketplace_preferred(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(runtime.os.environ, clear=True),
        ):
            home = Path(tmp).resolve()  # macOS: /var -> /private/var
            roots = {}
            for key in ("ppt-master@ppt-master", "ppt-master@preza"):
                root = home / key.replace("@", "_") / "skills"
                (root / "ppt-master").mkdir(parents=True)
                (root / "ppt-master/SKILL.md").write_text("fixture", encoding="utf-8")
                roots[key] = root
            registry = home / ".claude/plugins/installed_plugins.json"
            registry.parent.mkdir(parents=True)
            registry.write_text(
                json.dumps(
                    {
                        "plugins": {
                            k: [{"scope": "user", "installPath": str(v)}]
                            for k, v in roots.items()
                        }
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                runtime.find_skill("ppt-master", "claude", home),
                roots["ppt-master@preza"] / "ppt-master",
            )
            fork = home / "fork/skills/ppt-master"
            fork.mkdir(parents=True)
            (fork / "SKILL.md").write_text("fork", encoding="utf-8")
            with patch.dict(runtime.os.environ, {"PREZA_PPT_MASTER": str(fork)}):
                self.assertEqual(runtime.find_skill("ppt-master", "claude", home), fork)

    def test_assets_use_registered_install_not_stale_cache(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(runtime.os.environ, clear=True),
        ):
            home = Path(tmp).resolve()  # macOS: /var -> /private/var
            current = home / "registered/plugin/ppt-master"
            stale = home / ".codex/plugins/cache/unused/ppt-master/999/ppt-master"
            for p in [current, stale]:
                p.mkdir(parents=True)
                (p / "SKILL.md").write_text("fixture", encoding="utf-8")
            registry = home / ".claude/plugins/installed_plugins.json"
            registry.parent.mkdir(parents=True)
            registry.write_text(
                json.dumps(
                    {
                        "plugins": {
                            "ppt-master@pm": [
                                {"scope": "user", "installPath": str(current.parent)}
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            self.assertIsNone(runtime.find_skill("ppt-master", "codex", home))
            pinned = runtime.engine_checkout(home) / "skills/ppt-master"
            pinned.mkdir(parents=True)
            (pinned / "SKILL.md").write_text("pinned", encoding="utf-8")
            self.assertEqual(runtime.find_skill("ppt-master", "codex", home), pinned)

    def test_version_and_native_marketplaces_share_package(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        for host in ("claude", "codex", "manual"):
            self.assertEqual(runtime.preza_version(host), version)
        for client in ("claude", "codex"):
            manifest = json.loads(
                (ROOT / f".{client}-plugin/plugin.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                (manifest["name"], manifest["version"]), ("preza", version)
            )
        claude = json.loads(
            (ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(claude["plugins"][0]["version"], version)
        self.assertEqual(claude["plugins"][0]["source"], "./")
        self.assertIn("ppt-master", {item["name"] for item in claude["plugins"]})
        codex = json.loads(
            (ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            codex["plugins"][0]["source"], {"source": "local", "path": "./"}
        )
        for skill in ("preza", "setup", "deck-house-rules"):
            self.assertIn(
                f"name: {skill}\n",
                (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8"),
            )

    def test_isolated_data_and_claude_profile_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            data_dir = root / "data dir"
            profile = root / "claude profile"
            legacy = profile / "plugins/legacy/ppt-master"
            legacy.mkdir(parents=True)
            (legacy / "SKILL.md").touch()
            registry = profile / "plugins/installed_plugins.json"
            registry.write_text(
                json.dumps(
                    {
                        "plugins": {
                            "ppt-master@preza": [
                                {"scope": "user", "installPath": str(legacy.parent)}
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                runtime.os.environ, {"CLAUDE_CONFIG_DIR": str(profile)}, clear=True
            ):
                self.assertEqual(
                    runtime.find_skill("ppt-master", "claude", root), legacy
                )
                self.assertIsNone(runtime.find_skill("ppt-master", "manual", root))
                with patch.dict(runtime.os.environ, {"PREZA_DATA_DIR": str(data_dir)}):
                    self.assertIsNone(runtime.find_skill("ppt-master", "claude", root))
                    engine = runtime.engine_checkout(root) / "skills/ppt-master"
                    engine.mkdir(parents=True)
                    (engine / "SKILL.md").touch()
                    self.assertEqual(runtime.memory_root(root), data_dir / "memory")
                    for host in ("manual", "claude", "codex"):
                        self.assertEqual(
                            runtime.find_skill("ppt-master", host, root), engine
                        )
                    with patch.dict(
                        runtime.os.environ, {"PREZA_PPT_MASTER": str(root / "absent")}
                    ):
                        self.assertIsNone(
                            runtime.find_skill("ppt-master", "claude", root)
                        )
                    with patch.object(
                        Path, "home", side_effect=RuntimeError("no user profile")
                    ):
                        ctx = runtime.context("manual")
                        self.assertEqual(
                            runtime.find_skill("preza", "manual"), ROOT / "skills/preza"
                        )
                    self.assertIsNone(ctx["orca"])
                    self.assertIsNone(ctx["codex_cli"])
                    self.assertEqual(ctx["engine_source"], "pinned")

    def test_switching_hosts_keeps_level_and_discards_codex_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.json"
            runtime.write(path, runtime.roles("codex", "Обычный"))
            runtime.write(path, runtime.roles("manual"))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["host"], "manual")
            self.assertEqual(data["level"], "Обычный")
            self.assertEqual(data["worker_profiles"], {})

    def test_write_refuses_foreign_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.json"
            for text in ("[1, 2]", "не json"):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    runtime.write(path, {"host": "claude"})
                self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_write_keeps_paths_from_scaffold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.json"
            path.write_text(
                json.dumps(
                    {"layout": "1.3.5", "paths": {"work": "/w"}, "host": "codex"}
                ),
                encoding="utf-8",
            )
            runtime.write(path, {"host": "claude", "python": ["python3"]})
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                (data["layout"], data["paths"], data["host"]),
                ("1.3.5", {"work": "/w"}, "claude"),
            )


if __name__ == "__main__":
    unittest.main()
