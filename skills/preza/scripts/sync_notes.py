#!/usr/bin/env python3
"""Итоговая речь → заметки проекта ppt-master (notes/total.md), чтобы повторный экспорт их не откатил.

    python3 sync_notes.py <проект ppt-master> script.md
    python3 sync_notes.py --selftest

Раздел `## Слайд N.` пишется в заметку N-й страницы svg_output без промежуточных кадров Morph
(`10b_*.svg`); промежуточный кадр получает заметку своего слайда (`10_*`), потому что total_md_split.py
требует заметку на каждую страницу. Заголовок заметки — имя страницы.
Прежний total.md сохраняется рядом как total.md.bak. Затем — total_md_split.py и экспорт.
"""

import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean_deck import STAGING, order_key  # noqa: E402

HEAD = re.compile(r"^## Слайд \d+\..*$", re.M)
NUMBER = re.compile(r"^\d+")


def sync(project, script_text):
    project = Path(project)
    pages = sorted(
        (p.stem for p in (project / "svg_output").glob("*.svg")), key=order_key
    )
    clean = [p for p in pages if not STAGING.match(p)]
    sections = [s.strip() for s in HEAD.split(script_text)[1:]]
    if len(sections) != len(clean):
        raise ValueError(
            f"разделов речи {len(sections)}, страниц без промежуточных {len(clean)}"
        )
    for n, sec in enumerate(sections, 1):
        heading = next((ln for ln in sec.splitlines() if ln.lstrip().startswith("#")), None)
        if heading:  # total_md_split прочитает её как заголовок заметки и отдаст текст другому слайду
            raise ValueError(f"в разделе слайда {n} строка-заголовок «{heading.strip()}»: уберите «#» из речи")
    text = dict(zip(clean, sections))
    by_number = {}
    for page in clean:
        m = NUMBER.match(page)
        by_number.setdefault(m.group(0) if m else page, page)
    notes, owner = [], None
    for page in pages:
        if page in text:
            owner = page
        else:  # промежуточный кадр: заметка слайда с тем же номером, иначе предыдущего
            m = NUMBER.match(page)
            owner = by_number.get(m.group(0) if m else "", owner)
        notes.append(f"# {page}\n\n{text.get(owner, '')}\n")
    total = project / "notes/total.md"
    total.parent.mkdir(exist_ok=True)
    if total.is_file():
        shutil.copyfile(total, total.with_name("total.md.bak"))
    total.write_text("\n---\n\n".join(notes), encoding="utf-8")
    return clean


def selftest():
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "svg_output").mkdir()
        for name in ("01_a.svg", "02_b.svg", "02b_c.svg"):
            (root / "svg_output" / name).write_text("<svg/>", encoding="utf-8")
        assert sync(root, "## Слайд 1. А\nраз\n## Слайд 2. Б\nдва\n") == [
            "01_a",
            "02_b",
        ]
        total = (root / "notes/total.md").read_text(encoding="utf-8")
        assert (
            total.count("\n---\n") == 2 and total.count("два") == 2
        )  # 02b_c — заметка слайда 02_b
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        sys.exit()
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    try:
        pages = sync(sys.argv[1], Path(sys.argv[2]).read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit(str(e))
    print(
        f"notes/total.md: {len(pages)} разделов речи; дальше total_md_split.py и экспорт"
    )
