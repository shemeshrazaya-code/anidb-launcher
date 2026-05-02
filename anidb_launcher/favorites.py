from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def load_favorites(path: Path) -> set[int]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    out: set[int] = set()
    for aid in data.get("favorites", []):
        if isinstance(aid, int):
            out.add(aid)
        elif isinstance(aid, str) and aid.isdigit():
            out.add(int(aid))
    return out


def save_favorites(path: Path, favorites: set[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"favorites": sorted(favorites)}
    fd, tmp_str = tempfile.mkstemp(prefix="fav-", suffix=".json", dir=str(path.parent))
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def toggle_favorite(favorites: set[int], aid: int) -> bool:
    """Toggle aid in favorites. Returns True if it is now a favorite, False if removed."""
    if aid in favorites:
        favorites.discard(aid)
        return False
    favorites.add(aid)
    return True
