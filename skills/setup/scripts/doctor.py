#!/usr/bin/env python3
"""Проверка окружения preza: что установлено, чего не хватает, что можно обновить.

  python3 doctor.py            таблица и команды установки
  python3 doctor.py --json     то же в JSON (для навыка /preza:setup)
  python3 doctor.py --offline  без проверки обновлений по сети
  python3 doctor.py --selftest

Только стандартная библиотека. Код выхода 1 — не хватает обязательного.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

HOME = Path.home()
CLAUDE = HOME / ".claude"
CODEX = Path(os.environ.get("CODEX_HOME") or HOME / ".codex")
MAC, WIN = sys.platform == "darwin", os.name == "nt"
PY = "python" if WIN else "python3"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "preza/scripts"))
import runtime
HOST = None
# Обновления проверяются только у плагинов, от которых зависит preza. Официальный маркетплейс собран
# из чужих репозиториев: его коммит с установленным плагином не сравнить.
RELATED = {
    "preza",
    "ppt-master",
    "frontend-slides",
    "claudex-loop",
    "document-skills",
    "avoid-ai-writing-russian",
    "to-md",
}
NO_UPDATE_CHECK = {"claude-plugins-official"}


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def installed_plugins():
    """{"имя@маркетплейс": запись установки}."""
    data = load_json(CLAUDE / "plugins/installed_plugins.json").get("plugins", {})
    return {k: (v[0] if isinstance(v, list) and v else v) for k, v in data.items() if v}


def plugin_key(name):
    return next((k for k in installed_plugins() if k.split("@")[0] == name), None)


def skill_dir(name):
    return runtime.find_skill(name, HOST, HOME)


POINTER_FILES = ("SKILL.md", "references/image-generator.md", "references/executor-base.md")


def rules_pointer_exists(skill_file, expected=None):
    """Указатель ведёт к существующему SKILL.md, при наличии ожидаемого — с тем же содержимым.

    Сравнивается содержимое, а не путь: копии preza в Claude, Codex и клоне равноценны.
    """
    for line in skill_file.read_text(encoding="utf-8").splitlines():
        if "deck-house-rules" in line:
            for target in re.findall(r"`([^`]+)`", line):
                try:
                    path = Path(target).expanduser()
                except RuntimeError:
                    continue
                if (
                    path.name == "SKILL.md"
                    and path.is_file()
                    and (expected is None or path.read_bytes() == expected.read_bytes())
                ):
                    return True
    return False


def rules_installed(pm, expected=None):
    """Указатели во всех трёх файлах ppt-master: прерванный патч не считается выполненным."""
    return all(
        (pm / rel).is_file() and rules_pointer_exists(pm / rel, expected)
        for rel in POINTER_FILES
    )


def req_name(line):
    """Имя пакета из строки requirements.txt или None."""
    line = line.split("#")[0].split(";")[0].strip()
    return re.split(r"[<>=!~\[ ]", line, maxsplit=1)[0] if line else None


def missing_packages(req_file):
    missing = []
    for line in req_file.read_text(encoding="utf-8").splitlines():
        name = req_name(line)
        if name:
            try:
                metadata.version(name)
            except metadata.PackageNotFoundError:
                missing.append(name)
    return missing


def market_url(entry):
    """git-адрес маркетплейса из known_marketplaces.json или None."""
    src = (entry or {}).get("source", {})
    if src.get("source") == "github" and src.get("repo"):
        return f"https://github.com/{src['repo']}.git"
    return src.get("url")


def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def mcp_names(host=None):
    host = runtime.resolve_host(host or HOST)
    if host == "codex":
        path = CODEX / "config.toml"
        if not path.is_file():
            return set()
        try:
            import tomllib
        except ImportError:  # Python 3.10 remains supported for Claude and CLI-backed Codex discovery.
            cli = shutil.which("codex")
            code, text = run([cli, "mcp", "list", "--json"]) if cli else (1, "")
            rows = json.loads(text) if code == 0 else []
            return {r["name"].lower() for r in rows if r.get("enabled", True)}
        servers = tomllib.loads(path.read_text(encoding="utf-8")).get("mcp_servers", {})
        return {name.lower() for name, row in servers.items() if row.get("enabled", True)}
    d = load_json(HOME / ".claude.json")
    names = set(d.get("mcpServers", {}))
    # MCP from another project is not evidence for the current project.
    cwd = os.path.normcase(str(Path.cwd().resolve()))
    for project, config in d.get("projects", {}).items():
        if os.path.normcase(str(Path(project).resolve())) == cwd:
            names |= set(config.get("mcpServers", {}))
    return {n.lower() for n in names}


def install_plugin(repo, name, market=None):
    market = market or name
    return [
        f"claude plugin marketplace add {repo}",
        f"claude plugin install {name}@{market}",
    ]


def powerpoint_found():
    if MAC:
        return Path("/Applications/Microsoft PowerPoint.app").exists()
    if WIN:
        roots = [
            os.environ.get("ProgramFiles", ""),
            os.environ.get("ProgramFiles(x86)", ""),
        ]
        return any(
            Path(r, "Microsoft Office/root/Office16/POWERPNT.EXE").exists()
            for r in roots
            if r
        )
    return False


def checks(host=None):
    global HOST
    HOST = runtime.resolve_host(host or HOST)
    host = HOST
    """Список проверок: группа, компонент, есть ли, подробность, команды, ручные шаги."""
    out = []

    def add(group, name, ok, detail="", fix=(), manual=""):
        out.append(
            {
                "group": group,
                "name": name,
                "ok": bool(ok),
                "detail": detail,
                "fix": [] if ok else list(fix),
                "manual": "" if ok else manual,
            }
        )

    core, block = "Ядро", "По блокам"
    add(
        core,
        "Python ≥ 3.10",
        sys.version_info >= (3, 10),
        f"{sys.version.split()[0]} ({sys.executable})",
        manual="нужен Python 3.10+ как python3",
    )

    pm = skill_dir("ppt-master")
    add(
        core,
        "ppt-master (плагин)",
        pm,
        str(pm or ""),
        install_plugin("hugohe3/ppt-master", "ppt-master"),
    )
    if pm:
        req = pm / "requirements.txt"
        miss = missing_packages(req) if req.is_file() else []
        extra = " --break-system-packages" if MAC else ""
        add(
            core,
            "Python-пакеты ppt-master",
            not miss,
            ", ".join(miss) or "все на месте",
            [f'{PY} -m pip install --user{extra} -r "{req}"'],
        )
        dhr = skill_dir("deck-house-rules")
        patched = rules_installed(pm, dhr / "SKILL.md" if dhr else None)
        add(
            core,
            "Правила deck-house-rules в ppt-master",
            patched,
            fix=[f'{PY} "{dhr / "scripts/patch_ppt_master.py"}"'] if dhr else [],
            manual=""
            if dhr
            else "установите плагин preza — в нём навык deck-house-rules",
        )

    reviewer = runtime.roles(host)["reviewer"]
    add(core, f"claudex-loop (ревью с {reviewer})", skill_dir("claudex-loop"),
        manual="подключите общий навык claudex-loop к текущему хосту")
    cli = shutil.which(reviewer)
    add(core, f"{reviewer}: CLI рецензента", cli,
        manual=f"установите CLI рецензента {reviewer}")
    if cli:
        command = [cli, "auth", "status"] if reviewer == "claude" else [cli, "login", "status"]
        code, text = run(command)
        if reviewer == "claude" and code == 0:
            try:
                code = 0 if json.loads(text).get("loggedIn") else 1
            except ValueError:
                code = 1
        add(core, f"{reviewer}: вход рецензента", code == 0,
            "вход подтверждён" if code == 0 else "вход не подтверждён; выполните штатный login",
            manual=f"выполните вход через CLI {reviewer}")
    add(block, "Codex imagegen (Облик)", (CODEX / "skills/.system/imagegen").is_dir(),
        "наличие инструкции; инструмент генерации проверяется в активной сессии",
        manual="используйте сессию Codex с фактически доступным imagegen")
    add(
        core,
        "Microsoft PowerPoint (рендер)",
        powerpoint_found(),
        "scripts/render_pptx.py: PowerPoint COM" if WIN else "scripts/render_pptx.py: AppleScript",
        manual="установите Microsoft PowerPoint (Office 2021 / Microsoft 365)",
    )
    poppler = shutil.which("pdftoppm") and shutil.which("pdffonts")
    add(
        core,
        "poppler (pdftoppm, pdffonts)",
        poppler,
        fix=["brew install poppler"]
        if MAC
        else []
        if WIN
        else ["sudo apt install poppler-utils"],
        manual="установите poppler и добавьте его bin в PATH" if WIN else "",
    )

    mcp = mcp_names(host)
    for name, url, var in (
        ("tavily", "https://mcp.tavily.com/mcp", "TAVILY_API_KEY"),
        ("firecrawl", "https://mcp.firecrawl.dev/v2/mcp", "FIRECRAWL_API_KEY"),
    ):
        ok = any(name in n for n in mcp)
        add(
            block,
            f"{name.capitalize()} MCP (Факты, Референсы)",
            ok,
            detail=f"регистрация {host}; вызов и авторизацию проверяйте в активной сессии",
            fix=[f"claude mcp add -s user -t http {name} {url} -H 'Authorization: Bearer ${{{var}}}'"] if host == "claude" else [],
            manual=f"подключите {name} к {host}; ключи и OAuth остаются локально",
        )
        if host == "claude" and ok and not os.environ.get(var):
            out[-1]["detail"] = (
                f"{var} не видна этому процессу — если MCP берёт ключ из неё, проверьте профиль"
            )
    add(
        block,
        "frontend-slides (Референсы)",
        plugin_key("frontend-slides"),
        fix=install_plugin("zarazhangrui/frontend-slides", "frontend-slides"),
    )
    add(
        block,
        "docx — речь в Word (Речь)",
        skill_dir("docx") or plugin_key("document-skills"),
        fix=install_plugin(
            "anthropics/skills", "document-skills", "anthropic-agent-skills"
        ),
    )
    add(
        block,
        "antiplagiat + avoid-ai-writing-russian (Речь)",
        skill_dir("antiplagiat") and skill_dir("avoid-ai-writing-russian"),
        fix=install_plugin(
            "ormeilu/avoid-ai-writing-russian", "avoid-ai-writing-russian"
        ),
    )
    add(
        block,
        "детектор aiw-ru (Речь)",
        shutil.which("aiw-ru"),
        fix=["uv tool install aiw-ru"] if shutil.which("uv") else [],
        manual=""
        if shutil.which("uv")
        else "поставьте uv (https://docs.astral.sh/uv/), затем: uv tool install aiw-ru",
    )
    add(
        block,
        "grill-me (Идеи)",
        skill_dir("grill-me") or skill_dir("grilling"),
        fix=["claude plugin install mattpocock-skills"],
    )
    add(
        block,
        "to-md (Материалы)",
        plugin_key("to-md") or shutil.which("pandoc"),
        fix=install_plugin("Inhibit0r/to-md", "to-md"),
    )
    return out


def updates():
    """Плагины, у которых в источнике есть коммиты новее установленного."""
    if not shutil.which("git"):
        return []
    markets = load_json(CLAUDE / "plugins/known_marketplaces.json")
    found = []
    for key, rec in installed_plugins().items():
        name, _, market = key.partition("@")
        url = market_url(markets.get(market))
        sha = rec.get("gitCommitSha")
        if name not in RELATED or market in NO_UPDATE_CHECK or not (url and sha):
            continue
        source = markets.get(market, {}).get("source", {})
        ref = source.get("ref") or "HEAD"
        code, text = run(["git", "ls-remote", url, ref], timeout=8)
        head = text.split()[0] if code == 0 and text else ""
        if head and head != sha:
            found.append(
                {
                    "plugin": key,
                    "fix": [
                        f"claude plugin marketplace update {market}",
                        f"claude plugin update {key}",
                    ],
                }
            )
    return found


def report(items, ups):
    print("preza: проверка окружения\n")
    for group in ("Ядро", "По блокам"):
        print(group if group == "Ядро" else "По блокам — нужны только своим блокам")
        for c in (c for c in items if c["group"] == group):
            mark = "✓" if c["ok"] else ("✗" if group == "Ядро" else "·")
            print(f"  {mark} {c['name']:<46} {c['detail']}")
        print()
    if ups:
        print("Обновления (в источнике есть новые коммиты)")
        for u in ups:
            print(f"  ↑ {u['plugin']}")
        print()
    cmds = [cmd for c in items for cmd in c["fix"]] + [
        cmd for u in ups for cmd in u["fix"]
    ]
    manual = [c["manual"] for c in items if c["manual"]]
    if cmds:
        print("Команды для недостающего и обновлений:")
        print("\n".join(f"  {cmd}" for cmd in dict.fromkeys(cmds)))
        print("  После установки: Claude — /reload-plugins; Codex — новый сеанс.\n")
    if manual:
        print("Вручную:")
        print("\n".join(f"  - {m}" for m in manual))


def selftest():
    from tempfile import TemporaryDirectory
    from unittest.mock import patch

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin = root / "plugin/skills"
        personal = root / ".agents/skills"
        for parent, name in (
            (plugin, "deck-house-rules"),
            (personal, "deck-house-rules"),
            (personal, "selftest-fallback"),
        ):
            skill = parent / name
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("fixture", encoding="utf-8")
        with patch.object(runtime, "SKILLS", plugin), patch.dict(globals(), HOME=root):
            assert skill_dir("deck-house-rules") == plugin / "deck-house-rules"
            assert skill_dir("selftest-fallback") == personal / "selftest-fallback"

        pm_skill = root / "SKILL.md"
        rules = plugin / "deck-house-rules/SKILL.md"
        for text, expected in (
            ("deck-house-rules", False),
            (f"ordinary link `{pm_skill}`", False),
            (f"deck-house-rules `{root / 'missing/SKILL.md'}`", False),
            ("deck-house-rules `~nonexistentuser_preza_selftest/SKILL.md`", False),
            (f"deck-house-rules `{rules}` and `$imagegen`", True),
            ("deck-house-rules `~/plugin/skills/deck-house-rules/SKILL.md`", True),
        ):
            pm_skill.write_text(text, encoding="utf-8")
            with patch.dict(os.environ, HOME=tmp, USERPROFILE=tmp):
                assert rules_pointer_exists(pm_skill) is expected, text
                assert rules_pointer_exists(pm_skill, rules) is expected, text
        with patch.object(Path, "expanduser", side_effect=RuntimeError):
            assert not rules_pointer_exists(pm_skill, rules)
        other = personal / "deck-house-rules/SKILL.md"
        pm_skill.write_text(f"deck-house-rules `{other}`", encoding="utf-8")
        assert rules_pointer_exists(
            pm_skill, rules
        )  # та же версия правил в другой установке
        other.write_text("older rules", encoding="utf-8")
        assert rules_pointer_exists(pm_skill)
        assert not rules_pointer_exists(pm_skill, rules)
        pm = root / "pm"
        for rel in POINTER_FILES:
            (pm / rel).parent.mkdir(parents=True, exist_ok=True)
            (pm / rel).write_text(f"deck-house-rules `{rules}`", encoding="utf-8")
        assert rules_installed(pm, rules)
        (pm / POINTER_FILES[2]).write_text("no pointer", encoding="utf-8")
        assert not rules_installed(pm, rules)  # патч прервался на третьем файле
        (pm / POINTER_FILES[2]).write_text(f"deck-house-rules `{other}`", encoding="utf-8")
        assert not rules_installed(pm, rules)  # третий указатель на устаревшие правила
    assert req_name("python-pptx>=0.6.21") == "python-pptx"
    assert (
        req_name("uharfbuzz>=0.50.0 ; sys_platform != 'win32'  # note") == "uharfbuzz"
    )
    assert req_name("  # comment") is None and req_name("") is None
    assert (
        market_url({"source": {"source": "github", "repo": "a/b"}})
        == "https://github.com/a/b.git"
    )
    assert (
        market_url({"source": {"source": "git", "url": "https://x/y.git"}})
        == "https://x/y.git"
    )
    assert market_url(None) is None
    print("selftest ok")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if "--selftest" in sys.argv:
        selftest()
        sys.exit()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=["claude", "codex"])
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        HOST = runtime.resolve_host(args.host)
        items = checks(HOST)
    except (OSError, ValueError) as error:
        if args.json:
            print(json.dumps({"required_ok": False, "error": str(error)}, ensure_ascii=False))
        else:
            print(str(error), file=sys.stderr)
        sys.exit(2)
    ups = [] if args.offline else updates()
    required_ok = all(c["ok"] for c in items if c["group"] == "Ядро")
    if args.json:
        print(json.dumps({"required_ok": required_ok, "runtime": runtime.context(HOST),
                          "checks": items, "updates": ups}, ensure_ascii=False, indent=1))
    else:
        print(f"Хост: {HOST}; независимый рецензент: {runtime.roles(HOST)['reviewer']}")
        report(items, ups)
    sys.exit(0 if required_ok else 1)
