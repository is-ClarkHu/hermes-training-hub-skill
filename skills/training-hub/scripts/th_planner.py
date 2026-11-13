"""Rule-based session planner. The LLM narrates; it never invents these numbers.

Standard library only.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from th_constraints import DAY_END_H, DAY_START_H, Slot

MIN_SLOT_MIN = 60
MAX_CONSECUTIVE = 2
SPORT_EVENT = re.compile(r"\b(frisbee|ultimate|game)\b", re.IGNORECASE)
RUN_EVENT = re.compile(r"\b(run|running|jog)\b", re.IGNORECASE)
OUTDOOR_KINDS = ("outdoor_run", "frisbee")
DEFAULT_TZ = "America/Los_Angeles"


def _event_start(ev: dict, zone: ZoneInfo) -> datetime | None:
    value = ev.get("start")
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=zone) if dt.tzinfo is None else dt.astimezone(zone)


def _event_end(ev: dict, start: datetime, zone: ZoneInfo) -> datetime:
    try:
        end = datetime.fromisoformat(str(ev.get("end")).replace("Z", "+00:00"))
        return end.replace(tzinfo=zone) if end.tzinfo is None else end.astimezone(zone)
    except ValueError:
        return start + timedelta(hours=1)


def _title(ev: dict) -> str:
    return str(ev.get("title") or ev.get("summary") or "")


def _events_on(events: list[dict], day: date, zone: ZoneInfo):
    for ev in events or []:
        start = _event_start(ev, zone)
        if start and start.date() == day:
            yield ev, start


def _cycle(status: dict) -> tuple[list[str], dict[str, list[str]], str | None]:
    pos = status.get("cycle_position") or {}
    return pos.get("order") or [], pos.get("body_parts_by_label") or {}, pos.get("next_label")


def _strength(label: str | None, parts_by_label: dict) -> dict:
    return {"label": label, "body_parts": list(parts_by_label.get(label, [])) if label else [], "kind": "strength"}


def _earliest_slot(slots: list[Slot], day: date) -> Slot | None:
    for s in sorted(slots, key=lambda s: s.start):
        zone = s.start.tzinfo
        lo = datetime.combine(day, time(DAY_START_H), zone)
        hi = datetime.combine(day, time(DAY_END_H), zone)
        start, end = max(s.start, lo), min(s.end, hi)
        if (end - start) >= timedelta(minutes=MIN_SLOT_MIN):
            return Slot(start, end)
    return None


def _outdoor_ok(outdoor: dict, slot: Slot) -> bool | None:
    """True/False for the slot's hours, or None when the forecast is unavailable."""
    if not outdoor or not outdoor.get("available"):
        return None
    hours = {h["hour"]: h["suitable"] for h in outdoor.get("hours", [])}
    wanted = range(slot.start.hour, max(slot.start.hour + 1, slot.end.hour + (slot.end.minute > 0)))
    return all(hours.get(h, False) for h in wanted)


def recommend_today(status: dict, slots: list[Slot], outdoor: dict, events: list[dict], today: date,
                    tz: str = DEFAULT_TZ) -> dict:
    zone = ZoneInfo(tz)
    order, parts_by_label, label = _cycle(status)
    reasons: list[str] = []
    session = _strength(label, parts_by_label)
    slot: Slot | None = None

    # Outdoor practice on today's calendar sets the session kind and its time.
    for ev, start in _events_on(events, today, zone):
        kind = "frisbee" if SPORT_EVENT.search(_title(ev)) else "outdoor_run" if RUN_EVENT.search(_title(ev)) else None
        if kind:
            session = {"label": None, "body_parts": ["legs", "cardio"], "kind": kind}
            slot = Slot(start, _event_end(ev, start, zone))
            reasons.append(f"calendar: {kind.replace('_', ' ')} today")
            break

    # Rule 1: no heavy legs the day before a frisbee/ultimate game.
    tomorrow = today + timedelta(days=1)
    sport_tomorrow = any(SPORT_EVENT.search(_title(ev)) for ev, _ in _events_on(events, tomorrow, zone))
    if session["kind"] == "strength" and sport_tomorrow and "legs" in session["body_parts"] and label in order:
        i = order.index(label)
        for candidate in order[i + 1:] + order[:i]:
            if "legs" not in parts_by_label.get(candidate, []):
                session = _strength(candidate, parts_by_label)
                reasons.append("frisbee tomorrow: avoid heavy legs")
                break

    # Rule 2: needs a 60-minute slot inside 07:00-21:00.
    if slot is None:
        slot = _earliest_slot(slots, today)
    if slot is None:
        return {"session": {"label": None, "body_parts": [], "kind": "rest"}, "slot": None,
                "reasons": reasons + ["no 60-min slot today"]}

    # Rule 3: bad weather moves outdoor work indoors.
    if session["kind"] in OUTDOOR_KINDS:
        ok = _outdoor_ok(outdoor, slot)
        if ok is False:
            session = _strength(label, parts_by_label)
            reasons.append("rain/wind: moved indoors")
        elif ok is None:
            reasons.append("weather unavailable: check before going out")

    # Rule 4: keep the session but flag injured body parts.
    for inj in status.get("active_injuries") or []:
        if inj.get("body_part") and inj["body_part"] in session["body_parts"]:
            reasons.append(f"modify: {inj.get('body_area')}")

    return {"session": session, "slot": {"start": slot.start.isoformat(), "end": slot.end.isoformat()},
            "reasons": reasons}


def full_day(day: date, zone: ZoneInfo) -> list[Slot]:
    return [Slot(datetime.combine(day, time(DAY_START_H), zone), datetime.combine(day, time(DAY_END_H), zone))]


def week_plan(status: dict, slots_by_day: dict[date, list[Slot]], outdoor_by_day: dict[date, dict],
              events: list[dict], start: date, tz: str = DEFAULT_TZ) -> list[dict]:
    """Seven day-records. Labels rotate from ``next_label``; a missed day keeps its label."""
    zone = ZoneInfo(tz)
    order, _parts, label = _cycle(status)
    last = status.get("last_workout_date")
    consecutive = 1 if last and last[:10] == (start - timedelta(days=1)).isoformat() else 0
    days = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        if consecutive >= MAX_CONSECUTIVE:
            rec = {"session": {"label": None, "body_parts": [], "kind": "rest"}, "slot": None,
                   "reasons": [f"rest after {MAX_CONSECUTIVE} training days"]}
        else:
            day_status = {**status, "cycle_position": {**(status.get("cycle_position") or {}), "next_label": label}}
            slots = slots_by_day[day] if day in slots_by_day else full_day(day, zone)
            rec = recommend_today(day_status, slots, outdoor_by_day.get(day, {}), events, day, tz)
        if rec["session"]["kind"] == "rest":
            consecutive = 0
        else:
            consecutive += 1
            done = rec["session"]["label"]
            if done in order:  # advance the rotation past the label actually trained
                label = order[(order.index(done) + 1) % len(order)]
        days.append({"date": day.isoformat(), **rec})
    return days
