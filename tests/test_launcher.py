from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anidb_launcher.launcher import launch  # noqa: E402
from anidb_launcher.sources import SearchSource  # noqa: E402


def test_launch_returns_built_url_and_calls_opener():
    source = SearchSource(name="DDG", search_url_template="https://duckduckgo.com/?q={query}")
    calls: list[str] = []

    url = launch(source, "Cowboy Bebop", opener=lambda u: calls.append(u) or True)

    assert url == "https://duckduckgo.com/?q=Cowboy%20Bebop"
    assert calls == ["https://duckduckgo.com/?q=Cowboy%20Bebop"]


def test_launch_url_encodes_special_chars():
    source = SearchSource(name="DDG", search_url_template="https://duckduckgo.com/?q={query}")
    captured: list[str] = []

    launch(source, "Re:Zero / & ?", opener=lambda u: captured.append(u) or True)

    assert "Re%3AZero" in captured[0]
    assert "%26" in captured[0]


def test_launch_rejects_empty_query():
    source = SearchSource(name="DDG", search_url_template="https://duckduckgo.com/?q={query}")
    with pytest.raises(ValueError):
        launch(source, "   ", opener=lambda u: True)


def test_launch_path_template():
    source = SearchSource(name="Path", search_url_template="https://example.com/find/{query}")
    captured: list[str] = []
    launch(source, "Mushishi", opener=lambda u: captured.append(u) or True)
    assert captured == ["https://example.com/find/Mushishi"]
