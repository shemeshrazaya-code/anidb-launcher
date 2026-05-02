from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AnimeDetail:
    aid: int
    title: str
    description: str
    rating: float | None
    rating_count: int | None
    picture_url: str | None
    type: str | None
    episode_count: int | None
    genres: list[str] | None = None
    season: str | None = None  # human-readable, e.g. "Spring 2023" or "2023"
    is_adult: bool = False  # provider-flagged adult/hentai content
    start_date: str | None = None  # ISO date "YYYY-MM-DD" or "YYYY-MM" or "YYYY"
    alt_titles: list[str] | None = None  # romaji/native/synonyms — searched for matching
