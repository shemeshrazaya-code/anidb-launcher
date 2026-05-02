from __future__ import annotations

import webbrowser
from typing import Callable

from .sources import SearchSource

Opener = Callable[[str], bool]


def launch(source: SearchSource, query: str, opener: Opener | None = None) -> str:
    if not query.strip():
        raise ValueError("query must be non-empty")
    url = source.build_url(query)
    (opener or webbrowser.open)(url)
    return url
