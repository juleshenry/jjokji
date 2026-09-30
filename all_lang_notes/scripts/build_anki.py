#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def run_step(command: list[str], cwd: Path, env: dict[str, str]) -> int:
    result = subprocess.run(command, cwd=cwd, env=env, text=True)
    return result.returncode


def main() -> int:
    root = repo_root()
    env = os.environ.copy()
    local_bin_dir = os.path.expanduser("~/.local/bin")
    env["PATH"] = env.get("PATH", "") + os.pathsep + local_bin_dir

    normalize_status = run_step([sys.executable, str(root / "scripts" / "normalize_language_notes.py")], root, env)
    if normalize_status != 0:
        return normalize_status

    brainbrew = shutil.which("brainbrew") or os.path.expanduser("~/.local/bin/brainbrew")

    return run_step([brainbrew, "run", "recipes/source_to_anki.yaml"], root, env)


if __name__ == "__main__":
    raise SystemExit(main())
