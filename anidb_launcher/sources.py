from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote

QUERY_PLACEHOLDER = "{query}"
DEFAULT_USER_AGENT = "anidb-launcher/0.1 (availability-check)"
DEFAULT_TIMEOUT_SECONDS = 10.0

# Defaults shipped inside the package. Edit this file (or use the
# --save-defaults CLI flag) to rev the bundled list when sites die / move.
BUNDLED_DEFAULTS_PATH = Path(__file__).parent / "default_sources.json"

Fetcher = Callable[[str], "FetchResult"]


class SourceError(ValueError):
    pass


@dataclass(frozen=True)
class FetchResult:
    body: str
    status: int


@dataclass(frozen=True)
class SearchSource:
    name: str
    search_url_template: str
    match_pattern: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SourceError("source name must be non-empty")
        if QUERY_PLACEHOLDER not in self.search_url_template:
            raise SourceError(
                f"search_url_template must contain {QUERY_PLACEHOLDER}: "
                f"{self.search_url_template!r}"
            )
        if self.match_pattern is not None:
            if not self.match_pattern.strip():
                raise SourceError("match_pattern, if set, must be non-empty")
            try:
                re.compile(self.match_pattern)
            except re.error as e:
                raise SourceError(f"invalid match_pattern regex: {e}") from e

    def build_url(self, query: str) -> str:
        return self.search_url_template.replace(QUERY_PLACEHOLDER, quote(query, safe=""))


@dataclass
class AvailabilityResult:
    url: str
    found: bool | None
    status: int | None
    error: str | None = None


def _default_fetcher(url: str) -> FetchResult:
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
        raw = resp.read()
        try:
            body = raw.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            body = raw.decode("latin-1", errors="replace")
        return FetchResult(body=body, status=getattr(resp, "status", 200))


def check_availability(
    source: SearchSource,
    query: str,
    fetcher: Fetcher | None = None,
) -> AvailabilityResult:
    url = source.build_url(query)
    fetch = fetcher or _default_fetcher
    try:
        result = fetch(url)
    except urllib.error.HTTPError as e:
        return AvailabilityResult(url=url, found=False, status=e.code, error=None)
    except Exception as e:
        return AvailabilityResult(url=url, found=None, status=None, error=f"{type(e).__name__}: {e}")

    if source.match_pattern:
        try:
            found = bool(re.search(source.match_pattern, result.body, re.IGNORECASE))
        except re.error as e:
            return AvailabilityResult(url=url, found=None, status=result.status, error=f"bad regex: {e}")
    else:
        found = query.lower() in result.body.lower()

    return AvailabilityResult(url=url, found=found, status=result.status, error=None)


def load_sources(path: Path) -> list[SearchSource]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("sources", [])
    if not isinstance(entries, list):
        raise SourceError(f"sources file must have a 'sources' array: {path}")
    return [
        SearchSource(
            name=e["name"],
            search_url_template=e["search_url_template"],
            match_pattern=e.get("match_pattern"),
        )
        for e in entries
    ]


def save_sources(path: Path, sources: list[SearchSource]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned: list[dict] = []
    for s in sources:
        item = asdict(s)
        cleaned.append({k: v for k, v in item.items() if v is not None})
    payload = {"sources": cleaned}
    fd, tmp_name = tempfile.mkstemp(prefix=".sources-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def add_source(path: Path, source: SearchSource) -> list[SearchSource]:
    sources = load_sources(path)
    if any(s.name == source.name for s in sources):
        raise SourceError(f"source name already exists: {source.name!r}")
    sources.append(source)
    save_sources(path, sources)
    return sources


def load_bundled_defaults() -> list[SearchSource]:
    if not BUNDLED_DEFAULTS_PATH.exists():
        return []
    try:
        return load_sources(BUNDLED_DEFAULTS_PATH)
    except (json.JSONDecodeError, SourceError, KeyError):
        return []


def save_bundled_defaults(sources: list[SearchSource]) -> None:
    """Write the package's default_sources.json. Used to update the shipped
    list when sites go down — the next time you build/distribute, downstream
    users get the new defaults."""
    save_sources(BUNDLED_DEFAULTS_PATH, sources)


def remove_source(path: Path, name: str) -> list[SearchSource]:
    sources = load_sources(path)
    new = [s for s in sources if s.name != name]
    if len(new) == len(sources):
        raise SourceError(f"no source named {name!r}")
    save_sources(path, new)
    return new
