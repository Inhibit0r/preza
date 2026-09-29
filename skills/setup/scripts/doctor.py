#!/usr/bin/env python3
"""Проверка окружения preza: что установлено, чего не хватает, что можно обновить.

  python3 doctor.py            таблица и команды установки
  python3 doctor.py --json     то же в JSON (для навыка /preza:setup)
  python3 doctor.py --offline  без проверки обновлений по сети
  python3 doctor.py --selftest

Только стандартная библиотека. Код выхода 1 — не хватает обязательного.
"""

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
SKILL_DIRS = [CLAUDE / "skills", HOME / ".agents/skills", CODEX / "skills"]
# Обновления проверяются только у плагинов, от которых зависит preza. Официальный маркетплейс собран
# из чужих репозиториев: его коммит с установленным плагином не сравнить.
RELATED = {"preza", "ppt-master", "frontend-slides", "claudex-loop", "document-skills", "avoid-ai-writing-russian", "to-md"}
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
    """Папка навыка: личная или внутри установленного плагина."""
    for d in SKILL_DIRS:
        if (d / name / "SKILL.md").is_file():
            return d / name
    for rec in installed_plugins().values():
        root = Path(rec.get("installPath", ""))
        for d in (root / name, root / "skills" / name):
            if (d / "SKILL.md").is_file():
                return d
    return None


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


def mcp_names():
    d = load_json(HOME / ".claude.json")
    names = set(d.get("mcpServers", {}))
    for proj in d.get("projects", {}).values():
        names |= set(proj.get("mcpServers", {}))
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


def checks():
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
        "Claude Code CLI",
        shutil.which("claude"),
        manual="установите Claude Code: https://code.claude.com",
    )
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
        patched = "deck-house-rules" in (pm / "SKILL.md").read_text(encoding="utf-8")
        add(
            core,
            "Правила deck-house-rules в ppt-master",
            patched,
            fix=[f'{PY} "{dhr / "scripts/patch_ppt_master.py"}"'] if dhr else [],
            manual=""
            if dhr
            else "установите плагин preza — в нём навык deck-house-rules",
        )

    add(
        core,
        "claudex-loop (ревью с Codex)",
        skill_dir("claudex-loop"),
        fix=install_plugin("chaseai-yt/claudex-loop", "claudex-loop"),
    )
    codex = shutil.which("codex")
    add(core, "Codex CLI", codex, fix=["npm install -g @openai/codex"])
    if codex:
        code, text = run(["codex", "login", "status"])
        add(
            core,
            "Codex: вход выполнен",
            code == 0,
            text.splitlines()[-1] if text else "",
            manual="выполните в терминале: codex login",
        )
        add(
            core,
            "Codex: навык $imagegen",
            (CODEX / "skills/.system/imagegen").is_dir(),
            fix=["npm install -g @openai/codex@latest"],
        )
    add(
        core,
        "Microsoft PowerPoint (рендер)",
        powerpoint_found(),
        "render_pptx.sh работает только на macOS" if not MAC else "",
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

    mcp = mcp_names()
    for name, url, var in (
        ("tavily", "https://mcp.tavily.com/mcp", "TAVILY_API_KEY"),
        ("firecrawl", "https://mcp.firecrawl.dev/v2/mcp", "FIRECRAWL_API_KEY"),
    ):
        ok = any(name in n for n in mcp)
        add(
            block,
            f"{name.capitalize()} MCP (Факты, Референсы)",
            ok,
            fix=[
                f"claude mcp add -s user -t http {name} {url} -H 'Authorization: Bearer ${{{var}}}'"
            ],
            manual=f"ключ положите в переменную {var} в профиле оболочки",
        )
        if ok and not os.environ.get(var):
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
        code, text = run(["git", "ls-remote", url, "HEAD"], timeout=8)
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
        print("  После установки плагинов — /reload-plugins в Claude Code.\n")
    if manual:
        print("Вручную:")
        print("\n".join(f"  - {m}" for m in manual))


def selftest():
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
    items = checks()
    ups = [] if "--offline" in sys.argv else updates()
    required_ok = all(c["ok"] for c in items if c["group"] == "Ядро")
    if "--json" in sys.argv:
        print(
            json.dumps(
                {"required_ok": required_ok, "checks": items, "updates": ups},
                ensure_ascii=False,
                indent=1,
            )
        )
    else:
        report(items, ups)
    sys.exit(0 if required_ok else 1)
