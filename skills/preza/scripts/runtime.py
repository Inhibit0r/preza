"""Resolve the coordinating runtime and registered skill assets without model calls."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

SKILLS = Path(__file__).resolve().parents[2]


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


def roles(host):
    if host not in ('claude', 'codex'):
        raise ValueError('Unsupported host')
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


def preza_version():
    for manifest in ('.claude-plugin/plugin.json', '.codex-plugin/plugin.json'):
        path = SKILLS.parent / manifest
        if path.is_file():
            return json.loads(path.read_text(encoding='utf-8')).get('version')
    return None


def context(host=None):
    host = resolve_host(host)
    result = roles(host)
    result['preza_version'] = preza_version()
    pm = find_skill('ppt-master', host)
    review = find_skill('doubt-driven-development', host)
    result.update(platform=sys.platform, python=[sys.executable, '-X', 'utf8'],
                  ppt_master=str(pm) if pm else None,
                  review_skill_path=str(review) if review else None,
                  codex_cli=shutil.which('codex'),
                  deck_house_rules=str(SKILLS / 'deck-house-rules/SKILL.md'),
                  renderer=str(SKILLS / 'preza/scripts/render_pptx.py'),
                  evidence='CLI paths and registered files only; auth, native tools and model identities require live checks')
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
    old.update(data)
    path.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=['claude', 'codex'])
    parser.add_argument('--write', metavar='RUNTIME_JSON', help='слить результат в этот файл (Исходники/runtime.json папки задания)')
    args = parser.parse_args()
    try:
        result = context(args.host)
        if args.write:
            write(args.write, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + '\n')
