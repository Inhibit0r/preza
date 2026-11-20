"""Start one authorized Orca worker using the selected preza profile."""

import argparse
from pathlib import Path
import subprocess
import sys

from runtime import roles


def command(level, role, title, run=None):
    profiles = roles("codex", level)["worker_profiles"]
    if role not in profiles:
        raise ValueError(f"Role {role} is unavailable for {level}")
    profile = profiles[role]
    cmd = [
        "orca",
        "orchestration",
        "worker-start",
        "--worktree",
        "current",
        "--agent",
        "codex",
        "--model",
        profile["model"],
        "--effort",
        profile["effort"],
        "--spec-file",
        "-",
        "--task-title",
        title,
        "--json",
    ]
    if run:
        cmd.extend(["--run", run])
    return cmd


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--run", help="existing Orca run for this deck")
    args = parser.parse_args()
    try:
        brief = args.brief.read_text(encoding="utf-8").strip()
        if not brief:
            raise ValueError("Empty brief")
        result = subprocess.run(
            command(args.level, args.role, args.title, args.run),
            input=brief.encode("utf-8"),
            check=False,
        )
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")
    sys.exit(result.returncode)
