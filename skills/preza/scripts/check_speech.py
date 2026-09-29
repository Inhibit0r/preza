#!/usr/bin/env python3
"""Проверка речи: разделы «## Слайд N. …», объём под хронометраж, запрещённые формулировки, заметки PPTX.

  python3 check_speech.py script.md --slides 13 --words 720-860 [--forbid REGEX] [--pptx deck.pptx]

--forbid ищется в речи, а с --pptx ещё и в видимом тексте слайдов. --pptx сверяет заметки докладчика
каждого слайда с разделом речи (пробелы не учитываются). Самопроверка: python3 check_speech.py --selftest
"""

import argparse
import re
import sys
from pathlib import Path

HEAD = re.compile(r"^## Слайд \d+\..*$", re.M)


def words(text):
    return len(re.findall(r"[\wЁё-]+", text))


def shape_texts(shapes):
    for shape in shapes:
        if hasattr(shape, "shapes"):  # группа
            yield from shape_texts(shape.shapes)
        if shape.has_text_frame:
            yield shape.text_frame.text
        if getattr(shape, "has_table", False) and shape.has_table:
            yield from (cell.text for row in shape.table.rows for cell in row.cells)


def check(text, slides, lo, hi, forbid=None, deck=None):
    """(ошибки, слов по разделам); пустой список ошибок — речь в порядке."""
    secs = HEAD.split(text)[1:]
    per = [words(s) for s in secs]
    errors = []
    if len(secs) != slides:
        errors.append(f"разделов {len(secs)}, слайдов {slides}")
    if not lo <= sum(per) <= hi:
        errors.append(f"слов {sum(per)}, нужно {lo}–{hi}")
    texts = [text]
    if deck is not None:
        if len(deck.slides) != slides:
            errors.append(f"в PPTX {len(deck.slides)} слайдов, ожидалось {slides}")
        for n, (slide, sec) in enumerate(zip(deck.slides, secs), 1):
            notes = (
                slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ""
            )
            if " ".join(notes.split()) != " ".join(sec.split()):
                errors.append(f"слайд {n}: заметки докладчика не совпадают с речью")
            texts += shape_texts(slide.shapes)
    if forbid:
        found = [m.group(0) for t in texts for m in re.finditer(forbid, t, re.I)]
        if found:
            errors.append(f"запрещённые формулировки: {found}")
    return errors, per


def selftest():
    text = "## Слайд 1. А\nРаз два три.\n## Слайд 2. Б\nКак говорилось на лекции, четыре.\n"
    assert check(text, 2, 5, 20) == ([], [3, 5])
    errors, _ = check(text, 3, 1, 2, forbid="лекци")
    assert len(errors) == 3, errors  # число разделов, объём, запрет
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        sys.exit()
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--slides", type=int, required=True)
    ap.add_argument("--words", required=True, help="диапазон слов, например 720-860")
    ap.add_argument("--forbid")
    ap.add_argument("--pptx")
    a = ap.parse_args()
    lo, hi = map(int, a.words.split("-"))
    deck = None
    if a.pptx:
        from pptx import Presentation

        deck = Presentation(a.pptx)
    errors, per = check(Path(a.script).read_text(), a.slides, lo, hi, a.forbid, deck)
    print(f"разделов={len(per)} слов={sum(per)} по слайдам={per}")
    for e in errors:
        print("  -", e)
    sys.exit(1 if errors else 0)
