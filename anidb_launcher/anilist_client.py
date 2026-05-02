from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .models import AnimeDetail

ProgressFn = Callable[..., None]

API_URL = "https://graphql.anilist.co"
RATE_LIMIT_DELAY = 1.2  # ~50 req/min — well under AniList's 90/min ceiling
                        # (burst window means simply staying under the average isn't enough)

# AniList sits behind Cloudflare and bans default urllib User-Agents
# (Error 1010: browser_signature_banned). Browser-shaped UA gets through.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

_MEDIA_FIELDS = """
      id
      title { romaji english native userPreferred }
      synonyms
      description(asHtml: false)
      averageScore
      popularity
      coverImage { medium large }
      format
      episodes
      genres
      season
      seasonYear
      startDate { year month day }
      isAdult
      tags { name isMediaSpoiler isAdult rank }
"""

QUERY = (
    "query ($page: Int, $perPage: Int) {"
    "  Page(page: $page, perPage: $perPage) {"
    "    pageInfo { hasNextPage currentPage total }"
    "    media(type: ANIME, sort: POPULARITY_DESC) {"
    + _MEDIA_FIELDS +
    "    }"
    "  }"
    "}"
)

# Separate query so hentai aren't drowned out by all-time popularity sort —
# they typically have low popularity counts even when highly rated within
# their genre. genre_in: ["Hentai"] returns only adult-genre tagged shows.
HENTAI_QUERY = (
    "query ($page: Int, $perPage: Int) {"
    "  Page(page: $page, perPage: $perPage) {"
    "    pageInfo { hasNextPage currentPage total }"
    "    media(type: ANIME, sort: POPULARITY_DESC, genre_in: [\"Hentai\"]) {"
    + _MEDIA_FIELDS +
    "    }"
    "  }"
    "}"
)

# Hentai sorted by score — catches highly-rated but low-popularity titles
# the popularity sort misses entirely (niche / older / doujin-style works).
HENTAI_SCORE_QUERY = (
    "query ($page: Int, $perPage: Int) {"
    "  Page(page: $page, perPage: $perPage) {"
    "    pageInfo { hasNextPage currentPage total }"
    "    media(type: ANIME, sort: SCORE_DESC, genre_in: [\"Hentai\"]) {"
    + _MEDIA_FIELDS +
    "    }"
    "  }"
    "}"
)

# Currently-trending anime (newest releases gaining traction). Catches new
# titles that haven't accumulated all-time popularity yet.
TRENDING_QUERY = (
    "query ($page: Int, $perPage: Int) {"
    "  Page(page: $page, perPage: $perPage) {"
    "    pageInfo { hasNextPage currentPage total }"
    "    media(type: ANIME, sort: TRENDING_DESC) {"
    + _MEDIA_FIELDS +
    "    }"
    "  }"
    "}"
)

# Content-categorical tags that should always be merged into the genre filter,
# regardless of how AniList ranks them on a particular show. These describe
# whole-show themes/audience, not plot beats — so users want to filter by them.
ALWAYS_INCLUDE_TAGS = {
    # Romance/relationship structures
    "Harem", "Reverse Harem", "Love Triangle", "Age Gap", "Marriage", "Polyamorous",
    # Adult tone
    "Ecchi", "Fanservice", "Nudity", "Sexual Content", "Sexual Abuse",
    # Content warnings / dark themes
    "Gore", "Body Horror", "Cosmic Horror", "Drugs", "Bullying", "Suicide", "Lolicon", "Shotacon",
    # LGBTQ
    "Yuri", "Yaoi", "Boys' Love", "Girls' Love", "LGBTQ+ Themes", "Crossdressing", "Genderswap",
    # Audience demographics / cast
    "Cute Girls Doing Cute Things", "Cute Boys Doing Cute Things", "Idol",
    "Primarily Female Cast", "Primarily Male Cast", "Primarily Teen Cast", "Primarily Adult Cast",
    "Female Protagonist", "Male Protagonist",
    # Personality archetypes
    "Tsundere", "Kuudere", "Yandere", "Dandere",
    # Supernatural / fantasy creatures
    "Vampire", "Werewolf", "Demons", "Gods", "Witch", "Ghost", "Zombie", "Youkai", "Angels",
    "Dragons", "Monster Girl", "Monster Boy", "Kemonomimi",
    # Settings & big themes
    "Mecha", "Real Robot", "Super Robot", "Mahou Shoujo", "Magic", "Cultivation",
    "Isekai", "Reincarnation", "Time Travel", "Time Loop", "Time Manipulation",
    "Slice of Life", "Iyashikei", "Cyberpunk", "Steampunk", "Space", "Space Opera",
    "Post-Apocalyptic", "Dystopian", "Survival", "Virtual World", "Urban Fantasy",
    "Historical", "Military", "War", "Politics", "Espionage", "Crime", "Yakuza",
    "Samurai", "Ninja", "Pirates", "Vikings", "Wuxia", "Martial Arts",
    # Narrative tone / structure
    "Psychological", "Tragedy", "Slow Burn", "Mind Games", "Revenge", "Conspiracy",
    "Coming of Age", "Episodic", "Anthology", "Surreal Comedy", "Parody",
    # Setting subtypes
    "School", "School Club", "Workplace", "Boarding School", "Rural", "Urban",
    "Boys' School", "Girls' School", "College",
    # Supernatural mechanics / superpowers
    "Super Power", "Henshin", "Superhero", "Shapeshifting", "Memory Manipulation",
    "Body Swapping",
    # Hobbies / activities
    "Music", "Sports", "Cooking", "Food", "Art", "Photography", "Filmmaking",
    "Detective", "Gambling", "Otaku Culture", "Video Games", "Cosplay",
    # Roles / occupations / characters
    "Maids", "Shrine Maidens", "Police", "Firefighters", "Teacher", "Assassins",
    "Anti-Hero", "Elderly Protagonist", "Chuunibyou", "Hikikomori",
}

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = _BR_RE.sub("\n", s)
    return _TAG_RE.sub("", s).strip()


class AniListError(RuntimeError):
    pass


class AniListClient:
    def __init__(
        self,
        cache_dir: Path | None = None,
        max_pages: int = 60,
        per_page: int = 50,
        hentai_pages: int = 40,
        hentai_score_pages: int = 30,
        trending_pages: int = 20,
    ) -> None:
        self.cache_dir = cache_dir or (Path.home() / ".cache" / "anidb-launcher")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_pages = max_pages
        self.per_page = per_page
        self.hentai_pages = hentai_pages
        self.hentai_score_pages = hentai_score_pages
        self.trending_pages = trending_pages
        self._last_call_at = 0.0
        # Set during _fetch_all_pages; lets _post surface 429 retry countdowns
        # to the loading dialog instead of a silent 30s sleep.
        self._progress: ProgressFn | None = None

    def get_top_anime(self, force_refresh: bool = False, progress: ProgressFn | None = None) -> list[AnimeDetail]:
        cache_path = self.cache_dir / "anilist-top.json"
        existing = self._load_cache(cache_path) if cache_path.exists() else []
        if existing and not force_refresh:
            age_days = (time.time() - cache_path.stat().st_mtime) / 86400
            print(f"  using cached AniList data: {len(existing)} entries, {age_days:.1f} days old (--refresh to update)",
                  file=sys.stderr)
            if progress:
                progress(status=f"Loaded cached AniList data ({len(existing)} entries)",
                         detail=f"{age_days:.1f} days old — re-run with --refresh to update")
            return existing

        print(f"  refreshing AniList ({len(existing)} cached entries will be merged with new results)...",
              file=sys.stderr)
        if progress:
            progress(status="Fetching from AniList...",
                     detail=f"{len(existing)} cached entries; new results will merge")
        new_details = self._fetch_all_pages(progress=progress)
        merged = _merge_by_aid(existing, new_details)
        self._save_cache(cache_path, merged)
        added = len(merged) - len(existing)
        print(f"  saved {len(merged)} entries to cache (+{added} new)", file=sys.stderr)
        if progress:
            progress(status=f"AniList: {len(merged)} entries saved (+{added} new)",
                     detail="opening main window...")
        return merged

    def _fetch_all_pages(self, progress: ProgressFn | None = None) -> list[AnimeDetail]:
        total = (
            self.max_pages + self.hentai_pages
            + self.hentai_score_pages + self.trending_pages
        )
        out: list[AnimeDetail] = []
        seen_ids: set[int] = set()
        self._progress = progress

        def fetch_phase(query: str, max_pages: int, label: str, page_offset: int) -> None:
            for page in range(1, max_pages + 1):
                if progress:
                    progress(
                        status=f"Fetching {label} from AniList...",
                        detail=f"page {page}/{max_pages} — {len(out)} anime so far",
                        current=page_offset + page, total=total,
                    )
                data = self._post(query, {"page": page, "perPage": self.per_page})
                page_data = data["data"]["Page"]
                for m in page_data["media"]:
                    aid = m.get("id")
                    if aid is None or aid in seen_ids:
                        continue
                    seen_ids.add(aid)
                    out.append(_media_to_detail(m))
                if (page % 10 == 0) or not page_data["pageInfo"]["hasNextPage"]:
                    print(f"  {label} page {page}: {len(out)} anime fetched", file=sys.stderr)
                if not page_data["pageInfo"]["hasNextPage"]:
                    break

        offset = 0
        try:
            fetch_phase(QUERY, self.max_pages, "top anime", offset)
            offset += self.max_pages
            if self.hentai_pages > 0:
                fetch_phase(HENTAI_QUERY, self.hentai_pages, "hentai (popular)", offset)
            offset += self.hentai_pages
            if self.hentai_score_pages > 0:
                fetch_phase(HENTAI_SCORE_QUERY, self.hentai_score_pages, "hentai (top-rated)", offset)
            offset += self.hentai_score_pages
            if self.trending_pages > 0:
                fetch_phase(TRENDING_QUERY, self.trending_pages, "trending", offset)
        finally:
            self._progress = None
        return out

    def _post(self, query: str, variables: dict) -> dict:
        elapsed = time.time() - self._last_call_at
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        req = urllib.request.Request(
            API_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": BROWSER_UA,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after_hdr = (e.headers.get("Retry-After") if e.headers else None) or "30"
                try:
                    retry_after = max(1, min(int(retry_after_hdr), 90))
                except ValueError:
                    retry_after = 30
                print(f"  AniList rate-limited; sleeping {retry_after}s before retry...",
                      file=sys.stderr)
                # Sleep in 1s slices and push a countdown to the progress dialog
                # so the user can see it's not stuck.
                for remaining in range(retry_after, 0, -1):
                    if self._progress:
                        self._progress(
                            status="AniList rate-limited — waiting before retry",
                            detail=f"resuming in {remaining}s",
                        )
                    time.sleep(1)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            else:
                raise
        self._last_call_at = time.time()
        if "errors" in payload:
            raise AniListError(str(payload["errors"]))
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
        by_aid[d.aid] = d  # new overrides old (fresh score/synopsis); old-only entries kept
    return list(by_aid.values())


def _media_to_detail(m: dict) -> AnimeDetail:
    title_obj = m.get("title") or {}
    title_en = (title_obj.get("english") or "").strip() or None
    title_ro = (title_obj.get("romaji") or "").strip() or "(untitled)"
    title_native = (title_obj.get("native") or "").strip() or None
    title_pref = (title_obj.get("userPreferred") or "").strip() or None
    synonyms = m.get("synonyms") or []
    alt_titles: list[str] = []
    primary = title_en or title_ro
    for cand in [title_en, title_ro, title_native, title_pref, *synonyms]:
        s = (cand or "").strip()
        if s and s != primary and s not in alt_titles:
            alt_titles.append(s)
    avg = m.get("averageScore")
    rating = (avg / 10.0) if avg is not None else None
    cover = m.get("coverImage") or {}
    picture_url = cover.get("large") or cover.get("medium")
    raw_genres = m.get("genres") or []
    combined: list[str] = []
    for g in raw_genres:
        name = str(g).strip()
        if name and name not in combined:
            combined.append(name)
    # Merge tags into the same filterable list so categorical labels (Harem,
    # Fanservice, Tsundere, Isekai, ...) show up alongside the small "genres"
    # set. Always-include tags are kept regardless of their rank on the show;
    # other non-spoiler tags pass if their rank meets a softer threshold.
    raw_tags = m.get("tags") or []
    eligible_tags: list[dict] = []
    for t in raw_tags:
        if t.get("isMediaSpoiler"):
            continue
        name = (t.get("name") or "").strip()
        if not name:
            continue
        rank = t.get("rank") or 0
        if name in ALWAYS_INCLUDE_TAGS or rank >= 50:
            eligible_tags.append(t)
    eligible_tags.sort(key=lambda t: -(t.get("rank") or 0))
    for t in eligible_tags[:15]:
        name = (t.get("name") or "").strip()
        if name and name not in combined:
            combined.append(name)
    genres = combined or None
    season_name = (m.get("season") or "").strip()
    sd = m.get("startDate") or {}
    sd_year = sd.get("year")
    sd_month = sd.get("month")
    sd_day = sd.get("day")
    season_year = m.get("seasonYear") or sd_year
    if season_name and season_year:
        season = f"{season_name.capitalize()} {season_year}"
    elif season_year:
        season = str(season_year)
    else:
        season = None
    if sd_year and sd_month and sd_day:
        start_date = f"{sd_year:04d}-{sd_month:02d}-{sd_day:02d}"
    elif sd_year and sd_month:
        start_date = f"{sd_year:04d}-{sd_month:02d}"
    elif sd_year:
        start_date = f"{sd_year:04d}"
    else:
        start_date = None
    return AnimeDetail(
        aid=int(m["id"]),
        title=primary,
        description=_strip_html(m.get("description")),
        rating=rating,
        rating_count=m.get("popularity"),
        picture_url=picture_url,
        type=m.get("format"),
        episode_count=m.get("episodes"),
        genres=genres,
        season=season,
        is_adult=bool(m.get("isAdult")),
        start_date=start_date,
        alt_titles=alt_titles or None,
    )
