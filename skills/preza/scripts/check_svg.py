#!/usr/bin/env python3
"""Плотность и кегль страниц SVG ppt-master до рендера: ловит то, что иначе правится после показа.

    python3 check_svg.py <svg_output> [--skip 1,12] [--accept 8] [--json]
    python3 check_svg.py --selftest

Холст 1280×720 px = 960×540 pt, поэтому pt = px × 0,75. На странице (кроме --skip; по умолчанию первая и последняя):
- текст мельче 14 px (≈10,5 pt) — ошибка: на проекторе не читается даже сноска;
- больше 40 % знаков мельче 18 px (≈13,5 pt) — ошибка: мелкий основной текст;
- больше 120 слов или больше 24 чисел вне нативных графиков — предупреждение «плотно»: сократи или обоснуй
  в раскадровке (таблица по заданию, тепловая карта) и передай номер в --accept.
Калибровка 27.10.2026 по трём учебным колодам: кегль совпал с замечаниями ревьюеров
(сноски 13 px, основной текст 15–16 px); плотность по числам шумит на таблицах, поэтому не ошибка.
Код выхода 1 — ошибка кегля или непринятая плотность.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree

SVG = "{http://www.w3.org/2000/svg}"
TINY, SMALL, SMALL_SHARE, MAX_WORDS, MAX_NUMBERS = 14, 18, 0.40, 120, 24
NUMBER = re.compile(r"(?<![\w.,])[-+−]?\d+(?:[.,]\d+)?%?")
WORD = re.compile(r"[A-Za-zА-Яа-яЁё][\w-]*")


def font_px(value, inherited):
    if not value:
        return inherited
    m = re.match(r"([\d.]+)\s*(px|pt)?", value)
    if not m:
        return inherited
    return float(m.group(1)) / (0.75 if m.group(2) == "pt" else 1)


def runs(el, size=None, chart=False):
    """(текст, кегль px, внутри нативного графика) для каждого текстового узла страницы."""
    if el.tag == SVG + "metadata":
        return
    size = font_px(el.get("font-size") or _style(el, "font-size"), size)
    chart = chart or el.get("data-pptx-replace-with") == "chart"
    if el.text and el.text.strip() and el.tag in (SVG + "text", SVG + "tspan"):
        yield el.text.strip(), size, chart
    for child in el:
        yield from runs(child, size, chart)
        if (
            child.tail
            and child.tail.strip()
            and el.tag in (SVG + "text", SVG + "tspan")
        ):
            yield child.tail.strip(), size, chart


def _style(el, prop):
    m = re.search(rf"{prop}\s*:\s*([^;]+)", el.get("style") or "")
    return m.group(1) if m else None


def check_page(root, *, dense_ok=False):
    items = list(runs(root, 16))
    found = []
    tiny = sorted({round(s, 1) for t, s, _ in items if s and s < TINY})
    if tiny:
        found.append(f"текст мельче {TINY} px: {tiny}")
    chars = sum(len(t) for t, _, _ in items) or 1
    small = sum(len(t) for t, s, _ in items if s and s < SMALL)
    if small / chars > SMALL_SHARE:
        found.append(f"{small / chars:.0%} знаков мельче {SMALL} px")
    if not dense_ok:
        words = sum(len(WORD.findall(t)) for t, _, _ in items)
        numbers = sum(len(NUMBER.findall(t)) for t, _, chart in items if not chart)
        if words > MAX_WORDS:
            found.append(f"плотно: слов {words} > {MAX_WORDS}")
        if numbers > MAX_NUMBERS:
            found.append(f"плотно: чисел {numbers} > {MAX_NUMBERS}")
    return found


def check(folder, skip=None, accept=()):
    pages = sorted(Path(folder).glob("*.svg"))
    skip = {1, len(pages)} if skip is None else set(skip)
    result = {}
    for no, page in enumerate(pages, 1):
        if no in skip:
            continue
        found = check_page(ElementTree.parse(page).getroot(), dense_ok=no in accept)
        if found:
            result[page.name] = found
    return result


def selftest():
    def page(body):
        return ElementTree.fromstring(
            f'<svg xmlns="http://www.w3.org/2000/svg" font-size="20">{body}</svg>'
        )

    assert (
        check_page(
            page('<text font-size="22">Заголовок</text><text>Текст на двадцать</text>')
        )
        == []
    )
    assert check_page(page('<text font-size="12">Источник: ОЭСР</text>'))[0].startswith(
        "текст мельче"
    )
    assert any(
        "знаков мельче" in f
        for f in check_page(
            page(
                '<g font-size="16"><text>длинный основной текст слайда</text></g><text>А</text>'
            )
        )
    )
    nums = "".join(f"<text>{i},5</text>" for i in range(25))
    assert check_page(page(nums)) == [f"плотно: чисел 25 > {MAX_NUMBERS}"]
    assert check_page(page(nums), dense_ok=True) == []
    chart = f'<g data-pptx-replace-with="chart">{nums}</g>'
    assert check_page(page(chart)) == []  # подписи осей нативного графика не считаются
    meta = '<g><metadata>{"x": 1, "y": 2, "values": [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25]}</metadata><text>Итог</text></g>'
    assert check_page(page(meta)) == []
    assert font_px("12pt", None) == 16
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--skip", help="номера страниц без проверки, через запятую")
    ap.add_argument(
        "--accept", default="", help="страницы с обоснованной плотностью, через запятую"
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.folder:
        ap.error("нужна папка svg_output")
    nums = lambda s: {int(x) for x in s.split(",") if x.strip()}  # noqa: E731
    result = check(
        a.folder, nums(a.skip) if a.skip is not None else None, nums(a.accept)
    )
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for name, fs in result.items():
            print(f"{name}: " + "; ".join(fs))
        print("находок нет" if not result else f"страниц с находками: {len(result)}")
    sys.exit(int(bool(result)))


if __name__ == "__main__":
    main()
