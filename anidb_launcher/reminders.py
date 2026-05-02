from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path


def load_reminders(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw = data.get("reminders") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for r in raw:
        if isinstance(r, dict) and "aid" in r:
            out.append(r)
    return out


def save_reminders(path: Path, reminders: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"reminders": reminders}
    fd, tmp_str = tempfile.mkstemp(prefix="rem-", suffix=".json", dir=str(path.parent))
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


def has_reminder(reminders: list[dict], aid: int) -> bool:
    return any(int(r.get("aid", -1)) == aid for r in reminders)


def add_reminder(reminders: list[dict], aid: int, title: str, target_date: str | None) -> bool:
    """Add a reminder. Returns True if added, False if already existed."""
    if has_reminder(reminders, aid):
        return False
    reminders.append({"aid": int(aid), "title": title, "target_date": target_date or ""})
    return True


def remove_reminder(reminders: list[dict], aid: int) -> bool:
    before = len(reminders)
    reminders[:] = [r for r in reminders if int(r.get("aid", -1)) != aid]
    return len(reminders) < before


def is_released(reminder: dict, today: date | None = None) -> bool:
    """True if the reminder's target_date is today or earlier."""
    if today is None:
        today = date.today()
    target = (reminder.get("target_date") or "")[:10]
    if len(target) < 10:
        return False
    try:
        y, m, d = int(target[0:4]), int(target[5:7]), int(target[8:10])
        return date(y, m, d) <= today
    except ValueError:
        return False
