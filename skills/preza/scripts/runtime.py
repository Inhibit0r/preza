"""Resolve the coordinating runtime and registered skill assets without model calls."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys

SKILLS = Path(__file__).resolve().parents[2]
ENGINE_REPO = "https://github.com/Inhibit0r/ppt-master.git"
ENGINE_REVISION = "1ab8a4df202677e442daebcc21931e33fbcc08df"
HOSTS = ("claude", "codex", "manual")


def user_home(home):
    return Path.home() if home is None else Path(home)


def data_root(home=None):
    override = os.environ.get("PREZA_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return user_home(home) / ".local" / "share" / "preza"


def engine_checkout(home=None):
    return data_root(home) / "engines" / ENGINE_REVISION


def venv_python(version, home=None):
    folder = data_root(home) / "venvs" / version
    return folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def memory_root(home=None):
    override = os.environ.get("PREZA_MEMORY")
    return (
        Path(override).expanduser().resolve()
        if override
        else data_root(home) / "memory"
    )


def resolve_host(explicit=None, environ=None):
    if explicit is not None:
        if explicit not in HOSTS:
            raise ValueError(f"Unsupported host: {explicit}")
        return explicit
    env = os.environ if environ is None else environ
    codex = bool(env.get("CODEX_THREAD_ID"))
    claude = env.get("CLAUDECODE") == "1"
    if codex and claude:
        raise ValueError(
            "Runtime identity is inherited from both hosts; pass --host claude|codex|manual from the actual conversation"
        )
    return "codex" if codex else "claude" if claude else "manual"


def roles(host, level=None):
    host = resolve_host(host)
    profiles = json.loads(
        (SKILLS / "preza/references/worker-profiles.json").read_text(encoding="utf-8")
    )
    if level is not None and level not in profiles["levels"]:
        raise ValueError(f"Unknown preza level: {level}")
    reviewer, review_skill = {
        "codex": ("orca-codex-worker", "orchestration"),
        "claude": ("claude-subagent", "doubt-driven-development"),
        "manual": ("separate-session-or-human", None),
    }[host]
    workers = {}
    if host == "codex" and level is not None:
        for role, effort in profiles["levels"][level].items():
            workers[role] = {"model": profiles["model"], "effort": effort}
    return {
        "host": host,
        "coordinator": host,
        "reviewer": reviewer,
        "review_skill": review_skill,
        "level": level,
        "worker_profiles": workers,
        "image_provider": "codex" if host == "codex" else "current-host",
        "image_mode": "native-tool-if-available",
    }


def claude_root(home=None):
    return Path(
        os.environ.get("CLAUDE_CONFIG_DIR") or user_home(home) / ".claude"
    ).expanduser()


def installed_claude_plugins(home=None):
    path = claude_root(home) / "plugins/installed_plugins.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("plugins", {})


def registered_claude_skill(name, home):
    plugins = installed_claude_plugins(home)
    # The historically supported preza fork takes priority among registrations.
    for key in sorted(plugins, key=lambda k: not k.endswith("@preza")):
        rows = plugins[key]
        for rec in rows if isinstance(rows, list) else [rows]:
            if rec.get("scope") not in (None, "user"):
                continue
            root = Path(rec.get("installPath", ""))
            if not root.is_absolute():
                continue
            for candidate in (root / name, root / "skills" / name):
                if (candidate / "SKILL.md").is_file():
                    return candidate.resolve()
    return None


def find_skill(name, host=None, home=None):
    host = resolve_host(host)
    isolated = bool(os.environ.get("PREZA_DATA_DIR"))
    if name == "ppt-master":
        override = os.environ.get("PREZA_PPT_MASTER")
        if override:
            engine = Path(override).expanduser().resolve()
            return engine if (engine / "SKILL.md").is_file() else None
        engine = engine_checkout(home) / "skills" / name
        if (engine / "SKILL.md").is_file():
            return engine
        if host != "claude" or isolated:
            return None
        legacy = registered_claude_skill(name, home)
        if legacy:
            return legacy
    roots = [SKILLS, data_root(home) / "skills"]
    if not isolated:
        roots.append(user_home(home) / ".agents/skills")
    if host == "codex":
        codex = Path(os.environ.get("CODEX_HOME") or user_home(home) / ".codex")
        roots.extend((codex / "skills", codex / "skills/.system"))
    if host == "claude":
        roots.append(claude_root(home) / "skills")
    for root in roots:
        candidate = root / name
        if (candidate / "SKILL.md").is_file():
            return candidate.resolve()
    return registered_claude_skill(name, home) if host == "claude" else None


def preza_version(host="codex"):
    return (SKILLS.parent / "VERSION").read_text(encoding="utf-8").strip()


def build_python(host):
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    versions = (version, "3.14", "3.12")
    if host == "codex" and not os.environ.get("PREZA_DATA_DIR"):
        versions = ("3.14", version, "3.12")
    prepared = [venv_python(v) for v in dict.fromkeys(versions)]
    if any(Path(sys.prefix).resolve() == p.parent.parent for p in prepared):
        return sys.executable
    return next((str(p) for p in prepared if p.is_file()), sys.executable)


def context(host=None, level=None):
    host = resolve_host(host)
    result = roles(host, level)
    pm = find_skill("ppt-master", host)
    review = (
        find_skill(result["review_skill"], host) if result["review_skill"] else None
    )
    revision = None
    if pm is not None and (pm.parent.parent / ".git").exists():
        try:
            git = subprocess.run(
                ["git", "-C", str(pm), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if git.returncode == 0:
                revision = git.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    engine_source = None
    if pm:
        if os.environ.get("PREZA_PPT_MASTER"):
            engine_source = "override"
        elif pm == engine_checkout() / "skills/ppt-master":
            engine_source = "pinned"
        else:
            engine_source = "legacy-claude"
    result.update(
        preza_version=preza_version(host),
        platform=sys.platform,
        python=[build_python(host), "-X", "utf8"],
        ppt_master=str(pm) if pm else None,
        review_skill_path=str(review) if review else None,
        independent_review_status="unverified",
        image_tool_status="unverified",
        codex_cli=shutil.which("codex") if host == "codex" else None,
        orca=shutil.which("orca") if host == "codex" else None,
        data_root=str(data_root()),
        memory_root=str(memory_root()),
        engine_source=engine_source,
        engine_revision=revision,
        pinned_revision=ENGINE_REVISION,
        deck_house_rules=str(SKILLS / "deck-house-rules/SKILL.md"),
        hosts_guide=str(SKILLS / "preza/references/hosts.md"),
        renderer=str(SKILLS / "preza/scripts/render_pptx.py"),
        evidence="Local discovery only; confirm tools and independent review in the actual session",
    )
    return result


def write(path, data):
    """Слить окружение в runtime.json: пути и метку раскладки, которые пишет scaffold.py, сохранить."""
    path = Path(path)
    try:
        old = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError as error:
        raise ValueError(
            f"{path}: не JSON ({error}) — проверь файл, runtime.py его не перезаписывает"
        ) from error
    if not isinstance(old, dict):
        raise ValueError(
            f"{path}: ожидался объект JSON — проверь файл, runtime.py его не перезаписывает"
        )
    if data.get("host") in HOSTS and data.get("level") is None and old.get("level"):
        data = {**data, **roles(data["host"], old["level"])}
    old.update(data)
    with tempfile.TemporaryDirectory(dir=path.parent) as directory:
        candidate = Path(directory) / "runtime.json"
        candidate.write_text(
            json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(candidate, path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=HOSTS)
    parser.add_argument("--level", help="название выбранного уровня из брифа")
    parser.add_argument(
        "--write",
        metavar="RUNTIME_JSON",
        help="слить результат в этот файл (Исходники/runtime.json папки задания)",
    )
    args = parser.parse_args()
    try:
        result = context(args.host, args.level)
        if args.write:
            write(args.write, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")
