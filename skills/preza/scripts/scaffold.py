#!/usr/bin/env python3
"""Папки работы preza: где запущена сессия, каркас предмета, папка задания, порядок в ней.

    python3 scaffold.py find [<папка запуска>]
    python3 scaffold.py init <папка> --kind subject|company [--host claude|codex]
    python3 scaffold.py work <корень> [--series S] [--task T]
    python3 scaffold.py check <папка задания>
    python3 scaffold.py --selftest

Устройство папок — references/layout.md. Файлы не перемещаются, не переименовываются и не удаляются;
существующий текст не переписывается — дописывается раздел или блок в конец.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

LAYOUT = "1.3.5"
SRC = "Исходники"
STAGES = ("1-вход", "2-материалы", "3-речь", "4-сборка", "5-проверка", "6-архив")
KEYS = ("input", "materials", "speech", "build", "check", "archive")
MEMORY = {"subject": "КУРС.md", "company": "БРЕНД.md"}
SERIES_MEMORY = "ПРОЕКТ.md"
# первое имя создаётся, остальные — уже принятые у пользователя
FOLDERS = {
    "subject": (("Лекции",), ("Задания", "Задание"), ("Материалы",)),
    "company": (("Материалы",), ("Бренд",)),
}
CONTEXT_DIRS = {"Лекции", "Задания", "Задание", "Материалы", "Конспекты", "Бренд"}
SECTION = "## Презентации"
SECTION_RE = re.compile(r"^## Презентации\s*$", re.M)  # «## Презентации курса» — чужой раздел
BAD_NAME = re.compile(r'[/\\:*?"<>|]|\.\.|^[.\s]|\s$')
TEMPLATES = {
    "КУРС.md": ("Требования к сдаче", "Имена файлов", "Решения владельца"),
    "БРЕНД.md": (
        "Фирменные константы",
        "Требования к сдаче",
        "Имена файлов",
        "Решения владельца",
    ),
    SERIES_MEMORY: (
        "Кто",
        "Про что",
        "Облик серии",
        "Сквозные числа",
        "Решения владельца",
    ),
}
START, END = "<!-- preza:start -->", "<!-- preza:end -->"
COMMAND = {"claude": "/preza:preza", "codex": "$preza:preza"}
BLOCK = (
    f"{START}\n## Презентации (preza)\n"
    "Презентации по этой папке делаются через `{command}`, запуск отсюда. "
    "Структура: `<Серия>/<Задание>/` — сверху сдача и `PLAN.md`, рабочее в `Исходники/` (1-вход … 6-архив). "
    "Память: `{memory}` здесь и `ПРОЕКТ.md` в папке серии. "
    f"Дорабатывая готовую работу без preza, сначала прочитай её `PLAN.md`.\n{END}\n"
)
PROJECT = re.compile(r"_ppt\d+_\d{8}")  # папка проекта ppt-master: <имя>_ppt169_20261027
PROJECT_MARKS = ("svg_output", "design_spec.md", "spec_lock.md")  # без формата в имени — по содержимому
TRACES = {
    "script.md",
    "runtime.json",
    "render",
    "notes",
}  # след старой плоской работы preza рядом с PLAN.md
# имена файлов preza, которым место в Исходники/ (файлы пользователя в корне задания — не находка)
KNOWN = {
    "runtime.json",
    "script.md",
    "notes",
    "render",
    "data",
    "research",
    "backup",
    "images",
    "svg_output",
    "exports",
}


def nfc(name):
    return unicodedata.normalize(
        "NFC", name
    )  # macOS хранит «й» и «ё» в именах разложенными


def visible(folder):
    return [p for p in folder.iterdir() if not p.name.startswith((".", "~$", "__"))]


def read_json(path, strict=False):
    """Объект JSON из файла; нет файла — {}. Битый файл — {}, а при strict — ошибка: preza его не перезаписывает."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        if strict:
            raise ValueError(f"{path}: не читается как JSON ({error}) — проверь файл, preza его не перезаписывает") from error
        return {}
    if not isinstance(data, dict):
        if strict:
            raise ValueError(f"{path}: ожидался объект JSON — проверь файл, preza его не перезаписывает")
        return {}
    return data


def is_work(folder):
    return "layout" in read_json(folder / SRC / "runtime.json")


def is_project(path):
    return path.is_dir() and bool(
        PROJECT.search(path.name) or any((path / m).exists() for m in PROJECT_MARKS)
    )


def has_trace(d):
    return (d / "PLAN.md").is_file() and any(
        nfc(p.name) in TRACES or is_project(p) for p in visible(d)
    )


def legacy_dir(folder, deep=False):
    """Папка старой работы preza (PLAN.md и след preza): сама folder или её «Исходники…» («Исходники v2») —
    из нескольких с самым свежим PLAN.md; при deep, если их нет, — `<Задание>/work/` (стратмаркетинг).
    Другие подпапки не смотрим: там копии и образцы пользователя."""
    if not folder.is_dir():
        return None
    subs = [p for p in visible(folder) if p.is_dir() and nfc(p.name).startswith(SRC)]
    found = [d for d in (folder, *subs) if has_trace(d)]
    if not found and deep and has_trace(folder / "work"):
        return folder / "work"
    # при равном времени — сама папка, затем по имени: выбор не зависит от порядка каталога
    return max(
        found,
        key=lambda d: ((d / "PLAN.md").stat().st_mtime, d == folder, nfc(d.name)),
        default=None,
    )


def task_kind(folder, deep=False):
    if is_work(folder):
        return "work"
    return "legacy" if legacy_dir(folder, deep) else "other"


def memory_root(folder, levels):
    """(kind, папка с файлом памяти) в folder или до levels уровней выше; ближайший побеждает."""
    for p in [folder, *folder.parents][: levels + 1]:
        for kind, name in MEMORY.items():
            if (p / name).is_file():
                return kind, p
    return None, None


def list_series(root):
    series = {}
    for p in sorted(visible(root)):
        if not p.is_dir() or nfc(p.name) in CONTEXT_DIRS or nfc(p.name) == SRC:
            continue
        tasks = {
            nfc(t.name): task_kind(t, deep=True) for t in sorted(visible(p)) if t.is_dir()
        }
        if (kind := task_kind(p)) != "other":
            # серия — сама работа: заданиями считаются только новые папки заданий рядом с её файлами
            series[nfc(p.name)] = {
                "kind": kind,
                "tasks": {k: v for k, v in tasks.items() if v == "work"},
            }
        else:
            series[nfc(p.name)] = {"tasks": tasks}
    return series


def located(kind, folder):
    """memory — вид файла памяти (subject|company|None); series_dir — папка серии работы (None — работа в корне или вне предмета)."""
    task = folder.parent if nfc(folder.name).startswith(SRC) else folder  # старая работа в «Исходники…»
    memory, root = memory_root(task.parent, 2)  # <корень>/<серия>/<задание>[/work — старая работа]
    parts = task.relative_to(root).parts if root else ()
    # старая работа прямо в корне предмета — сама серия (там же ПРОЕКТ.md, который кладёт work)
    series = root / parts[0] if len(parts) > 1 or (kind == "legacy" and parts) else None
    return {
        "kind": kind,
        "work": str(folder),
        "root": str(root) if root else None,
        "memory": memory,
        "series_dir": str(series) if series else None,
    }


def find(start="."):
    start = Path(start).resolve()
    memory, root = memory_root(start, 2)
    parts = start.relative_to(root).parts if root else ()
    # старую работу в подпапке (`<Задание>/work/`) ищем только у папки задания: у предмета и серии подпапки — серии и задания
    deep = len(parts) >= 2
    # запуск изнутри Исходники/4-сборка/<проект>/.review/backup — та же работа
    for p in [start, *start.parents][:7]:
        if is_work(p):
            return located("work", p)
        if old := legacy_dir(p, deep=deep and p == start):
            return located("legacy", old)
    if root is None:
        return {"kind": "none", "root": str(start)}
    here = "" if not parts or nfc(parts[0]) in CONTEXT_DIRS else nfc("/".join(parts))
    return {
        "kind": memory,
        "root": str(root),
        "here": here,
        "series_dir": str(root / parts[0]) if here else None,
        "series": list_series(root),
    }


def ensure_memory(path, title):
    body = SECTION + "\n\n" + "".join(f"### {s}\n\n" for s in TEMPLATES[path.name])
    try:
        with path.open(
            "x", encoding="utf-8"
        ) as f:  # «x»: параллельная сессия не затрёт уже созданный
            f.write(f"# {title}\n\n{body}")
        return
    except FileExistsError:
        pass
    text = path.read_text(encoding="utf-8")
    if not SECTION_RE.search(text):
        with path.open("a", encoding="utf-8") as f:
            f.write(("\n" if text.endswith("\n") else "\n\n") + body)


def append_block(path, memory, host):
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if START in text:
        return
    block = BLOCK.replace("{command}", COMMAND[host]).replace("{memory}", memory)
    with path.open("a", encoding="utf-8") as f:
        f.write(("" if not text else "\n" if text.endswith("\n") else "\n\n") + block)


def init(root, kind, host="claude"):
    root = Path(root)
    for p in visible(root):
        if p.is_dir() and any((p / name).is_file() for name in MEMORY.values()):
            raise ValueError(
                f"в «{nfc(p.name)}» уже есть память предмета: «{nfc(root.name)}» — папка с предметами, а не предмет"
            )
    ensure_memory(root / MEMORY[kind], nfc(root.name))
    for names in FOLDERS[kind]:
        if not any((root / n).is_dir() for n in names):
            (root / names[0]).mkdir()
    append_block(
        root / ("AGENTS.md" if host == "codex" else "CLAUDE.md"), MEMORY[kind], host
    )


def names_key(name):
    return frozenset(
        w.strip().lower() for w in re.split(r"\+|,|\sи\s", nfc(name)) if w.strip()
    )


def resolve_series(root, series):
    """Существующая папка серии с теми же именами в любом порядке («Петров + Иванов» = «Иванов + Петров»)."""
    key = names_key(series)
    for p in visible(root):
        if p.is_dir() and names_key(p.name) == key:
            return p
    return root / series


def valid_name(name):
    if not name or BAD_NAME.search(name):
        raise ValueError(
            f"имя «{name}» не годится для папки: без / \\ : * ? \" < > |, «..», точки и пробела по краям"
        )


def work(root, series=None, task=None):
    root = Path(root).resolve()
    for name in (series, task):
        if name is not None:
            valid_name(name)
    if memory_root(root, 0)[0] and not (series and task):
        raise ValueError("корень предмета или компании: нужны --series и --task")
    sdir = resolve_series(root, series) if series else root
    base = sdir / task if task else sdir
    # проверки до любой записи: старую работу не трогаем, битый runtime.json не перезаписываем, ПРОЕКТ.md не создаём зря
    if base.is_dir():
        read_json(base / SRC / "runtime.json", strict=True)
    # подпапки — только у папки задания: у отдельной папки они могут быть чужими работами
    if base.exists() and not is_work(base) and (old := legacy_dir(base, deep=bool(task))):
        raise ValueError(
            f"{base} — старая работа (её PLAN.md — в {old}): продолжай по старым путям (layout.md), структуру создаст миграция"
        )
    if not (series or task) and not is_work(base) and visible(base):
        raise ValueError(
            f"{base} не пуста — передай --task <тема кратко>: работа получит свою подпапку"
        )
    if series:  # серия — старая плоская работа: новое задание и ПРОЕКТ.md — рядом с её файлами, их не трогаем
        sdir.mkdir(exist_ok=True)
        ensure_memory(sdir / SERIES_MEMORY, nfc(sdir.name))
    src = base / SRC
    for s in STAGES:
        (src / s).mkdir(parents=True, exist_ok=True)
    paths = {
        "work": str(base),
        "src": str(src),
        **{k: str(src / s) for k, s in zip(KEYS, STAGES)},
    }
    runtime = src / "runtime.json"
    data = read_json(runtime)  # окружение runtime.py сохраняется, пути обновляются
    data.update(layout=LAYOUT, paths=paths)
    runtime.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def check(folder):
    """Находки порядка в корне папки задания 1.3.5; None — не она (старая работа, чужая папка), проверки нет."""
    folder = Path(folder)
    if not is_work(folder):
        return None
    found = [f"нет {SRC}/{s}" for s in STAGES if not (folder / SRC / s).is_dir()]
    for p in sorted(visible(folder)):
        if nfc(p.name) in KNOWN or is_project(p):
            found.append(f"файл preza не на месте: {nfc(p.name)} → {SRC}/ (layout.md)")
    return found


def selftest():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp).resolve()
        subject = tmp / "Предмет"
        subject.mkdir()
        assert find(subject)["kind"] == "none"
        (subject / "Задание").mkdir()
        (subject / "CLAUDE.md").write_text("# Свои правила\n", encoding="utf-8")
        init(subject, "subject")
        snapshot = {p: p.read_text(encoding="utf-8") for p in subject.glob("*.md")}
        init(subject, "subject")  # повторный запуск ничего не меняет
        assert snapshot == {
            p: p.read_text(encoding="utf-8") for p in subject.glob("*.md")
        }
        assert not (subject / "Задания").exists() and (subject / "Лекции").is_dir()
        claude = (subject / "CLAUDE.md").read_text(encoding="utf-8")
        assert (
            claude.startswith("# Свои правила\n")
            and claude.count(START) == 1
            and "/preza:preza" in claude
        )
        try:
            init(tmp, "subject")
            raise AssertionError("папка с предметами — не предмет")
        except ValueError:
            pass
        paths = work(subject, "Иванов + Петров", "ДЗ-4")
        assert (
            Path(paths["speech"]).is_dir()
            and (subject / "Иванов + Петров" / SERIES_MEMORY).is_file()
        )
        runtime = Path(paths["src"]) / "runtime.json"
        runtime.write_text(
            json.dumps({**read_json(runtime), "host": "claude"}), encoding="utf-8"
        )
        assert (
            work(subject, "Петров + Иванов", "ДЗ-4") == paths
        )  # пара в другом порядке — та же серия
        assert (
            read_json(runtime)["host"] == "claude"
            and read_json(runtime)["layout"] == LAYOUT
        )
        nested = Path(paths["build"]) / "проект" / "svg_output"
        nested.mkdir(parents=True)
        assert find(nested) == find(paths["work"]) and find(nested)["root"] == str(
            subject
        )
        found = find(subject)
        assert found["kind"] == "subject" and found["series"]["Иванов + Петров"][
            "tasks"
        ] == {"ДЗ-4": "work"}
        assert (
            find(subject / "Иванов + Петров")["here"] == "Иванов + Петров"
            and find(subject / "Лекции")["here"] == ""
        )
        task = Path(paths["work"])
        for name in ("Тема_Иванов_Петров.pptx", "~$Тема_Иванов_Петров.pptx", "Анкета.md"):
            (task / name).write_text("", encoding="utf-8")
        (task / "work").mkdir()  # рабочая папка другого конвейера пользователя
        assert check(task) == []
        (task / "notes").mkdir()
        assert check(task) == ["файл preza не на месте: notes → Исходники/ (layout.md)"]
        try:
            work(subject)
            raise AssertionError("корень предмета без серии и задания")
        except ValueError:
            pass
        old = subject / "Долг"
        (old / "notes").mkdir(parents=True)
        (old / "PLAN.md").write_text("", encoding="utf-8")
        assert (
            find(old)["kind"] == "legacy"
            and find(subject)["series"]["Долг"]["kind"] == "legacy"
        )
        moved = (
            subject / "Реферат" / SRC
        )  # старая работа, которую пользователь сам убрал в Исходники/
        (moved / "dag_ppt169_20261020").mkdir(parents=True)
        (moved / "PLAN.md").write_text("", encoding="utf-8")
        assert (
            find(subject / "Реферат") == find(moved) and find(moved)["kind"] == "legacy"
        )
        assert find(moved)["work"] == str(moved) and check(subject / "Реферат") is None
        word = (
            subject / "Мое" / "ДЗ-4 оркестр"
        )  # конвейер Word с PLAN.md — не работа preza
        word.mkdir(parents=True)
        (word / "PLAN.md").write_text("", encoding="utf-8")
        (word / "STATE.md").write_text("", encoding="utf-8")
        assert find(word)["series_dir"] == str(subject / "Мое")
        assert find(word)["kind"] == "subject" and find(subject)["series"]["Мое"][
            "tasks"
        ] == {"ДЗ-4 оркестр": "other"}
        for target in (old, subject / "Реферат"):
            try:
                work(target)
                raise AssertionError("старую плоскую работу work не трогает")
            except ValueError:
                pass
        pair = subject / "Анна + Ольга"  # серия — сама старая плоская работа
        (pair / "notes").mkdir(parents=True)
        (pair / "PLAN.md").write_text("старый план", encoding="utf-8")
        new = Path(work(subject, "Ольга + Анна", "Тема 2")["work"])
        assert new == pair / "Тема 2" and (pair / "PLAN.md").read_text(encoding="utf-8") == "старый план"
        assert find(subject)["series"]["Анна + Ольга"] == {"kind": "legacy", "tasks": {"Тема 2": "work"}}
        assert find(pair)["series_dir"] == str(pair)  # старая работа в корне предмета — сама серия
        assert find(new)["series_dir"] == str(pair) and find(new)["root"] == str(subject)
        assert find(paths["work"])["series_dir"] == str(subject / "Иванов + Петров")
        dz = subject / "Мое 2" / "ДЗ-3"  # старая работа в <Задание>/work/ (стратмаркетинг)
        (dz / "work" / "deck_20261008" / "svg_output").mkdir(parents=True)
        (dz / "work" / "PLAN.md").write_text("", encoding="utf-8")
        assert find(subject)["series"]["Мое 2"]["tasks"] == {"ДЗ-3": "legacy"}
        got = find(dz)
        assert got["kind"] == "legacy" and got["work"] == str(dz / "work") and got["root"] == str(subject)
        assert got["series_dir"] == str(subject / "Мое 2") and got["memory"] == "subject"
        inside = find(dz / "work" / "deck_20261008" / "svg_output")  # три уровня ниже предмета — память предмета та же
        assert inside["root"] == str(subject) and inside["work"] == str(dz / "work")
        try:
            work(subject, "Мое 2", "ДЗ-3")
            raise AssertionError("задание со старой работой в work/")
        except ValueError:
            pass
        assert not (dz / SRC).exists()
        try:  # папка с чужими старыми работами в подпапках — не старая работа, а «передай --task»
            work(subject / "Мое 2")
            raise AssertionError("непустая папка без --task")
        except ValueError as error:
            assert "--task" in str(error), error
        copy = subject / "Мое 2" / "ДЗ-5"  # копия пользователя с более свежим PLAN.md не перехватывает работу
        (copy / "notes").mkdir(parents=True)
        (copy / "PLAN.md").write_text("", encoding="utf-8")
        os.utime(copy / "PLAN.md", (time.time() - 3600, time.time() - 3600))
        (copy / "backup_v1" / "notes").mkdir(parents=True)
        (copy / "backup_v1" / "PLAN.md").write_text("", encoding="utf-8")
        assert find(copy)["work"] == str(copy)
        sample = subject / "Мое 2" / "ДЗ-6"  # образец прошлой работы внутри нового задания
        (sample / "ДЗ-5 образец" / "notes").mkdir(parents=True)
        (sample / "ДЗ-5 образец" / "PLAN.md").write_text("", encoding="utf-8")
        assert find(sample)["kind"] == "subject" and Path(work(subject, "Мое 2", "ДЗ-6")["work"]) == sample
        two = subject / "Реферат 4"  # две папки «Исходники…»: берётся та, где PLAN.md свежее
        for name, age in (("Исходники и проверка", 86400), ("Исходники v2", 0)):
            (two / name / "notes").mkdir(parents=True)
            plan = two / name / "PLAN.md"
            plan.write_text("", encoding="utf-8")
            os.utime(plan, (time.time() - age, time.time() - age))
        assert find(two)["work"] == str(two / "Исходники v2")
        same = time.time() - 7200  # одинаковое время — выбор по правилу, а не по порядку каталога
        for name in ("Исходники и проверка", "Исходники v2"):
            os.utime(two / name / "PLAN.md", (same, same))
        assert find(two)["work"] == str(two / max(("Исходники и проверка", "Исходники v2")))
        broken = subject / "Иванов + Петров" / "ДЗ-5"  # битый runtime.json: ошибка, а не «передай --task»
        (broken / SRC).mkdir(parents=True)
        (broken / SRC / "runtime.json").write_text("[", encoding="utf-8")
        try:
            work(broken)
            raise AssertionError("битый runtime.json")
        except ValueError as error:
            assert "runtime.json" in str(error)
        assert (broken / SRC / "runtime.json").read_text(encoding="utf-8") == "["
        stale = subject / "Долг 2" / "доработка"  # задание — старая работа: отказ до записи ПРОЕКТ.md
        (stale / "notes").mkdir(parents=True)
        (stale / "PLAN.md").write_text("", encoding="utf-8")
        for bad in (("Долг 2", "доработка"), ("../x", "т"), ("Мое", "Доходы/расходы"), ("Мое", ".скрытая")):
            try:
                work(subject, *bad)
                raise AssertionError(bad)
            except ValueError:
                pass
        assert not (subject / "Долг 2" / SERIES_MEMORY).exists() and not (tmp / "x").exists()
        v2 = subject / "Реферат 1" / "Исходники v2"  # старая работа, убранная в «Исходники v2»
        (v2 / "notes").mkdir(parents=True)
        (v2 / "PLAN.md").write_text("", encoding="utf-8")
        assert find(subject / "Реферат 1")["kind"] == "legacy" and find(v2)["work"] == str(v2)
        dated = subject / "Реферат 3"  # проект ppt-master без формата в имени — по содержимому
        (dated / "deck_20261020" / "svg_output").mkdir(parents=True)
        (dated / "PLAN.md").write_text("", encoding="utf-8")
        assert find(dated)["kind"] == "legacy"
        deep = Path(paths["build"]) / "проект" / ".review" / "backup"
        deep.mkdir(parents=True)
        assert find(deep)["kind"] == "work"
        course = tmp / "Курс 2"  # чужой раздел «## Презентации курса» — свой раздел всё равно дописывается
        course.mkdir()
        (course / "КУРС.md").write_text("# Курс\n\n## Презентации курса\n", encoding="utf-8")
        init(course, "subject")
        assert len(SECTION_RE.findall((course / "КУРС.md").read_text(encoding="utf-8"))) == 1
        brand = tmp / "Компания"
        brand.mkdir()
        init(brand, "company")
        assert find(brand)["kind"] == "company" and (brand / "Бренд").is_dir()
        own = tmp / "Личное"
        own.mkdir()
        (own / "заметка.txt").write_text("", encoding="utf-8")
        try:
            work(own)
            raise AssertionError("непустая папка без --task")
        except ValueError:
            pass
        assert Path(work(own, task="Питч")["work"]) == own / "Питч"
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("find")
    p.add_argument("folder", nargs="?", default=".")
    p = sub.add_parser("init")
    p.add_argument("folder")
    p.add_argument("--kind", choices=MEMORY, required=True)
    p.add_argument("--host", choices=COMMAND, default="claude")
    p = sub.add_parser("work")
    p.add_argument("folder")
    p.add_argument("--series")
    p.add_argument("--task")
    p = sub.add_parser("check")
    p.add_argument("folder")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    try:
        if a.cmd == "find":
            print(json.dumps(find(a.folder), ensure_ascii=False, indent=2))
        elif a.cmd == "init":
            init(a.folder, a.kind, a.host)
            print(json.dumps(find(a.folder), ensure_ascii=False, indent=2))
        elif a.cmd == "work":
            print(
                json.dumps(
                    work(a.folder, a.series, a.task), ensure_ascii=False, indent=2
                )
            )
        elif a.cmd == "check":
            found = check(a.folder)
            if found is None:
                print(
                    "не папка задания 1.3.5 (старая работа или чужая папка): проверка порядка не идёт"
                )
            for f in found or []:
                print("  -", f)
            sys.exit(1 if found else 0)
        else:
            ap.print_help()
    except (OSError, ValueError) as error:
        ap.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
