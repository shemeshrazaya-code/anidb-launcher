from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .models import AnimeDetail

ProgressFn = Callable[..., None]

API_BASE = "https://api.jikan.moe/v4"
RATE_LIMIT_DELAY = 0.4  # 3 req/sec ceiling; 0.4s spacing leaves headroom

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


class JikanError(RuntimeError):
    pass


class JikanClient:
    def __init__(
        self,
        cache_dir: Path | None = None,
        max_pages: int = 120,
        hentai_pages: int = 80,
        hentai_score_pages: int = 60,
    ) -> None:
        self.cache_dir = cache_dir or (Path.home() / ".cache" / "anidb-launcher")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_pages = max_pages
        self.hentai_pages = hentai_pages
        self.hentai_score_pages = hentai_score_pages
        self._last_call_at = 0.0

    def get_top_anime(self, force_refresh: bool = False, progress: ProgressFn | None = None) -> list[AnimeDetail]:
        cache_path = self.cache_dir / "jikan-top.json"
        existing = self._load_cache(cache_path) if cache_path.exists() else []
        if existing and not force_refresh:
            age_days = (time.time() - cache_path.stat().st_mtime) / 86400
            print(f"  using cached Jikan data: {len(existing)} entries, {age_days:.1f} days old (--refresh to update)",
                  file=sys.stderr)
            if progress:
                progress(status=f"Loaded cached Jikan data ({len(existing)} entries)",
                         detail=f"{age_days:.1f} days old — re-run with --refresh to update")
            return existing

        print(f"  refreshing Jikan ({len(existing)} cached entries will be merged with new results)...",
              file=sys.stderr)
        if progress:
            progress(status="Fetching from Jikan/MyAnimeList...",
                     detail=f"{len(existing)} cached entries; new results will merge")
        new_details = self._fetch_all_pages(progress=progress)
        merged = _merge_by_aid(existing, new_details)
        self._save_cache(cache_path, merged)
        added = len(merged) - len(existing)
        print(f"  saved {len(merged)} entries to cache (+{added} new)", file=sys.stderr)
        if progress:
            progress(status=f"Jikan: {len(merged)} entries saved (+{added} new)",
                     detail="opening main window...")
        return merged

    def _fetch_all_pages(self, progress: ProgressFn | None = None) -> list[AnimeDetail]:
        out: list[AnimeDetail] = []
        seen_ids: set[int] = set()
        total = self.max_pages + self.hentai_pages + self.hentai_score_pages

        def fetch_phase(path_template: str, max_pages: int, label: str, page_offset: int) -> None:
            for page in range(1, max_pages + 1):
                if progress:
                    progress(
                        status=f"Fetching {label} from Jikan/MyAnimeList...",
                        detail=f"page {page}/{max_pages} — {len(out)} anime so far",
                        current=page_offset + page, total=total,
                    )
                data = self._get(path_template.format(page=page))
                entries = data.get("data") or []
                for entry in entries:
                    aid = entry.get("mal_id")
                    if aid is None or aid in seen_ids:
                        continue
                    seen_ids.add(aid)
                    out.append(_entry_to_detail(entry))
                pag = data.get("pagination") or {}
                has_next = pag.get("has_next_page", False)
                if (page % 10 == 0) or not has_next:
                    print(f"  {label} page {page}: {len(out)} anime fetched", file=sys.stderr)
                if not has_next:
                    break

        # /top/anime excludes adult content by default. Use the search endpoint
        # with genres=12 (Hentai on MAL) + sfw=false for the second pass.
        offset = 0
        fetch_phase("/top/anime?page={page}&limit=25", self.max_pages, "top anime", offset)
        offset += self.max_pages
        if self.hentai_pages > 0:
            fetch_phase(
                "/anime?genres=12&order_by=popularity&sort=desc&sfw=false&page={page}&limit=25",
                self.hentai_pages, "hentai (popular)", offset,
            )
        offset += self.hentai_pages
        if self.hentai_score_pages > 0:
            fetch_phase(
                "/anime?genres=12&order_by=score&sort=desc&sfw=false&page={page}&limit=25",
                self.hentai_score_pages, "hentai (top-rated)", offset,
            )
        return out

    def _get(self, path: str) -> dict:
        elapsed = time.time() - self._last_call_at
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        url = API_BASE + path
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": BROWSER_UA},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            else:
                raise
        self._last_call_at = time.time()
        if "error" in payload and "data" not in payload:
            raise JikanError(str(payload["error"]))
        return payload

    def _save_cache(self, path: Path, details: list[AnimeDetail]) -> None:
        payload = {
            "version": 1,
            "fetched_at": time.time(),
            "items": [d.__dict__ for d in details],
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)

    def _load_cache(self, path: Path) -> list[AnimeDetail]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [AnimeDetail(**item) for item in payload["items"]]


def _merge_by_aid(existing: list[AnimeDetail], new: list[AnimeDetail]) -> list[AnimeDetail]:
    by_aid: dict[int, AnimeDetail] = {d.aid: d for d in existing}
    for d in new:
        by_aid[d.aid] = d
    return list(by_aid.values())


def _entry_to_detail(entry: dict) -> AnimeDetail:
    title_en = (entry.get("title_english") or "").strip() or None
    title_ja = (entry.get("title") or "").strip() or "(untitled)"
    primary = title_en or title_ja
    alt_titles: list[str] = []
    for cand in [
        title_en, title_ja,
        entry.get("title_japanese"),
        *(entry.get("title_synonyms") or []),
        *((t.get("title") if isinstance(t, dict) else None) for t in (entry.get("titles") or [])),
    ]:
        s = ((cand or "") if isinstance(cand, str) else "").strip()
        if s and s != primary and s not in alt_titles:
            alt_titles.append(s)
    score = entry.get("score")
    rating = float(score) if score is not None else None
    images = entry.get("images") or {}
    jpg = images.get("jpg") or {}
    picture_url = jpg.get("large_image_url") or jpg.get("image_url")
    # Jikan returns separate genres / themes / demographics arrays of {mal_id, name, ...}.
    # Merge them all under the same `genres` field for filtering purposes.
    genre_names: list[str] = []
    for key in ("genres", "themes", "demographics"):
        for g in (entry.get(key) or []):
            name = (g.get("name") or "").strip() if isinstance(g, dict) else ""
            if name and name not in genre_names:
                genre_names.append(name)
    season_name = (entry.get("season") or "").strip()
    aired_from = (entry.get("aired") or {}).get("from") or ""
    year = entry.get("year")
    if not year and len(aired_from) >= 4 and aired_from[:4].isdigit():
        year = int(aired_from[:4])
    if season_name and year:
        season = f"{season_name.capitalize()} {year}"
    elif year:
        season = str(year)
    else:
        season = None
    # ISO date "YYYY-MM-DD" extracted from aired.from (typically "2023-04-06T00:00:00+00:00")
    start_date = aired_from[:10] if len(aired_from) >= 10 and aired_from[:10].count("-") == 2 else None
    rating_label = (entry.get("rating") or "").lower()
    is_adult = "rx" in rating_label or "hentai" in rating_label
    return AnimeDetail(
        aid=int(entry["mal_id"]),
        title=primary,
        description=(entry.get("synopsis") or "").strip(),
        rating=rating,
        rating_count=entry.get("scored_by"),
        picture_url=picture_url,
        type=entry.get("type"),
        episode_count=entry.get("episodes"),
        genres=genre_names or None,
        season=season,
        is_adult=is_adult,
        start_date=start_date,
        alt_titles=alt_titles or None,
    )
