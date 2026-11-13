#!/usr/bin/env python3
"""Training Hub CLI. Every command prints one JSON document to stdout.

Exit 0 on success; exit 2 with ``{"error": "..."}`` on bad input. Standard library only.

Environment:
  TH_DATA       backup JSON (default: ../assets/sample-backup.json next to this script)
  TH_STATE_DIR  state directory: plan.json, rebase.json, journal/ (default ~/.th-state)
  TH_JOURNAL_DIR  journal directory (default $TH_STATE_DIR/journal)
  TH_TZ         IANA time zone (default America/Los_Angeles)
  TH_LAT/TH_LON outdoor forecast location (default Los Angeles 34.05 / -118.24)
  TH_REBASE     1 = shift the fixture so its last workout is yesterday (default 1)
  TH_WEATHER    0 = skip the Open-Meteo call (default 1)
  TH_TODAY      YYYY-MM-DD override for "today" (demos and tests)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

from th_adapter import TrainingData, load_backup, merge_journal, reset_rebase, today_local, validate_event  # noqa: E402
from th_analysis import personal_records, status_summary, weekly_volume  # noqa: E402
from th_constraints import outdoor_forecast, parse_free_slots  # noqa: E402
from th_planner import full_day, recommend_today, week_plan  # noqa: E402
from th_state import PlanStore, VersionConflict  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent


class CliError(Exception):
    pass


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise CliError(message)


def _env(name: str, default: str) -> str:
    return os.environ.get(name) or default


def state_dir() -> Path:
    return Path(_env("TH_STATE_DIR", "~/.th-state")).expanduser()


def journal_dir() -> Path:
    return Path(_env("TH_JOURNAL_DIR", str(state_dir() / "journal"))).expanduser()


def tz() -> str:
    return _env("TH_TZ", "America/Los_Angeles")


def today() -> date:
    override = os.environ.get("TH_TODAY")
    return date.fromisoformat(override) if override else today_local(tz())


def load_data() -> TrainingData:
    data_path = Path(_env("TH_DATA", str(SCRIPT_DIR.parent / "assets" / "sample-backup.json"))).expanduser()
    rebase = state_dir() / "rebase.json" if _env("TH_REBASE", "1") == "1" else None
    data = load_backup(data_path, today=today(), rebase_file=rebase)
    return merge_journal(data, journal_dir())


def _read_json_arg(value: str | None):
    if value is None:
        return None
    text = sys.stdin.read() if value == "-" else Path(value).read_text(encoding="utf-8")
    return json.loads(text) if text.strip() else None


def _outdoor(day: date) -> dict:
    if _env("TH_WEATHER", "1") != "1":
        return {"available": False, "error": "weather disabled (TH_WEATHER=0)"}
    lat, lon = float(_env("TH_LAT", "34.05")), float(_env("TH_LON", "-118.24"))
    return outdoor_forecast(lat, lon, day, tz())


def cmd_status(args) -> dict:
    data = load_data()
    return {**status_summary(data, today()), "rebase_days": data.rebase_days}


def cmd_analyze(args) -> dict:
    data = load_data()
    return {"weekly_volume": weekly_volume(data, today(), weeks=args.weeks),
            "personal_records": personal_records(data)}


def _slots_and_events(args):
    slots_raw = _read_json_arg(args.slots_json)
    events = _read_json_arg(args.events_json) or []
    slots = None if slots_raw is None else parse_free_slots(slots_raw, tz())
    return slots, events


def cmd_today(args) -> dict:
    day = today()
    status = status_summary(load_data(), day)
    slots, events = _slots_and_events(args)
    if slots is None:  # standalone: whole day 07:00-21:00 is free
        slots = full_day(day, ZoneInfo(tz()))
    return {"date": day.isoformat(), **recommend_today(status, slots, _outdoor(day), events, day, tz())}


def cmd_week(args) -> dict:
    start = today()
    status = status_summary(load_data(), start)
    slots, events = _slots_and_events(args)
    days = [start + timedelta(days=i) for i in range(7)]
    slots_by_day = {}
    if slots is not None:
        slots_by_day = {d: [s for s in slots if s.start.date() == d] for d in days}
    outdoor_by_day = {d: _outdoor(d) for d in days} if _env("TH_WEATHER", "1") == "1" else {}
    return {"start": start.isoformat(), "days": week_plan(status, slots_by_day, outdoor_by_day, events, start, tz())}


def cmd_outdoor(args) -> dict:
    day = date.fromisoformat(args.date) if args.date else today()
    return {"date": day.isoformat(), **_outdoor(day)}


def cmd_plan(args) -> dict:
    store = PlanStore(state_dir() / "plan.json")
    if args.plan_cmd == "show":
        return store.read()
    plan = _read_json_arg(args.file)
    if not isinstance(plan, dict):
        raise CliError("plan file must hold a JSON object")
    try:
        return {"version": store.write(plan, expected_version=args.expect_version)}
    except VersionConflict as exc:
        raise CliError(f"{exc}; run `plan show` and retry with the current version") from exc


def cmd_journal(args) -> dict:
    try:
        event = validate_event(json.loads(args.json))
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CliError(f"invalid workout event: {type(exc).__name__}: {exc}") from exc
    event.setdefault("id", str(uuid.uuid4()))
    folder = journal_dir() / str(event["date"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{event['id']}.json"
    tmp = folder / f".{event['id']}.tmp"
    tmp.write_text(json.dumps(event, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return {"id": event["id"], "path": str(path)}


def cmd_rebase(args) -> dict:
    if args.reset:
        reset_rebase(state_dir() / "rebase.json")
    data = load_data()
    return {"rebase_days": data.rebase_days, "last_workout_date": data.entries[-1]["date"] if data.entries else None}


def build_parser() -> argparse.ArgumentParser:
    p = JsonArgumentParser(prog="th", description="Training Hub coach CLI (JSON output)")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=JsonArgumentParser)
    sub.add_parser("status").set_defaults(func=cmd_status)
    a = sub.add_parser("analyze")
    a.add_argument("--weeks", type=int, default=4)
    a.set_defaults(func=cmd_analyze)
    for name, func in (("today", cmd_today), ("week", cmd_week)):
        c = sub.add_parser(name)
        c.add_argument("--slots-json", help="free slots JSON file, or - for stdin")
        c.add_argument("--events-json", help="calendar events JSON file, or - for stdin")
        c.set_defaults(func=func)
    o = sub.add_parser("outdoor")
    o.add_argument("--date")
    o.set_defaults(func=cmd_outdoor)
    plan = sub.add_parser("plan")
    plan_sub = plan.add_subparsers(dest="plan_cmd", required=True, parser_class=JsonArgumentParser)
    plan_sub.add_parser("show")
    commit = plan_sub.add_parser("commit")
    commit.add_argument("--expect-version", type=int, required=True)
    commit.add_argument("--file", required=True, help="plan JSON file, or - for stdin")
    plan.set_defaults(func=cmd_plan)
    j = sub.add_parser("journal")
    j_sub = j.add_subparsers(dest="journal_cmd", required=True, parser_class=JsonArgumentParser)
    j_sub.add_parser("add").add_argument("--json", required=True, help="workout event JSON")
    j.set_defaults(func=cmd_journal)
    r = sub.add_parser("rebase")
    r.add_argument("--reset", action="store_true")
    r.set_defaults(func=cmd_rebase)
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = args.func(args)
    except (CliError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
