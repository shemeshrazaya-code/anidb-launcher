from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anidb_launcher.sources import (  # noqa: E402
    AvailabilityResult,
    FetchResult,
    SearchSource,
    SourceError,
    add_source,
    check_availability,
    load_sources,
    remove_source,
    save_sources,
)

FIXTURES = ROOT / "test_fixtures"


def test_search_source_requires_query_placeholder():
    with pytest.raises(SourceError):
        SearchSource(name="Bad", search_url_template="https://example.com/search?q=fixed")


def test_search_source_requires_name():
    with pytest.raises(SourceError):
        SearchSource(name="  ", search_url_template="https://example.com/?q={query}")


def test_search_source_validates_match_pattern_regex():
    with pytest.raises(SourceError):
        SearchSource(
            name="Bad",
            search_url_template="https://example.com/?q={query}",
            match_pattern="[unclosed",
        )


def test_build_url_url_encodes_query():
    s = SearchSource(name="DDG", search_url_template="https://duckduckgo.com/?q={query}")
    assert s.build_url("Cowboy Bebop") == "https://duckduckgo.com/?q=Cowboy%20Bebop"


def test_build_url_handles_special_chars():
    s = SearchSource(name="DDG", search_url_template="https://duckduckgo.com/?q={query}")
    url = s.build_url("Re:Zero / & ?")
    assert "Re%3AZero" in url
    assert "%2F" in url
    assert "%26" in url
    assert "%3F" in url


def test_load_sources_from_fixture():
    sources = load_sources(FIXTURES / "sources_sample.json")
    assert len(sources) == 2
    assert sources[0].name == "DuckDuckGo"
    assert sources[1].name == "MyAnimeList"


def test_load_sources_missing_file_returns_empty(tmp_path):
    assert load_sources(tmp_path / "does-not-exist.json") == []


def test_load_sources_with_match_pattern(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps({"sources": [
            {"name": "X", "search_url_template": "https://x.example/?q={query}", "match_pattern": "result-card"}
        ]}),
        encoding="utf-8",
    )
    [s] = load_sources(path)
    assert s.match_pattern == "result-card"


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "sources.json"
    originals = [
        SearchSource(name="A", search_url_template="https://a.example/?q={query}"),
        SearchSource(name="B", search_url_template="https://b.example/find/{query}", match_pattern="hits"),
    ]
    save_sources(path, originals)
    loaded = load_sources(path)
    assert loaded == originals


def test_save_omits_null_match_pattern(tmp_path):
    path = tmp_path / "sources.json"
    save_sources(path, [SearchSource(name="A", search_url_template="https://a.example/?q={query}")])
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw == {"sources": [{"name": "A", "search_url_template": "https://a.example/?q={query}"}]}


def test_add_source_rejects_duplicate_name(tmp_path):
    path = tmp_path / "sources.json"
    add_source(path, SearchSource(name="A", search_url_template="https://a.example/?q={query}"))
    with pytest.raises(SourceError):
        add_source(path, SearchSource(name="A", search_url_template="https://other.example/?q={query}"))


def test_remove_source_by_name(tmp_path):
    path = tmp_path / "sources.json"
    save_sources(path, [
        SearchSource(name="A", search_url_template="https://a.example/?q={query}"),
        SearchSource(name="B", search_url_template="https://b.example/?q={query}"),
    ])
    remaining = remove_source(path, "A")
    assert [s.name for s in remaining] == ["B"]


def test_remove_source_missing_name_errors(tmp_path):
    path = tmp_path / "sources.json"
    save_sources(path, [SearchSource(name="A", search_url_template="https://a.example/?q={query}")])
    with pytest.raises(SourceError):
        remove_source(path, "Z")


def test_check_availability_default_finds_query_in_body():
    s = SearchSource(name="X", search_url_template="https://x.example/?q={query}")
    fetcher = lambda _url: FetchResult(body="<html>... Cowboy Bebop ...</html>", status=200)
    res = check_availability(s, "Cowboy Bebop", fetcher=fetcher)
    assert res.found is True
    assert res.status == 200
    assert res.error is None


def test_check_availability_default_returns_false_when_query_absent():
    s = SearchSource(name="X", search_url_template="https://x.example/?q={query}")
    fetcher = lambda _url: FetchResult(body="<html>no results</html>", status=200)
    res = check_availability(s, "Cowboy Bebop", fetcher=fetcher)
    assert res.found is False


def test_check_availability_default_is_case_insensitive():
    s = SearchSource(name="X", search_url_template="https://x.example/?q={query}")
    fetcher = lambda _url: FetchResult(body="cowboy bebop", status=200)
    res = check_availability(s, "Cowboy Bebop", fetcher=fetcher)
    assert res.found is True


def test_check_availability_with_match_pattern_overrides_body_check():
    s = SearchSource(
        name="X",
        search_url_template="https://x.example/?q={query}",
        match_pattern=r'class="result-item"',
    )
    fetcher_with = lambda _url: FetchResult(body='<div class="result-item">Cowboy Bebop</div>', status=200)
    fetcher_without = lambda _url: FetchResult(body="<div>Cowboy Bebop</div>", status=200)
    assert check_availability(s, "Cowboy Bebop", fetcher=fetcher_with).found is True
    assert check_availability(s, "Cowboy Bebop", fetcher=fetcher_without).found is False


def test_check_availability_returns_error_on_fetch_failure():
    s = SearchSource(name="X", search_url_template="https://x.example/?q={query}")

    def fetcher(_url):
        raise ConnectionError("no route to host")

    res = check_availability(s, "Cowboy Bebop", fetcher=fetcher)
    assert res.found is None
    assert res.status is None
    assert "ConnectionError" in res.error


def test_check_availability_url_encodes_query_in_url():
    s = SearchSource(name="X", search_url_template="https://x.example/?q={query}")
    seen: list[str] = []

    def fetcher(url):
        seen.append(url)
        return FetchResult(body="", status=200)

    check_availability(s, "Cowboy Bebop", fetcher=fetcher)
    assert seen == ["https://x.example/?q=Cowboy%20Bebop"]
