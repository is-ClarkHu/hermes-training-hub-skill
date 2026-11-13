"""Training analysis over a ``TrainingData`` snapshot. Python standard library only."""

from __future__ import annotations

from datetime import date, timedelta

from th_adapter import TrainingData

COUNTED_SET_TYPES = ("normal", "superset", "dropset")
EXCLUDED_BODY_PARTS = ("warmup",)
DONE_INJURY_STATUS = "recovered"


def _d(value: str) -> date:
    return date.fromisoformat(value[:10])


def _counted(sets: list[dict]) -> list[dict]:
    return [s for s in sets if (s.get("set_type") or "normal") in COUNTED_SET_TYPES]


def _body_parts(ex: dict | None) -> list[str]:
    return [b for b in (ex or {}).get("body_parts") or [] if b not in EXCLUDED_BODY_PARTS]


def _trained_entries(d: TrainingData):
    """Entries with at least one counted set (or no set rows at all, e.g. duration work)."""
    for e in d.entries:
        sets = d.sets_by_entry.get(e["id"], [])
        if not sets or _counted(sets):
            yield e


def set_volume(s: dict) -> float:
    """weight × reps plus every sub-set (drop-set tail); per-side sets count both sides."""
    factor = 2 if s.get("per_side") else 1
    parts = [s, *(s.get("sub_sets") or [])]
    return sum((p.get("weight") or 0) * (p.get("reps") or 0) * factor for p in parts if isinstance(p, dict))


def days_since_trained(d: TrainingData, today: date) -> dict[str, int | None]:
    result: dict[str, int | None] = {b: None for ex in d.exercises.values() for b in _body_parts(ex)}
    for e in _trained_entries(d):
        days = (today - _d(e["date"])).days
        for b in _body_parts(d.exercises.get(e["exercise_id"])):
            if result.get(b) is None or days < result[b]:
                result[b] = days
    return result


def weekly_volume(d: TrainingData, today: date, weeks: int = 4) -> list[dict]:
    """Counted sets and kg volume per (Monday week, body part) for the last ``weeks`` weeks."""
    first_monday = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    totals: dict[tuple[str, str], dict] = {}
    for e in d.entries:
        day = _d(e["date"])
        if not first_monday <= day <= today:
            continue
        sets = _counted(d.sets_by_entry.get(e["id"], []))
        if not sets:
            continue
        week = (day - timedelta(days=day.weekday())).isoformat()
        for b in _body_parts(d.exercises.get(e["exercise_id"])):
            row = totals.setdefault((week, b), {"week_start": week, "body_part": b, "sets": 0, "volume_kg": 0})
            row["sets"] += len(sets)
            row["volume_kg"] += sum(set_volume(s) for s in sets)
    return [totals[k] for k in sorted(totals)]


def cycle_position(d: TrainingData) -> dict:
    """Where the athlete is in the active split: labels done this round and the next one."""
    cycle = d.active_cycle
    if not cycle:
        return {"cycle": None, "order": [], "done_this_round": [], "next_label": None, "last_date": None,
                "body_parts_by_label": {}}
    order = [day["label"] for day in cycle.get("days") or [] if day.get("label")]
    parts = {day["label"]: list(day.get("body_parts") or []) for day in cycle.get("days") or [] if day.get("label")}
    done: set[str] = set()
    last_date = None
    for e in d.entries:
        label = e.get("cycle_day_label")
        in_cycle = e.get("cycle_id") == cycle.get("id") or (e.get("source") == "journal" and label in order)
        if not in_cycle or label not in order:
            continue
        done.add(label)
        last_date = e["date"]
        if done >= set(order):
            done = set()
    return {
        "cycle": cycle.get("name"),
        "order": order,
        "done_this_round": [label for label in order if label in done],
        "next_label": next((label for label in order if label not in done), None),
        "last_date": last_date,
        "body_parts_by_label": parts,
    }


def personal_records(d: TrainingData, top: int = 10) -> list[dict]:
    """Heaviest working set per weight×reps exercise (ties: more reps, then earliest)."""
    best: dict[str, dict] = {}
    for e in d.entries:
        ex = d.exercises.get(e["exercise_id"]) or {}
        if ex.get("measure_type", "weight_reps") != "weight_reps":
            continue
        for s in _counted(d.sets_by_entry.get(e["id"], [])):
            weight, reps = s.get("weight"), s.get("reps") or 0
            if not weight:
                continue
            current = best.get(e["exercise_id"])
            if current is None or (weight, reps) > (current["weight"], current["reps"]):
                best[e["exercise_id"]] = {"exercise": ex.get("name_en") or e["exercise_id"],
                                          "weight": weight, "reps": reps, "date": e["date"]}
    return sorted(best.values(), key=lambda r: (-r["weight"], -r["reps"], r["exercise"]))[:top]


def sport_load(d: TrainingData, today: date, days: int = 7) -> dict[str, float]:
    """Hours per sport over the ``days`` days ending today (inclusive)."""
    start = today - timedelta(days=days - 1)
    load: dict[str, float] = {}
    for session in d.sessions:
        if not session.get("date") or not start <= _d(session["date"]) <= today:
            continue
        name = (d.sports.get(session.get("sport_id")) or {}).get("name_en") or "Other"
        load[name] = load.get(name, 0) + (session.get("hours") or 0)
    return load


def active_injuries(d: TrainingData) -> list[dict]:
    return [
        {"body_area": i.get("body_area_en") or i.get("body_area"), "status": i.get("status"),
         "severity": i.get("severity"), "started_on": i.get("started_on"), "body_part": i.get("body_part")}
        for i in d.injuries
        if i.get("status") != DONE_INJURY_STATUS
    ]


def status_summary(d: TrainingData, today: date) -> dict:
    return {
        "today": today.isoformat(),
        "last_workout_date": d.entries[-1]["date"] if d.entries else None,
        "goal": (d.profile or {}).get("goal"),
        "cycle_position": cycle_position(d),
        "days_since_trained": days_since_trained(d, today),
        "weekly_volume": weekly_volume(d, today),
        "personal_records": personal_records(d),
        "sport_load_7d": sport_load(d, today),
        "active_injuries": active_injuries(d),
        "warnings": list(d.warnings),
    }
