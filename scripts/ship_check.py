from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_step(name: str, cmd: list[str], env: dict[str, str] | None = None) -> bool:
    print(f"\n==> {name}")
    print(" ".join(cmd))
    rc = subprocess.call(cmd, cwd=str(ROOT), env=env)
    if rc != 0:
        print(f"[FAIL] {name} (exit {rc})")
        return False
    print(f"[PASS] {name}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run pre-ship quality gates for anidb-launcher."
    )
    parser.add_argument(
        "--include-build",
        action="store_true",
        help="Also run packaging build.py (slower, for release candidates).",
    )
    args = parser.parse_args()

    if not _module_available("pytest"):
        print("error: pytest is not installed in this Python environment.")
        print("install with: python -m pip install -r requirements.txt pytest")
        return 1

    pytest_tmp = ROOT / "pytest_tmp"
    if pytest_tmp.exists():
        shutil.rmtree(pytest_tmp, ignore_errors=True)
    pytest_tmp.mkdir(parents=True, exist_ok=True)
    pytest_env = os.environ.copy()
    pytest_env["TMP"] = str(pytest_tmp)
    pytest_env["TEMP"] = str(pytest_tmp)
    pytest_env["TMPDIR"] = str(pytest_tmp)

    steps: list[tuple[str, list[str], dict[str, str] | None]] = [
        (
            "Run tests",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--basetemp",
                str(pytest_tmp),
            ],
            pytest_env,
        ),
        (
            "Validate default source config",
            [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    "from anidb_launcher.sources import load_sources; "
                    "p=Path('anidb_launcher/default_sources.json'); "
                    "sources=load_sources(p); "
                    "print(f'default_sources={len(sources)}')"
                ),
            ],
            None,
        ),
    ]

    if args.include_build:
        steps.append(("Build artifact", [sys.executable, "build.py"], None))

    failures = 0
    try:
        for name, cmd, env in steps:
            ok = run_step(name, cmd, env=env)
            if not ok:
                failures += 1
    finally:
        shutil.rmtree(pytest_tmp, ignore_errors=True)

    if failures:
        print(f"\nFinished with {failures} failing step(s).")
        return 1

    print("\nAll pre-ship gates passed.")
    return 0


def _module_available(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
