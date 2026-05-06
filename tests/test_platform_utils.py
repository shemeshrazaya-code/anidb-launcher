from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anidb_launcher import platform_utils  # noqa: E402


def test_preferred_config_dir_macos():
    home = Path("/Users/tester")
    out = platform_utils._preferred_config_dir("anidb-launcher", "darwin", home, {})
    assert out == home / "Library" / "Application Support" / "anidb-launcher"


def test_preferred_config_dir_windows_uses_appdata():
    home = Path("C:/Users/tester")
    env = {"APPDATA": "C:/Users/tester/AppData/Roaming"}
    out = platform_utils._preferred_config_dir("anidb-launcher", "win32", home, env)
    assert out == Path("C:/Users/tester/AppData/Roaming") / "anidb-launcher"


def test_preferred_config_dir_linux_uses_xdg_when_present():
    home = Path("/home/tester")
    env = {"XDG_CONFIG_HOME": "/tmp/config-home"}
    out = platform_utils._preferred_config_dir("anidb-launcher", "linux", home, env)
    assert out == Path("/tmp/config-home") / "anidb-launcher"


def test_open_command_for_path():
    target = Path("/tmp/sources.json")
    assert platform_utils._open_command_for_path(target, "darwin") == ["open", str(target)]
    assert platform_utils._open_command_for_path(target, "linux") == ["xdg-open", str(target)]
    assert platform_utils._open_command_for_path(target, "win32") is None


def test_app_config_dir_honors_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    override = tmp_path / "my-anidb-config"
    monkeypatch.setenv(platform_utils.CONFIG_OVERRIDE_ENV, str(override))
    assert platform_utils.app_config_dir() == override


def test_app_config_dir_prefers_legacy_if_preferred_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    legacy = home / ".config" / "anidb-launcher"
    legacy.mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv(platform_utils.CONFIG_OVERRIDE_ENV, raising=False)
    monkeypatch.setattr(platform_utils.Path, "home", lambda *args, **kwargs: home)
    monkeypatch.setattr(platform_utils.sys, "platform", "darwin")

    assert platform_utils.app_config_dir() == legacy
