# anidb-launcher

A small desktop app that lets you browse the top anime from public anime
databases (AniList / Jikan / MyAnimeList) and then launch a search for any
title on whichever sites *you* configure. The app itself ships with **no**
search sites — you bring your own.

## What it does

- Fetches a ranked list of anime from AniList, with Jikan/MAL as a fallback
- Lets you browse, favorite, and set reminders for entries
- When you pick an anime, opens a search for it in your default browser on
  every site you've added — one tab per site

The launcher itself never scrapes results in-app; it just opens the site's
own search page in your browser. Whatever the site shows you is up to the
site.

## Why "bring your own" sources

The app has no opinion about where you watch or read. There is no bundled
list of streaming or reading sites — you add the URLs you already use. This
keeps the project source-agnostic and makes it trivial to swap a site out
when it dies, moves, or changes its URL format.

## Install

Requires Python 3.12+.

```
pip install -r requirements.txt
python -m anidb_launcher
```

On first launch you'll see the setup dialog (see below). After that the app
stores local state in an OS-specific config directory:

- macOS: `~/Library/Application Support/anidb-launcher/`
- Windows: `%APPDATA%\anidb-launcher\`
- Linux: `~/.config/anidb-launcher/` (or `$XDG_CONFIG_HOME/anidb-launcher/`)

Override on any OS with:

```
ANIDB_LAUNCHER_CONFIG_DIR=/path/to/dir
```

## Adding sources

### First run

The first time you start the app, a setup dialog walks you through adding
your first source. The full how-to:

1. Open the site you want to search in your browser.
2. Run a search there for any anime title — e.g. `naruto`.
3. Copy the URL from your browser's address bar.
4. Replace the search term with the literal placeholder `{query}`.
5. Back in the app, click **Add source...**, paste the template, and give
   it a name.

Concrete example with DuckDuckGo:

| Step | Value |
|---|---|
| Search URL the browser shows | `https://duckduckgo.com/?q=naruto` |
| Replace the query | `https://duckduckgo.com/?q={query}` |
| Name | `DuckDuckGo` |

When you launch an anime from the list, the app substitutes the title into
`{query}` (URL-encoded) and opens the resulting URL.

### Adding more sources later

The same dialog is reachable from the app — open the sources manager and
hit **Add source...** with the same recipe.

You can also edit the file directly:

```
<config-dir>/sources.json
```

```json
{
  "sources": [
    {
      "name": "DuckDuckGo",
      "search_url_template": "https://duckduckgo.com/?q={query}"
    },
    {
      "name": "MyAnimeList",
      "search_url_template": "https://myanimelist.net/anime.php?q={query}&cat=anime"
    }
  ]
}
```

### Optional: availability check pattern

A source can include a `match_pattern` regex. The app uses it to test
whether a search actually returned results before opening the tab. If
omitted, the app just checks whether the anime title appears anywhere in
the response body.

```json
{
  "name": "ExampleSite",
  "search_url_template": "https://example.com/search?q={query}",
  "match_pattern": "class=\"result-card\""
}
```

## CLI flags

```
python -m anidb_launcher [--demo] [--source auto|anilist|jikan]
                         [--max-pages N] [--refresh]
                         [--sources PATH] [--skip-setup]
                         [--save-defaults]
```

- `--demo` — use 5 hardcoded anime instead of hitting a live API
- `--source` — pin a single provider; default `auto` tries AniList then Jikan
- `--max-pages` — AniList pages to fetch (50/page; default 60 = top 3000)
- `--refresh` — force a re-fetch; new results merge into the existing cache
- `--sources` — point at an alternate `sources.json`
- `--skip-setup` — don't open the first-run dialog even if no sources exist
- `--save-defaults` — bundle your current `sources.json` into the package's
  `default_sources.json` (useful if you're packaging your own build for
  yourself or a friend)

## Data sources

- AniList GraphQL API — `graphql.anilist.co`
- Jikan v4 (MyAnimeList mirror) — `api.jikan.moe`

Both are public read-only APIs. No login required.

## Development

```
pip install -r requirements.txt
pytest
```

## Workflow

This repo now includes a gstack-style delivery loop in `WORKFLOW.md`:

- Think -> Plan -> Build -> Review -> Test -> Ship -> Reflect
- Suggested gstack commands: `/office-hours`, `/plan-eng-review`, `/review`, `/qa`, `/ship`, `/retro`

Design references for UI work:

- `DESIGN.md` (project visual and UX system)
- `docs/UI_REVIEW_CHECKLIST.md` (release UI audit checklist)

Pre-ship gates for every branch:

```
python scripts/ship_check.py
```

For release candidates (includes packaging build):

```
python scripts/ship_check.py --include-build
```

## Packaging

Build with PyInstaller:

```
python -m pip install pyinstaller
python build.py
```

Artifacts by platform:

- Windows: `dist/anidb-launcher.exe`
- macOS: `dist/anidb-launcher.app`
- Linux: `dist/anidb-launcher`

Modules:

- `anidb_launcher/anilist_client.py` — AniList GraphQL fetch + cache
- `anidb_launcher/jikan_client.py`   — Jikan/MAL fetch + cache (fallback)
- `anidb_launcher/sources.py`        — source schema + load/save/validate
- `anidb_launcher/launcher.py`       — open a search URL in the browser
- `anidb_launcher/setup_dialog.py`   — first-run "add a source" dialog
- `anidb_launcher/ui.py`             — main Tk UI
- `anidb_launcher/favorites.py` / `reminders.py` / `preferences.py` — local state

## License

See `LICENSE` if present, otherwise treat as personal/unlicensed.
