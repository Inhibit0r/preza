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
            'reviewer': 'claude' if host == 'codex' else 'codex',
            'image_provider': 'codex',
            'image_mode': 'native-tool-if-available' if host == 'codex' else 'capable-codex-session'}


def installed_claude_plugins(home=None):
    home = Path.home() if home is None else Path(home)
    path = home / '.claude/plugins/installed_plugins.json'
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding='utf-8')).get('plugins', {})


def find_skill(name, host=None, home=None):
    home = Path.home() if home is None else Path(home)
    roots = [SKILLS, home / '.agents/skills']
    clients = [host, 'claude' if host == 'codex' else 'codex'] if host else ['claude', 'codex']
    roots += [home / f'.{client}/skills' for client in clients]
    for root in roots:
        candidate = root / name
        if (candidate / 'SKILL.md').is_file():
            return candidate.resolve()
    # A registered plugin can supply files to either host; this does not assert native invocation.
    for rows in installed_claude_plugins(home).values():
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


def context(host=None):
    host = resolve_host(host)
    result = roles(host)
    pm = find_skill('ppt-master', host)
    loop = find_skill('claudex-loop', host)
    result.update(platform=sys.platform, python=[sys.executable, '-X', 'utf8'],
                  ppt_master=str(pm) if pm else None,
                  claudex_runner=str(loop / 'scripts/runner.py') if loop else None,
                  reviewer_cli=shutil.which(result['reviewer']),
                  renderer=str(SKILLS / 'preza/scripts/render_pptx.py'),
                  evidence='CLI paths and registered files only; auth, native tools and model identities require live checks')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=['claude', 'codex'])
    args = parser.parse_args()
    try:
        print(json.dumps(context(args.host), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + '\n')
