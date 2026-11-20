"""Install the pinned PPT Master checkout and requirements in this Python's private venv."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "preza/scripts"))
from runtime import ENGINE_REPO, ENGINE_REVISION, engine_checkout, venv_python


def obtain_engine():
    target = engine_checkout()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with tempfile.TemporaryDirectory(dir=target.parent) as scratch:
            candidate = Path(scratch) / "checkout"
            subprocess.run(["git", "init", "-q", str(candidate)], check=True)
            git = ["git", "-C", str(candidate)]
            subprocess.run([*git, "remote", "add", "origin", ENGINE_REPO], check=True)
            subprocess.run(
                [*git, "config", "remote.origin.promisor", "true"], check=True
            )
            subprocess.run(
                [*git, "config", "remote.origin.partialclonefilter", "blob:none"],
                check=True,
            )
            subprocess.run(
                [*git, "sparse-checkout", "set", "skills/ppt-master"], check=True
            )
            subprocess.run(
                [
                    *git,
                    "fetch",
                    "--filter=blob:none",
                    "--depth=1",
                    "origin",
                    ENGINE_REVISION,
                ],
                check=True,
            )
            subprocess.run(
                [*git, "checkout", "-q", "--detach", ENGINE_REVISION], check=True
            )
            try:
                candidate.rename(target)
            except OSError:
                if not target.is_dir():
                    raise
    git = ["git", "-C", str(target)]
    revision = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    changes = subprocess.check_output(
        [*git, "status", "--porcelain", "--untracked-files=no"], text=True
    )
    if revision != ENGINE_REVISION or changes:
        raise SystemExit(f"Unexpected checkout or local changes in {target}")
    engine = target / "skills" / "ppt-master"
    if (
        not (engine / "SKILL.md").is_file()
        or not (engine / "requirements.txt").is_file()
    ):
        raise SystemExit(f"Incomplete PPT Master checkout: {engine}")
    receipt = {"revision": revision, "source": ENGINE_REPO, "skill": str(engine)}
    current = target.parent.parent / "engine.json"
    with tempfile.TemporaryDirectory(dir=current.parent) as temporary:
        candidate = Path(temporary) / "engine.json"
        candidate.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(candidate, current)
    return engine


def prepare_python(engine):
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    executable = venv_python(version)
    folder = executable.parent.parent
    if not executable.is_file():
        if (
            folder.exists()
            and any(folder.iterdir())
            and not (folder / "pyvenv.cfg").is_file()
        ):
            raise SystemExit(f"Directory already in use: {folder}")
        folder.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", str(folder)], check=True)
    actual = subprocess.check_output(
        [str(executable), "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
        text=True,
    ).strip()
    if actual != version:
        raise SystemExit(f"Python {actual} in {folder}, expected {version}")
    requirements = engine / "requirements.txt"
    uv = shutil.which("uv")
    install = (
        [uv, "pip", "install", "--python", str(executable)]
        if uv
        else [str(executable), "-m", "pip", "install"]
    )
    subprocess.run([*install, "-r", str(requirements), "python-docx"], check=True)
    print(executable)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout-only", action="store_true")
    args = parser.parse_args()
    engine = obtain_engine()
    print(engine, flush=True)
    if not args.checkout_only:
        prepare_python(engine)
