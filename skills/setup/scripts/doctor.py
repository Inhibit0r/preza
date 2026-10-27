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


POINTER = ("(deck-house-rules)", "preza:deck-house-rules")  # единый источник текста указателей — форк ppt-master
FORK, FORK_WORKFLOW = "Inhibit0r/ppt-master", "sync-upstream.yml"


def rules_installed(pm):
    """Указатели форка во всех трёх файлах ppt-master: строка с маркером и именем навыка."""
    return all(
        (pm / rel).is_file()
        and any(all(m in line for m in POINTER) for line in (pm / rel).read_text(encoding="utf-8").splitlines())
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


def git_url(value):
    """owner/repo → https://github.com/owner/repo.git; полный адрес — как есть."""
    if value and re.fullmatch(r"[\w.-]+/[\w.-]+", value):
        return f"https://github.com/{value}.git"
    return value


def market_url(entry):
    """git-адрес маркетплейса из known_marketplaces.json или None."""
    src = (entry or {}).get("source", {})
    if src.get("source") == "github" and src.get("repo"):
        return git_url(src["repo"])
    return src.get("url")


def safe_source(url, ref):
    """Только https-адрес и ветка/тег без пробелов и ведущего «-»: значения не становятся опциями git."""
    return bool(url and re.fullmatch(r"https://[\w.-]+/[\w./~-]+", url)
                and re.fullmatch(r"[A-Za-z0-9._/][A-Za-z0-9._/-]*", ref or ""))


def market_plugins(market):
    """Имена плагинов маркетплейса по его клону (маркетплейс удаляется, только если в нём один ppt-master)."""
    data = load_json(CLAUDE / f"plugins/marketplaces/{market}/.claude-plugin/marketplace.json")
    return [p.get("name") for p in data.get("plugins", [])]


def inside_path(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def plugin_source(market, name):
    """(url, ref) источника плагина из marketplace.json клона маркетплейса — для git-subdir/github/url."""
    data = load_json(CLAUDE / f"plugins/marketplaces/{market}/.claude-plugin/marketplace.json")
    for plugin in data.get("plugins", []):
        src = plugin.get("source")
        if plugin.get("name") == name and isinstance(src, dict) and src.get("source") in ("git-subdir", "github", "url"):
            return git_url(src.get("url") or src.get("repo")), src.get("ref") or "HEAD"
    return None


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
    keys = [k for k in installed_plugins() if k.split("@")[0] == "ppt-master"]
    # Codex без Claude: файлы форка кладутся в общую библиотеку навыков, команды claude ему не подходят
    codex_manual = ("клонируйте ветку preza форка https://github.com/Inhibit0r/ppt-master и скопируйте "
                    "skills/ppt-master в ~/.agents/skills/ppt-master (на машине со стеком ~/.agents/stack — через install.py run; "
                    "если потом поставите ppt-master@preza в Claude, эту копию уберите: она перекроет форк)")
    fork_fix = install_plugin("Inhibit0r/preza", "ppt-master", "preza") if host == "claude" else []
    add(core, "ppt-master (плагин)", pm, str(pm or ""), fork_fix, manual="" if host == "claude" else codex_manual)
    # Claude ставит ppt-master из маркетплейса preza; Codex читает найденные файлы — ему достаточно указателей форка
    source = core if host == "claude" else block
    fork = installed_plugins().get("ppt-master@preza", {}).get("installPath")
    add(source, "ppt-master из маркетплейса preza (форк)", "ppt-master@preza" in keys,
        "ppt-master@preza" if "ppt-master@preza" in keys else f"установлено: {', '.join(keys) or 'нет'}", fork_fix,
        manual="" if host == "claude" else codex_manual)
    old = [k for k in keys if k != "ppt-master@preza"]
    removal = [f"claude plugin uninstall {k}" for k in old] + [
        f"claude plugin marketplace remove {m}" for m in {k.split("@")[1] for k in old} if market_plugins(m) == ["ppt-master"]]
    add(source, "без старого источника ppt-master", not old, ", ".join(old), removal if host == "claude" else [],
        manual=("на машине со стеком ~/.agents/stack: после удаления — stack.py sync и ручная правка манифеста; установка — install.py run"
                if host == "claude" else "в Claude Code: " + "; ".join(removal)))
    dev = os.environ.get("PREZA_PPT_MASTER")  # клон форка при разработке — не «личная копия»
    if fork and pm and not inside_path(pm, Path(fork)) and not (dev and inside_path(pm, Path(dev))):
        add(source, "ppt-master берётся из форка", False, f"перекрыт копией {pm}",
            manual=f"уберите или переименуйте личную копию {pm}: она перекрывает ppt-master@preza")
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
        add(source, "Указатели deck-house-rules в ppt-master", rules_installed(pm),
            "указатели приходят из форка; копия без них — не из маркетплейса preza", fork_fix,
            manual="" if host == "claude" else codex_manual)

    add(block, "doubt-driven-development (ревью, необязателен)", skill_dir("doubt-driven-development"),
        "рецензент — свежий субагент хоста; без навыка — промпт из references/hosts.md",
        manual="необязательно: навык doubt-driven-development (addyosmani/agent-skills)")
    if host == "claude":  # картинки из Claude делает codex exec с $imagegen
        cli = shutil.which("codex")
        add(block, "Codex CLI (картинки, Облик)", cli,
            manual="установите Codex CLI: картинки генерирует codex exec с $imagegen")
        if cli:
            code, _ = run([cli, "login", "status"])
            add(block, "Codex: вход (картинки, Облик)", code == 0,
                "вход подтверждён" if code == 0 else "вход не подтверждён",
                manual="выполните codex login")
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
        sha = rec.get("gitCommitSha")
        if name not in RELATED or market in NO_UPDATE_CHECK or not sha:
            continue
        # плагин из другого репозитория (git-subdir: ppt-master@preza из форка) сравнивается со своим источником
        url, ref = plugin_source(market, name) or (
            market_url(markets.get(market)), markets.get(market, {}).get("source", {}).get("ref") or "HEAD")
        if not url:
            continue
        if not safe_source(url, ref):  # адрес и ветка приходят из чужого marketplace.json
            continue
        code, text = run(["git", "-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
                          "ls-remote", "--", url, ref], timeout=8)
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


def fork_sync():
    """Состояние синхронизации форка: (ok, подробность); None — gh недоступен или GitHub не ответил."""
    from datetime import datetime, timezone

    gh = shutil.which("gh")
    if not gh:
        return None
    code, state = run([gh, "api", f"repos/{FORK}/actions/workflows/{FORK_WORKFLOW}", "--jq", ".state"], timeout=10)
    if code:
        return None
    if state != "active":
        return False, f"workflow {state}: gh workflow enable {FORK_WORKFLOW} --repo {FORK}"
    # прогон с конфликтом или красным контрактом тоже success — сбой виден по открытому issue ветки preza
    code_issues, stuck = run([gh, "issue", "list", "--repo", FORK, "--state", "open", "--json", "title",
                              "--jq", '.[] | select(.title | startswith("sync preza ")) | .title'], timeout=10)
    if code_issues:
        return None  # без списка issue застрявшую синхронизацию не отличить от рабочей
    if stuck.strip():
        return False, f"синхронизация остановлена: {stuck.splitlines()[0]} (tools/README.md форка)"
    code_runs, last = run([gh, "api", f"repos/{FORK}/actions/workflows/{FORK_WORKFLOW}/runs?status=success&per_page=1",
                           "--jq", ".workflow_runs[0].updated_at // empty"], timeout=10)
    if code_runs:
        return None
    try:
        when = datetime.fromisoformat(last.strip().replace("Z", "+00:00"))
    except ValueError:
        return False, "успешных прогонов нет"
    age = (datetime.now(timezone.utc) - when).days
    return age <= 14, f"последний успешный прогон {last[:10]} ({age} дн.)"


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
        root = Path(tmp).resolve()  # macOS: /var -> /private/var
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

        pm = root / "pm"
        for rel in POINTER_FILES:
            (pm / rel).parent.mkdir(parents=True, exist_ok=True)
            (pm / rel).write_text("# T\n\n> rule (deck-house-rules): `preza:deck-house-rules`\n", encoding="utf-8")
        assert rules_installed(pm)
        (pm / POINTER_FILES[2]).write_text("mentions deck-house-rules only", encoding="utf-8")
        assert not rules_installed(pm)  # нет маркера в третьем файле
    assert git_url("Inhibit0r/ppt-master") == "https://github.com/Inhibit0r/ppt-master.git"
    assert safe_source("https://github.com/a/b.git", "preza") and safe_source("https://x/y.git", "HEAD")
    responses = {"state": (0, "active"), "issue": (0, ""), "runs": (1, "HTTP 502: Bad Gateway")}
    pick = lambda cmd, timeout=15: responses["issue" if "issue" in cmd else "runs" if any("runs" in c for c in cmd) else "state"]  # noqa: E731
    with patch.object(shutil, "which", return_value="/usr/bin/gh"), patch.dict(globals(), run=pick):
        assert fork_sync() is None  # GitHub не ответил — не падать и не выдумывать вывод
        responses["runs"] = (0, "")
        assert fork_sync() == (False, "успешных прогонов нет")
        responses["issue"] = (0, "sync preza v6.8.0: conflict")
        assert fork_sync()[0] is False
        responses.update(issue=(1, "HTTP 502"), runs=(0, "2099-01-01T00:00:00Z"))
        assert fork_sync() is None  # сбой списка issue — не «зелёный»
    assert not safe_source("--upload-pack=touch x", "HEAD") and not safe_source("https://github.com/a/b.git", "--output=x")
    assert not safe_source("ext::sh -c x", "HEAD") and not safe_source("file:///tmp/r", "HEAD")
    assert git_url("https://x/y.git") == "https://x/y.git"
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
    sync = None if args.offline else fork_sync()
    if not args.offline:
        if sync is None:
            sync = (False, "не проверено: gh недоступен или GitHub не ответил")
        items.append({"group": "По блокам", "name": "синхронизация форка ppt-master", "ok": sync[0],
                      "detail": sync[1], "fix": [], "manual": "" if sync[0] else f"проверьте Actions {FORK}"})
    required_ok = all(c["ok"] for c in items if c["group"] == "Ядро")
    if args.json:
        print(json.dumps({"required_ok": required_ok, "runtime": runtime.context(HOST),
                          "checks": items, "updates": ups}, ensure_ascii=False, indent=1))
    else:
        print(f"Хост: {HOST}; независимый рецензент: {runtime.roles(HOST)['reviewer']}")
        report(items, ups)
    sys.exit(0 if required_ok else 1)
