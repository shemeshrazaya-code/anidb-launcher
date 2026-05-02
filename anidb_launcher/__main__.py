from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import tkinter as tk

from .models import AnimeDetail
from .anilist_client import AniListClient
from .demo_data import DEMO_ANIME
from .favorites import load_favorites
from .jikan_client import JikanClient
from .loading_dialog import run_with_progress
from .preferences import load_prefs
from .reminders import load_reminders
from .setup_dialog import run_setup_if_needed
from .sources import load_sources, save_bundled_defaults
from .ui import apply_modern_theme, run_app

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "anidb-launcher"
DEFAULT_SOURCES_PATH = DEFAULT_CONFIG_DIR / "sources.json"
DEFAULT_FAVORITES_PATH = DEFAULT_CONFIG_DIR / "favorites.json"
DEFAULT_PREFS_PATH = DEFAULT_CONFIG_DIR / "prefs.json"
DEFAULT_REMINDERS_PATH = DEFAULT_CONFIG_DIR / "reminders.json"


@dataclass
class AnimeListItem:
    aid: int
    title: str
    detail: AnimeDetail | None = None


def _items_from_demo() -> tuple[list[AnimeListItem], Callable[[int], AnimeDetail | None], str]:
    by_aid = {a.aid: a for a in DEMO_ANIME}
    items = [AnimeListItem(aid=a.aid, title=a.title, detail=a) for a in DEMO_ANIME]
    return items, lambda aid: by_aid.get(aid), "demo"


def _items_from_anilist(max_pages: int, refresh: bool, progress) -> list[AnimeDetail]:
    print("trying AniList...", file=sys.stderr)
    client = AniListClient(max_pages=max_pages)
    return client.get_top_anime(force_refresh=refresh, progress=progress)


def _items_from_jikan(max_pages: int, refresh: bool, progress) -> list[AnimeDetail]:
    print("trying Jikan/MyAnimeList...", file=sys.stderr)
    client = JikanClient(max_pages=max_pages)
    return client.get_top_anime(force_refresh=refresh, progress=progress)


def _build_items(details: list[AnimeDetail]) -> list[AnimeListItem]:
    items = [AnimeListItem(aid=d.aid, title=d.title, detail=d) for d in details]
    items.sort(key=lambda i: (-(i.detail.rating if (i.detail and i.detail.rating) else 0.0), i.title.lower()))
    return items


def _load_with_fallback(source: str, max_pages: int, refresh: bool, progress) -> tuple[list[AnimeDetail], str]:
    """Return (details, source_label). Tries each provider in order; surfaces the last error if all fail."""
    providers: list[tuple[str, Callable[[], list[AnimeDetail]]]] = []
    if source in ("auto", "anilist"):
        providers.append(("anilist", lambda: _items_from_anilist(max_pages, refresh, progress)))
    if source in ("auto", "jikan"):
        # Jikan is paginated 25/page (vs AniList 50/page); double the page budget by default.
        jikan_pages = max_pages * 2 if source == "auto" else max_pages
        providers.append(("jikan", lambda: _items_from_jikan(jikan_pages, refresh, progress)))

    last_error: BaseException | None = None
    for name, fn in providers:
        try:
            if progress:
                progress(status=f"Trying {name}...")
            details = fn()
            print(f"  {len(details)} anime loaded from {name}", file=sys.stderr)
            return details, name
        except Exception as e:
            print(f"  {name} failed: {type(e).__name__}: {e}", file=sys.stderr)
            if progress:
                progress(status=f"{name} failed: {type(e).__name__}", detail="trying fallback...")
            last_error = e
    assert last_error is not None
    raise last_error


def _print_load_error(e: BaseException) -> None:
    import urllib.error
    from .anilist_client import AniListError
    from .jikan_client import JikanError

    print(f"error: failed to load anime list from any source: {type(e).__name__}: {e}", file=sys.stderr)
    if isinstance(e, (AniListError, JikanError)):
        print("       Provider returned an API error.", file=sys.stderr)
    elif isinstance(e, urllib.error.URLError):
        print("       Network error. Check your connection.", file=sys.stderr)
    print("       Try --source jikan or --source anilist to force a single provider.", file=sys.stderr)
    print("       Or run with --demo for offline mode.", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="anidb-launcher")
    parser.add_argument("--demo", action="store_true", help="Use 5 hardcoded anime instead of a live source")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES_PATH, help="Path to sources.json")
    parser.add_argument("--skip-setup", action="store_true",
                        help="Skip first-run setup even when sources.json is empty")
    parser.add_argument("--source", choices=["auto", "anilist", "jikan"], default="auto",
                        help="Anime data provider; 'auto' tries AniList then falls back to Jikan/MAL")
    parser.add_argument("--max-pages", type=int, default=60,
                        help="AniList pages to fetch (50/page; default 60 = top 3000). Jikan auto-doubles in auto mode.")
    parser.add_argument("--refresh", action="store_true",
                        help="Force a refresh; new results merge into the existing cache (no entries lost)")
    parser.add_argument("--save-defaults", action="store_true",
                        help="Bundle your current sources.json into the package's default_sources.json. "
                             "Anyone you ship the package to will get those sources on first run.")
    args = parser.parse_args(argv)

    if args.save_defaults:
        if not args.sources.exists():
            print(f"error: no sources file at {args.sources}", file=sys.stderr)
            return 1
        current = load_sources(args.sources)
        if not current:
            print(f"error: {args.sources} has no sources to bundle", file=sys.stderr)
            return 1
        save_bundled_defaults(current)
        print(f"saved {len(current)} source(s) as bundled defaults", file=sys.stderr)
        for s in current:
            print(f"  - {s.name}", file=sys.stderr)
        return 0

    if not args.skip_setup:
        if not run_setup_if_needed(args.sources):
            print("setup cancelled — exiting.", file=sys.stderr)
            return 0

    prefs = load_prefs(DEFAULT_PREFS_PATH)
    initial_theme = prefs.get("theme") if prefs.get("theme") in ("dark", "light") else "dark"

    root = tk.Tk()
    apply_modern_theme(root, theme=initial_theme)
    root.withdraw()

    if args.demo:
        items, fetch, mode_label = _items_from_demo()
    else:
        try:
            details, source_name = run_with_progress(
                root,
                lambda progress: _load_with_fallback(args.source, args.max_pages, args.refresh, progress),
                title="Loading anime data",
                initial_status="Connecting...",
            )
        except Exception as e:
            _print_load_error(e)
            root.destroy()
            return 1
        items = _build_items(details)
        fetch = None
        mode_label = f"live · {source_name}"

    favorites = load_favorites(DEFAULT_FAVORITES_PATH)
    reminders = load_reminders(DEFAULT_REMINDERS_PATH)

    def refresh_fn(progress) -> tuple[list, str]:
        details, source_name = _load_with_fallback(args.source, args.max_pages, True, progress)
        return _build_items(details), source_name

    run_app(
        items=items,
        fetch_detail=fetch,
        sources_path=args.sources,
        mode_label=mode_label,
        root=root,
        favorites=favorites,
        favorites_path=DEFAULT_FAVORITES_PATH,
        refresh_fn=None if args.demo else refresh_fn,
        prefs_path=DEFAULT_PREFS_PATH,
        initial_theme=initial_theme,
        reminders=reminders,
        reminders_path=DEFAULT_REMINDERS_PATH,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
