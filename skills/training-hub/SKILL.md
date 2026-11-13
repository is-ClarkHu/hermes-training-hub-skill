---
name: training-hub
description: "Coach from a Training Hub export: cycle position, recovery, volume, PRs, weather-aware daily and weekly plans, and workout logging from chat."
version: 0.1.0
author: is-ClarkHu
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Fitness, Training, Planning, Coaching, Weather]
    category: productivity
---

# Training Hub

Answers training questions from a Training Hub JSON export (synthetic demo data ships
in `assets/sample-backup.json`). A stdlib-only CLI, `scripts/th.py`, does all the
counting and planning and prints JSON. **Every number you report (days since
trained, sets, kg, PRs, hours, dates, versions) must come from CLI output. Never
compute or estimate them yourself.** Your job is to run the CLI and explain its
output in plain words.

## When to Use

- "What should I train today?" / "Plan my week." / "I can't train tomorrow."
- "How long since I trained legs?" / "Show my volume / PRs / cycle progress."
- The user reports a workout in chat ("did legs: squat 100x5x3, rdl 80kg x 8").
- Morning briefing or evening recap needs the training section.

## Procedure

Run the CLI by its full path (the path below is filled in when the skill loads):
`python3 ${HERMES_SKILL_DIR}/scripts/th.py <command>`.

| Need | Command |
|---|---|
| Overall status (cycle, recovery, injuries, goal) | `python3 ${HERMES_SKILL_DIR}/scripts/th.py status` |
| Volume per body part and PRs | `python3 ${HERMES_SKILL_DIR}/scripts/th.py analyze --weeks 4` |
| Today's session | `python3 ${HERMES_SKILL_DIR}/scripts/th.py today [--slots-json FILE\|-] [--events-json FILE\|-]` |
| 7-day plan | `python3 ${HERMES_SKILL_DIR}/scripts/th.py week [--slots-json ...] [--events-json ...]` |
| Weather verdict | `python3 ${HERMES_SKILL_DIR}/scripts/th.py outdoor [--date YYYY-MM-DD]` |
| Current saved plan | `python3 ${HERMES_SKILL_DIR}/scripts/th.py plan show` |
| Save a plan | `python3 ${HERMES_SKILL_DIR}/scripts/th.py plan commit --expect-version N --file FILE\|-` |
| Log a workout | `python3 ${HERMES_SKILL_DIR}/scripts/th.py journal add --json '<event>'` |
| Re-anchor demo dates | `python3 ${HERMES_SKILL_DIR}/scripts/th.py rebase [--reset]` |

- Free slots and events are optional JSON lists, e.g. from a calendar skill:
  slots `[{"start": iso, "end": iso}]`, events `[{"title", "start", "end"}]`.
  Without slots the whole day 07:00–21:00 counts as free.
- To change the saved plan: `plan show`, edit, then `plan commit` with the version
  you read. On a version-conflict error, run `plan show` again and redo the edit.
- Logging a workout from chat: parse the message into this event, then run
  `journal add`. Use exercise names as the user wrote them; unknown names are fine.

```json
{"type": "workout", "date": "YYYY-MM-DD", "cycle_day_label": "C",
 "items": [{"exercise": "Back squat", "sets": [{"weight": 100, "reps": 5}, {"weight": 100, "reps": 5}]}]}
```

  `"100x5x3"` means 3 sets of 5 reps at 100 kg. `cycle_day_label` is optional. Echo
  the returned `id` and a one-line summary back to the user.

Files: `scripts/th.py` (CLI), `scripts/th_adapter.py` (load + journal merge + date
rebase), `scripts/th_analysis.py` (metrics), `scripts/th_constraints.py` (Open-Meteo
weather, free slots), `scripts/th_planner.py` (rules), `scripts/th_state.py`
(versioned plan file), `assets/sample-backup.json` (synthetic data).

Environment: `TH_DATA` (export path), `TH_STATE_DIR` (default `~/.th-state`),
`TH_JOURNAL_DIR`, `TH_TZ` (default `America/Los_Angeles`), `TH_LAT` / `TH_LON`,
`TH_REBASE` (`1` = last demo workout becomes yesterday), `TH_WEATHER` (`0` = offline),
`TH_TODAY` (date override for demos).

## Pitfalls

- Do not do arithmetic on training numbers; rerun the CLI instead.
- `reasons` in `today` / `week` output are the planner's rules (e.g. `frisbee
  tomorrow: avoid heavy legs`, `rain/wind: moved indoors`, `modify: <injury>`).
  Explain them; do not invent others.
- An `{"error": ...}` output with exit code 2 means bad input. Fix the arguments;
  do not guess an answer.
- `outdoor` returns `"available": false` when the weather API is unreachable. Say the
  forecast is unavailable instead of guessing the weather.
- Keep `TH_STATE_DIR` on local disk: the plan file lock needs POSIX `flock`.

## Verification

- `python3 ${HERMES_SKILL_DIR}/scripts/th.py status` prints JSON with `cycle_position.next_label` and
  `days_since_trained`.
- After `journal add`, `status` shows the new `last_workout_date`.
- `plan commit` with a stale `--expect-version` fails with a version error.
