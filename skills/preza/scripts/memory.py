"""Private Markdown memory. One file per accepted example or explicit preference."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from runtime import memory_root


def remember(root, key, kind, title, tags, evidence, body):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", key):
        raise ValueError("Use a short lowercase key")
    if not body.strip() or not title.strip() or not evidence.strip() or not tags:
        raise ValueError("Title, tags, owner evidence and body are required")
    meta = {
        "kind": kind,
        "title": title,
        "tags": sorted(set(tags)),
        "evidence": evidence,
    }
    header = json.dumps(meta, ensure_ascii=False, sort_keys=True)
    if "-->" in header:
        raise ValueError("Invalid markup in record header")
    content = f"<!-- preza {header} -->\n# {title}\n\n{body.strip()}\n"
    folder = root / "lessons"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{key}.md"
    with tempfile.TemporaryDirectory(dir=folder) as temporary:
        complete = Path(temporary) / "record.md"
        complete.write_text(content, encoding="utf-8")
        try:
            os.link(complete, target)
        except FileExistsError:
            if target.read_text(encoding="utf-8") != content:
                raise ValueError(
                    f"Existing record differs, reconcile the note explicitly: {target}"
                ) from None
    return target


def recall(root, query, kind):
    words = query.casefold().split()
    rows = []
    for path in sorted((root / "lessons").glob("*.md")):
        with path.open(encoding="utf-8") as stream:
            line = stream.readline().rstrip()
        if not line.startswith("<!-- preza ") or not line.endswith(" -->"):
            continue
        meta = json.loads(line[len("<!-- preza ") : -len(" -->")])
        if kind and meta["kind"] != kind:
            continue
        labels = " ".join([meta["title"], *meta["tags"]]).casefold()
        score = sum(word in labels for word in words)
        if score or not words:
            rows.append((score, meta["title"], str(path)))
    return [
        {"title": title, "path": path}
        for _, title, path in sorted(rows, key=lambda r: (-r[0], r[1]))
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    search = actions.add_parser("find")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--kind", choices=["preference", "example"])
    add = actions.add_parser("remember")
    add.add_argument("key")
    add.add_argument("--kind", choices=["preference", "example"], required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--tag", action="append", required=True)
    add.add_argument(
        "--evidence", required=True, help="owner decision or accepted artifact/version"
    )
    args = parser.parse_args()
    try:
        root = memory_root()
        if args.action == "remember":
            print(
                remember(
                    root,
                    args.key,
                    args.kind,
                    args.title,
                    args.tag,
                    args.evidence,
                    sys.stdin.read(),
                )
            )
        else:
            matches = recall(root, args.query, args.kind)
            print(
                json.dumps(
                    {"matches": matches[:6], "total": len(matches)}, ensure_ascii=False
                )
            )
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
