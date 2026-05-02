"""Build a standalone Windows executable with PyInstaller.

Run from the project root:
    python -m pip install -r requirements.txt
    python -m pip install pyinstaller
    python build.py

Output: dist/anidb-launcher.exe (single self-contained file).
Distribute: zip and send the .exe — recipients double-click to run, no install needed.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
# Use a top-level wrapper, not __main__.py directly — PyInstaller runs the
# entry script outside its package, which breaks relative imports.
ENTRY = PROJECT_ROOT / "anidb_launcher_entry.py"
APP_NAME = "anidb-launcher"
DEFAULT_SOURCES = PROJECT_ROOT / "anidb_launcher" / "default_sources.json"


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("error: PyInstaller is not installed.", file=sys.stderr)
        print("       Run: python -m pip install pyinstaller", file=sys.stderr)
        return 1

    if not DEFAULT_SOURCES.exists():
        print(f"warn: {DEFAULT_SOURCES} missing — recipients won't get bundled defaults.",
              file=sys.stderr)

    # Clean previous build artifacts so the rebuild is reproducible.
    for d in ("build", "dist", f"{APP_NAME}.spec"):
        target = PROJECT_ROOT / d
        if target.is_dir():
            shutil.rmtree(target)
        elif target.is_file():
            target.unlink()

    # PyInstaller's --add-data uses ';' on Windows, ':' elsewhere.
    sep = ";" if sys.platform == "win32" else ":"
    add_data = f"{DEFAULT_SOURCES}{sep}anidb_launcher"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                    # single .exe (no folder of dlls)
        "--windowed",                   # hide the console window for the GUI app
        f"--name={APP_NAME}",
        f"--add-data={add_data}",
        "--collect-all=sv_ttk",         # include sv-ttk's TCL theme files
        "--collect-all=pywinstyles",    # include pywinstyles
        "--collect-submodules=PIL",     # be safe with Pillow plugins
        "--noconfirm",
        str(ENTRY),
    ]
    print("running:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(PROJECT_ROOT))


if __name__ == "__main__":
    sys.exit(main())
