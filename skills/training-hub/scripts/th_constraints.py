"""Outdoor weather (Open-Meteo, no key) and free-slot parsing. Standard library only."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
HOURLY_FIELDS = ("temperature_2m", "precipitation_probability", "wind_speed_10m")
TEMP_MIN_C, TEMP_MAX_C = 8, 30
PRECIP_MAX_PCT = 30  # exclusive
WIND_MAX_KMH = 30  # exclusive
DAY_START_H, DAY_END_H = 7, 21
FETCH_TIMEOUT_S = 8


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "training-hub-skill/0.1"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:  # noqa: S310 (fixed https host)
        return json.loads(resp.read().decode("utf-8"))


def _suitable(temp, precip, wind) -> bool:
    if temp is None or precip is None or wind is None:
        return False
    return TEMP_MIN_C <= temp <= TEMP_MAX_C and precip < PRECIP_MAX_PCT and wind < WIND_MAX_KMH


def _best_window(hours: list[dict]) -> dict | None:
    best, run = None, []
    for h in hours:
        if DAY_START_H <= h["hour"] < DAY_END_H and h["suitable"]:
            run.append(h["hour"])
            if best is None or len(run) > len(best):
                best = list(run)
        else:
            run = []
    if not best:
        return None
    return {"start": f"{best[0]:02d}:00", "end": f"{best[-1] + 1:02d}:00"}


def outdoor_forecast(lat: float, lon: float, day: date, tz: str,
                     fetch: Callable[[str], dict] | None = None) -> dict:
    """Hourly outdoor suitability for ``day`` (local hours in ``tz``)."""
    query = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "hourly": ",".join(HOURLY_FIELDS),
        "timezone": tz, "start_date": day.isoformat(), "end_date": day.isoformat(),
    })
    try:
        hourly = (fetch or _fetch_json)(f"{OPEN_METEO}?{query}")["hourly"]
        hours = []
        for i, stamp in enumerate(hourly["time"]):
            temp = hourly["temperature_2m"][i]
            precip = hourly["precipitation_probability"][i]
            wind = hourly["wind_speed_10m"][i]
            hours.append({"hour": int(stamp[11:13]), "temp_c": temp, "precip_pct": precip,
                          "wind_kmh": wind, "suitable": _suitable(temp, precip, wind)})
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
    return {"available": True, "hours": hours, "best_window": _best_window(hours)}


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


def _parse_dt(value: str, zone: ZoneInfo) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.replace(tzinfo=zone) if dt.tzinfo is None else dt.astimezone(zone)


def parse_free_slots(obj: list[dict], tz: str = "America/Los_Angeles") -> list[Slot]:
    """``[{"start": iso, "end": iso}]`` → local-time slots, sorted; malformed items are skipped."""
    zone = ZoneInfo(tz)
    slots = []
    for item in obj or []:
        try:
            slot = Slot(_parse_dt(item["start"], zone), _parse_dt(item["end"], zone))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if slot.end > slot.start:
            slots.append(slot)
    return sorted(slots, key=lambda s: s.start)
