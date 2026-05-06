from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping

APP_NAME = "anidb-launcher"
CONFIG_OVERRIDE_ENV = "ANIDB_LAUNCHER_CONFIG_DIR"


def _preferred_config_dir(
    app_name: str,
    platform_name: str,
    home: Path,
    env: Mapping[str, str],
) -> Path:
    if platform_name == "darwin":
        return home / "Library" / "Application Support" / app_name
    if platform_name == "win32":
        appdata = env.get("APPDATA")
        if appdata:
            return Path(appdata) / app_name
        return home / "AppData" / "Roaming" / app_name
    xdg_home = env.get("XDG_CONFIG_HOME")
    if xdg_home:
        return Path(xdg_home) / app_name
    return home / ".config" / app_name


def app_config_dir(app_name: str = APP_NAME) -> Path:
    """Return an OS-appropriate config directory for this app.

    Backward compatibility: if a legacy ~/.config/<app> directory exists and
    the preferred OS-native directory does not, keep using the legacy path.
    """
    override = os.environ.get(CONFIG_OVERRIDE_ENV)
    if override:
        return Path(override).expanduser()

    home = Path.home()
    preferred = _preferred_config_dir(app_name, sys.platform, home, os.environ)
    legacy = home / ".config" / app_name

    if preferred.exists():
        return preferred
    if legacy.exists():
        return legacy
    return preferred


def _open_command_for_path(path: Path, platform_name: str) -> list[str] | None:
    if platform_name == "win32":
        return None
    if platform_name == "darwin":
        return ["open", str(path)]
    return ["xdg-open", str(path)]


def open_path(path: Path) -> None:
    """Open a path in the platform's default app/file browser."""
    target = path.expanduser()
    if sys.platform == "win32":
        os.startfile(str(target))
        return

    cmd = _open_command_for_path(target, sys.platform)
    if cmd is None:
        raise OSError(f"no open command for platform {sys.platform!r}")
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as e:
        raise OSError(f"missing opener command: {cmd[0]}") from e
