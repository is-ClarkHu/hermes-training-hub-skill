"""Load a Training Hub JSON backup, merge the agent's workout journal, rebase demo dates.

Python standard library only. The backup is the app's "export" file:
``{"version": 1, "exported_at": ..., "tables": {<table>: [rows...]}}``.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Tables the coach never reads (app-internal or free-form chat).
EXCLUDED_TABLES = ("optional_trackers", "chat_messages", "insights", "translation_dictionary")
# Date keys shifted by the rebase, anywhere inside fixture rows (incl. injury checkpoints).
DATE_KEYS = ("date", "started_on", "resolved_on")


@dataclass
class TrainingData:
    exercises: dict[str, dict]
    entries: list[dict]
    sets_by_entry: dict[str, list[dict]]
    sports: dict[str, dict]
    sessions: list[dict]
    cycles: list[dict]
    active_cycle: dict | None
    profile: dict | None
    injuries: list[dict]
    rebase_days: int = 0
    warnings: list[str] = field(default_factory=list)


def today_local(tz: str, now: datetime | None = None) -> date:
    """The calendar date in ``tz`` (``now`` must be timezone-aware when given)."""
    zone = ZoneInfo(tz)
    return (now.astimezone(zone) if now else datetime.now(zone)).date()


def _live(rows: list | None) -> list[dict]:
    return [r for r in rows or [] if isinstance(r, dict) and not r.get("deleted")]


def _shift(obj, days: int):
    """Shift every ISO date under DATE_KEYS, recursively, in place."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in DATE_KEYS and isinstance(value, str) and len(value) >= 10:
                try:
                    shifted = date.fromisoformat(value[:10]) + timedelta(days=days)
                except ValueError:
                    continue
                obj[key] = shifted.isoformat() + value[10:]
            else:
                _shift(value, days)
    elif isinstance(obj, list):
        for item in obj:
            _shift(item, days)


def _sort_entries(entries: list[dict]) -> list[dict]:
    return sorted(entries, key=lambda e: (e.get("date") or "", e.get("sort_order") or 0))


def _offset_days(entries: list[dict], today: date, rebase_file: Path | None) -> int:
    if rebase_file is None:
        return 0
    if rebase_file.exists():
        return int(json.loads(rebase_file.read_text())["offset_days"])
    if not entries:
        return 0
    last = max(date.fromisoformat(e["date"][:10]) for e in entries if e.get("date"))
    offset = ((today - timedelta(days=1)) - last).days
    rebase_file.parent.mkdir(parents=True, exist_ok=True)
    rebase_file.write_text(json.dumps({"offset_days": offset, "anchored_on": today.isoformat()}))
    return offset


def load_backup(path: Path, *, today: date, rebase_file: Path | None) -> TrainingData:
    """Read the backup. With ``rebase_file``, the last fixture workout lands on yesterday.

    The offset is computed once and persisted, so "yesterday" stays anchored to the
    first load (later loads reuse the stored ``offset_days``).
    """
    tables = json.loads(Path(path).read_text(encoding="utf-8")).get("tables", {})
    entries = _live(tables.get("workout_entries"))
    sessions = _live(tables.get("sport_sessions"))
    injuries = _live(tables.get("injuries"))
    days = _offset_days(entries, today, rebase_file)
    if days:
        for rows in (entries, sessions, injuries):
            _shift(rows, days)

    sets_by_entry: dict[str, list[dict]] = {}
    for s in _live(tables.get("sets")):
        sets_by_entry.setdefault(s.get("entry_id"), []).append(s)
    for sets in sets_by_entry.values():
        sets.sort(key=lambda s: s.get("set_index") or 0)

    cycles = _live(tables.get("training_cycle"))
    profiles = _live(tables.get("profile"))
    return TrainingData(
        exercises={e["id"]: e for e in _live(tables.get("exercises"))},
        entries=_sort_entries(entries),
        sets_by_entry=sets_by_entry,
        sports={s["id"]: s for s in _live(tables.get("sports"))},
        sessions=sorted(sessions, key=lambda s: s.get("date") or ""),
        cycles=cycles,
        active_cycle=next((c for c in cycles if c.get("active")), None),
        profile=profiles[0] if profiles else None,
        injuries=injuries,
        rebase_days=days,
    )


def reset_rebase(rebase_file: Path) -> None:
    """Forget the anchor; the next load re-anchors "last workout = yesterday"."""
    rebase_file.unlink(missing_ok=True)


def _parse_event(path: Path) -> dict:
    return validate_event(json.loads(path.read_text(encoding="utf-8")))


def validate_event(event) -> dict:
    """Raise ValueError/KeyError/TypeError unless ``event`` is a well-formed workout event."""
    if not isinstance(event, dict) or event.get("type") != "workout":
        raise ValueError("not a workout event")
    date.fromisoformat(str(event["date"]))
    items = event["items"]
    if not isinstance(items, list) or not items:
        raise ValueError("no items")
    for item in items:
        if not str(item.get("exercise", "")).strip() or not isinstance(item.get("sets"), list):
            raise ValueError("bad item")
    return event


def merge_journal(data: TrainingData, journal_dir: Path) -> TrainingData:
    """Return a copy of ``data`` with journal workouts (``<journal_dir>/*/*.json``) added.

    Journal dates are real dates and are never rebased. Corrupt files are skipped and
    reported in ``warnings``; an event id seen twice is merged once.
    """
    exercises = dict(data.exercises)
    by_name = {}
    for ex in exercises.values():
        for key in ("name_en", "name_zh"):
            if ex.get(key):
                by_name.setdefault(ex[key].strip().casefold(), ex["id"])
    entries = list(data.entries)
    sets_by_entry = dict(data.sets_by_entry)
    warnings = list(data.warnings)
    seen: set[str] = set()

    files = sorted(Path(journal_dir).glob("*/*.json")) if Path(journal_dir).is_dir() else []
    for path in files:
        try:
            event = _parse_event(path)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            warnings.append(f"skipped journal file {path.parent.name}/{path.name}: {type(exc).__name__}")
            continue
        event_id = str(event.get("id") or path.stem)
        if event_id in seen:
            continue
        seen.add(event_id)
        for order, item in enumerate(event["items"]):
            name = str(item["exercise"]).strip()
            ex_id = by_name.get(name.casefold())
            if ex_id is None:
                ex_id = f"adhoc:{name.casefold()}"
                exercises[ex_id] = {"id": ex_id, "name_en": name, "name_zh": "", "body_parts": [],
                                    "measure_type": "weight_reps", "is_custom": True, "adhoc": True}
                by_name[name.casefold()] = ex_id
            entry_id = f"{event_id}:{order}"
            entries.append({
                "id": entry_id, "date": str(event["date"]), "exercise_id": ex_id, "sort_order": order,
                "cycle_day_label": event.get("cycle_day_label"), "source": "journal",
            })
            sets_by_entry[entry_id] = [
                {"id": f"{entry_id}:{i}", "entry_id": entry_id, "set_index": i, "set_type": "working",
                 "weight": s.get("weight"), "reps": s.get("reps")}
                for i, s in enumerate(item["sets"]) if isinstance(s, dict)
            ]

    return dataclasses.replace(
        data, exercises=exercises, entries=_sort_entries(entries),
        sets_by_entry=sets_by_entry, warnings=warnings,
    )
