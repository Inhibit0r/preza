"""Check the final visual-review receipt and the completeness of reported time series."""

import argparse
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re

from pptx import Presentation
from pptx.oxml.ns import qn

from check_speech import norm


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ordinal(label, frequency):
    patterns = {
        "year": r"(\d{4})",
        "quarter": r"(\d{4})-Q([1-4])",
        "month": r"(\d{4})-(0[1-9]|1[0-2])",
    }
    if frequency == "day":
        return date.fromisoformat(label).toordinal()
    match = re.fullmatch(patterns[frequency], label)
    if not match:
        raise ValueError(f"Invalid {frequency} period: {label}")
    year = int(match[1])
    if frequency == "year":
        return year
    step = 4 if frequency == "quarter" else 12
    return year * step + int(match[2]) - 1


def series_errors(item, notes=None):
    points = item["points"]
    start, end, frequency = item["start"], item["end"], item["frequency"]
    if not points or not item["name"].strip():
        return ["series requires a name and observations"]
    labels = []
    gaps = item.get("gap_notes", {})
    missing = {period for period, value, source in points if value is None}
    if not isinstance(gaps, dict) or missing != gaps.keys():
        return ["each blank needs a spoken explanation and only blanks may have one"]
    if len(missing) == len(points):
        return ["series has no observed value"]
    for period, value, source in points:
        labels.append(period)
        if not isinstance(source, str) or not source.strip():
            return [f"missing source for {period}"]
        if value is None:
            reason = gaps[period]
            if not isinstance(reason, str) or not reason.strip():
                return [f"missing explanation for {period}"]
            if notes is not None and norm(reason) not in norm(notes):
                return [
                    f"explanation for {period} is absent from this slide's speaker notes"
                ]
        elif type(value) not in (int, float) or not math.isfinite(value):
            return [f"invalid observed value for {period}"]
    if labels[0] != start or labels[-1] != end or len(labels) != len(set(labels)):
        return ["missing boundary or duplicate period"]
    if frequency == "custom":
        if labels != item["expected"]:
            return ["custom period roster differs from observations"]
    else:
        indices = [ordinal(label, frequency) for label in labels]
        if any(b != a + 1 for a, b in zip(indices, indices[1:])):
            return ["gap in period roster"]
    return []


def calendar_frequency(labels):
    for frequency, pattern in (
        ("year", r"(?:19|20)[0-9]{2}"),
        ("quarter", r"[0-9]{4}-Q[1-4]"),
        ("month", r"[0-9]{4}-[0-9]{2}"),
        ("day", r"[0-9]{4}-[0-9]{2}-[0-9]{2}"),
    ):
        if len(labels) >= 2 and all(re.fullmatch(pattern, label) for label in labels):
            return frequency
    return None


def chart_errors(series, entries, blanks_mode):
    # PowerPoint omits c:pt for blank cells; its idx still denotes the original category.
    categories = series.xpath("./c:cat//c:pt")
    labels = [p.findtext(qn("c:v"), "") for p in categories]
    frequency = calendar_frequency(labels)
    if frequency is None:
        # Fiscal years and other custom calendars are identified by their declared category labels.
        if not any(
            e["frequency"] == "custom" and e["expected"] == labels for e in entries
        ):
            return None
        frequency = "custom"
    indexed = {int(p.get("idx")): label for p, label in zip(categories, labels)}
    category_count = series.xpath("./c:cat//c:ptCount/@val")
    if (
        set(indexed) != set(range(len(labels)))
        or category_count
        and int(category_count[0]) != len(labels)
    ):
        return ["missing or duplicate category index"]
    periods = [indexed[i] for i in range(len(labels))]
    if frequency != "custom":
        indices = [ordinal(label, frequency) for label in periods]
        if not (
            all(b == a + 1 for a, b in zip(indices, indices[1:]))
            or all(b == a - 1 for a, b in zip(indices, indices[1:]))
        ):
            return ["gap or duplicate on the calendar axis"]
    values = dict.fromkeys(periods)
    seen = set()
    for pt in series.xpath("./c:val//c:pt"):
        idx = int(pt.get("idx"))
        if idx not in indexed or idx in seen:
            return ["invalid or duplicate chart value index"]
        seen.add(idx)
        text = pt.findtext(qn("c:v"), "").strip()
        if text:
            values[indexed[idx]] = float(text)
    if None in values.values() and blanks_mode != "gap":
        return ["empty cells must display as gaps"]
    for entry in entries:
        if entry["frequency"] != frequency:
            continue
        points = {period: value for period, value, source in entry["points"]}
        if points.keys() != values.keys():
            continue
        factor = entry.get("chart_multiplier", 1)
        if all(
            (expected is None and values[period] is None)
            or (
                type(expected) in (int, float)
                and values[period] is not None
                and math.isclose(
                    expected, values[period] * factor, rel_tol=1e-8, abs_tol=1e-8
                )
            )
            for period, expected in points.items()
        ):
            return []
    return ["chart values or blanks do not match sourced observations"]


def verify(deck, render, receipt):
    slides = list(Presentation(deck).slides)
    pages = list(range(1, len(slides) + 1))
    pngs = sorted(render.glob("slide-*.png"), key=lambda f: int(f.stem.split("-")[-1]))
    if len(pngs) != len(pages):
        pages = [i for i in pages if slides[i - 1]._element.get("show") != "0"]
    if len(pages) != len(pngs) or not pages:
        return ["slide/render count mismatch"]
    problems = []
    if receipt["deck_sha256"] != digest(deck):
        problems.append("deck changed since receipt")
    rows = receipt["slides"]
    if [row["slide"] for row in rows] != pages:
        return problems + ["review must cover final rendered pages in order"]
    reported = {}
    for item in receipt["series"]:
        number = item["slide"]
        if number not in pages:
            problems.append(f"series points to absent slide {number}")
        reported.setdefault(number, []).append(item)
        if number in pages:
            page = slides[number - 1]
            frame = page.notes_slide.notes_text_frame if page.has_notes_slide else None
            notes = frame.text if frame is not None else ""
            problems.extend(f"slide {number}: {message}" for message in series_errors(item, notes))
    for number, png, row in zip(pages, pngs, rows):
        slide = slides[number - 1]._element
        required = {"composition"}
        if slide.xpath(".//p:pic") or slide.xpath(".//p:bg//a:blip"):
            required.add("image")
        if slide.xpath(".//p:cxnSp"):
            required.add("diagram")
        if slide.xpath(".//a:tbl"):
            required.add("table")
        for ref in slide.xpath(".//c:chart[@r:id]"):
            chart = slides[number - 1].part.related_part(ref.get(qn("r:id")))._element
            mode = chart.xpath("./c:chart/c:dispBlanksAs/@val") or ["gap"]
            for series in chart.xpath(".//c:ser"):
                findings = chart_errors(series, reported.get(number, []), mode[0])
                if findings is not None:
                    required.add("time_axis")
                    problems.extend(f"slide {number}: {error}" for error in findings)
        if number in reported:
            required.add("time_axis")
        if row["png_sha256"] != digest(png):
            problems.append(f"slide {number}: PNG changed since review")
        if row["verdict"] != "APPROVED" or not re.fullmatch(
            r"ctx_[\w-]+", row["reviewer"]
        ):
            problems.append(f"slide {number}: missing independent approval")
        for key in required:
            value = row["checks"].get(key)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"slide {number}: missing {key} observation")
    return problems


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck", type=Path)
    parser.add_argument("render", type=Path)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        errors = verify(
            args.deck, args.render, json.loads(args.receipt.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(1, f"Invalid visual-review inputs: {error}\n")
    if errors:
        parser.exit(1, "\n".join(errors) + "\n")
    print("Visual review receipt matches the final artifacts.")
