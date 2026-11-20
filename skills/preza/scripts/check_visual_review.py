"""Check the final visual-review receipt and the completeness of reported time series."""

import argparse
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re

from pptx import Presentation


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


def series_errors(item):
    points = item["points"]
    start, end, frequency = item["start"], item["end"], item["frequency"]
    if not points or not item["name"].strip():
        return ["series requires a name and observations"]
    labels = []
    for period, value, source in points:
        labels.append(period)
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not isinstance(source, str)
            or not source.strip()
        ):
            return [f"missing observed value/source for {period}"]
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
        problems.extend(f"slide {number}: {message}" for message in series_errors(item))
    for number, png, row in zip(pages, pngs, rows):
        slide = slides[number - 1]._element
        required = {"composition"}
        if slide.xpath(".//p:pic") or slide.xpath(".//p:bg//a:blip"):
            required.add("image")
        if slide.xpath(".//p:cxnSp"):
            required.add("diagram")
        for shape in slides[number - 1].shapes:
            if not shape.has_chart:
                continue
            for series in shape.chart._chartSpace.xpath(".//c:ser"):
                labels = series.xpath("./c:cat//c:pt/c:v/text()")
                if len(labels) < 2 or not all(
                    re.fullmatch(r"(?:19|20)[0-9]{2}", label) for label in labels
                ):
                    continue
                years = list(map(int, labels))
                if len(set(years)) < 2:
                    continue
                required.add("time_axis")
                span = sorted(years)
                if span[-1] - span[0] + 1 != len(span) or len(set(span)) != len(span):
                    problems.append(f"slide {number}: gap or duplicate in annual chart")
                cached = series.xpath("./c:val//c:pt/c:v/text()")
                candidates = [
                    entry
                    for entry in reported.get(number, [])
                    if entry["frequency"] == "year"
                ]
                if len(cached) != len(labels):
                    problems.append(f"slide {number}: missing chart values")
                else:
                    chart_data = dict(zip(labels, map(float, cached)))
                    for entry in candidates:
                        values = {
                            period: value for period, value, source in entry["points"]
                        }
                        # Percent-formatted workbooks may store 0.61 for a reported 61%.
                        factor = entry.get("chart_multiplier", 1)
                        if values.keys() == chart_data.keys() and all(
                            math.isclose(
                                value,
                                chart_data[period] * factor,
                                rel_tol=1e-8,
                                abs_tol=1e-8,
                            )
                            for period, value in values.items()
                        ):
                            break
                    else:
                        problems.append(
                            f"slide {number}: annual chart data not matched to sourced observations"
                        )
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
