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


def data_root(home=None):
    return (Path.home() if home is None else Path(home)) / ".local" / "share" / "preza"


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
    if explicit in ('claude', 'codex'):
        return explicit
    env = os.environ if environ is None else environ
    hosts = []
    if env.get('CODEX_THREAD_ID'):
        hosts.append('codex')
    if env.get('CLAUDECODE') == '1':
        hosts.append('claude')
    if len(hosts) != 1:
        raise ValueError('Runtime identity is missing or inherited from both hosts; pass --host claude|codex from the actual conversation')
    return hosts[0]


def roles(host, level=None):
    if host not in ('claude', 'codex'):
        raise ValueError('Unsupported host')
    if host == "codex":
        profiles = json.loads(
            (SKILLS / "preza/references/worker-profiles.json").read_text(
                encoding="utf-8"
            )
        )
        if level is not None and level not in profiles["levels"]:
            raise ValueError(f"Unknown preza level: {level}")
        workers = {}
        if level is not None:
            for role, effort in profiles["levels"][level].items():
                workers[role] = {"model": profiles["model"], "effort": effort}
        return {
            "host": host,
            "coordinator": host,
            "reviewer": "orca-codex-worker",
            "review_skill": "orchestration",
            "level": level,
            "worker_profiles": workers,
            "image_provider": "codex",
            "image_mode": "native-tool-if-available",
        }
    return {'host': host, 'coordinator': host,
            'reviewer': f'{host}-subagent',
            'review_skill': 'doubt-driven-development',
            'image_provider': 'codex',
            'image_mode': 'native-tool-if-available' if host == 'codex' else 'codex-exec'}


def installed_claude_plugins(home=None):
    home = Path.home() if home is None else Path(home)
    path = home / '.claude/plugins/installed_plugins.json'
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding='utf-8')).get('plugins', {})


def find_skill(name, host=None, home=None):
    home = Path.home() if home is None else Path(home)
    override = os.environ.get('PREZA_PPT_MASTER') if name == 'ppt-master' else None
    if override and (Path(override) / 'SKILL.md').is_file():  # dev: a fork clone loaded with --plugin-dir
        return Path(override).resolve()
    if host == "codex":
        if name == "ppt-master":
            if override:
                return None
            engine = engine_checkout(home) / "skills" / name
            return engine if (engine / "SKILL.md").is_file() else None
        codex = Path(os.environ.get("CODEX_HOME") or home / ".codex")
        for root in (
            SKILLS,
            home / ".agents/skills",
            codex / "skills",
            codex / "skills/.system",
        ):
            candidate = root / name
            if (candidate / "SKILL.md").is_file():
                return candidate.resolve()
        return None
    roots = [SKILLS, home / '.agents/skills']
    clients = [host, 'claude' if host == 'codex' else 'codex'] if host else ['claude', 'codex']
    roots += [home / f'.{client}/skills' for client in clients]
    for root in roots:
        candidate = root / name
        if (candidate / 'SKILL.md').is_file():
            return candidate.resolve()
    # A registered plugin can supply files to either host; this does not assert native invocation.
    plugins = installed_claude_plugins(home)
    # ppt-master from the preza marketplace (fork) wins over the upstream marketplace
    for key in sorted(plugins, key=lambda k: not k.endswith('@preza')):
        rows = plugins[key]
        for rec in rows if isinstance(rows, list) else [rows]:
            if rec.get('scope') not in (None, 'user'):
                continue
            root = Path(rec.get('installPath', ''))
            if not root.is_absolute():
                continue
            for candidate in (root / name, root / 'skills' / name):
                if (candidate / 'SKILL.md').is_file():
                    return candidate.resolve()
    return None


def preza_version(host="codex"):
    path = SKILLS.parent / f".{host}-plugin" / "plugin.json"
    return json.loads(path.read_text(encoding="utf-8")).get("version") if path.is_file() else None


def context(host=None, level=None):
    host = resolve_host(host)
    result = roles(host, level)
    result['preza_version'] = preza_version(host)
    pm = find_skill('ppt-master', host)
    review = find_skill(result['review_skill'], host)
    result.update(platform=sys.platform, python=[sys.executable, '-X', 'utf8'],
                  ppt_master=str(pm) if pm else None,
                  review_skill_path=str(review) if review else None,
                  codex_cli=shutil.which('codex'),
                  deck_house_rules=str(SKILLS / 'deck-house-rules/SKILL.md'),
                  renderer=str(SKILLS / 'preza/scripts/render_pptx.py'),
                  evidence='CLI paths and registered files only; auth, native tools and model identities require live checks')
    if host == "codex":
        build = venv_python("3.14")
        prepared = [venv_python(version) for version in ("3.14", "3.12")]
        if (
            Path(sys.prefix) not in {p.parent.parent for p in prepared}
            and build.is_file()
        ):
            result["python"] = [str(build), "-X", "utf8"]
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
        result.update(
            orca=shutil.which("orca"),
            memory_root=str(memory_root()),
            engine_revision=revision,
            pinned_revision=ENGINE_REVISION,
        )
    return result


def write(path, data):
    """Слить окружение в runtime.json: пути и метку раскладки, которые пишет scaffold.py, сохранить."""
    path = Path(path)
    try:
        old = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    except ValueError as error:
        raise ValueError(f'{path}: не JSON ({error}) — проверь файл, runtime.py его не перезаписывает') from error
    if not isinstance(old, dict):
        raise ValueError(f'{path}: ожидался объект JSON — проверь файл, runtime.py его не перезаписывает')
    if (
        data.get("host") == old.get("host") == "codex"
        and data.get("level") is None
        and old.get("level")
    ):
        data = {**data, **roles("codex", old["level"])}
    old.update(data)
    with tempfile.TemporaryDirectory(dir=path.parent) as directory:
        candidate = Path(directory) / "runtime.json"
        candidate.write_text(
            json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(candidate, path)



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=['claude', 'codex'])
    parser.add_argument('--level', help='название выбранного уровня из брифа')
    parser.add_argument('--write', metavar='RUNTIME_JSON', help='слить результат в этот файл (Исходники/runtime.json папки задания)')
    args = parser.parse_args()
    try:
        result = context(args.host, args.level)
        if args.write:
            write(args.write, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + '\n')
