"""PyInstaller entry script.

PyInstaller runs the entry script as a top-level module, which breaks the
relative imports inside anidb_launcher/__main__.py (e.g. `from .anidb_client
import ...`). This wrapper imports the package by name first so its parent
package is registered, then delegates to its main().

Use `python -m anidb_launcher` for dev runs; this script is only the build
entry point.
"""
from __future__ import annotations

import sys

from anidb_launcher.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
