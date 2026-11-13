# Training Hub skill for Hermes Agent

A [Hermes Agent](https://hermes-agent.nousresearch.com/docs) skill that coaches from a
Training Hub export: where you are in your training split, recovery per body part, weekly
volume, personal records, weather-aware daily and weekly plans, and logging a workout from a
chat message.

It is the custom skill of a CSCI 599 (Agentic AI, Fall 2026) personal-assistant project.
The bundled data (`skills/training-hub/assets/sample-backup.json`) is a test fixture.

## Install (Hermes skill tap)

```bash
hermes skills tap add is-ClarkHu/hermes-training-hub-skill
hermes skills install training-hub
hermes chat --oneshot -q "/training-hub what should I train today?"
```

Requirements: Python 3.11+ standard library only (no pip packages). Weather uses the free
Open-Meteo API; set `TH_WEATHER=0` to work offline.

## What it does

| Command (run by the agent) | Result |
|---|---|
| `th.py status` | Cycle position, last workout, active injuries, weekly volume |
| `th.py today [--slots-json F --events-json F]` | Today's session, time slot and reasons (calendar- and weather-aware) |
| `th.py week` | A 7-day plan that respects rest days and the split order |
| `th.py analyze --weeks 4` | Volume per body part and personal records |
| `th.py outdoor [--date YYYY-MM-DD]` | Hourly forecast and an outdoor-training verdict |
| `th.py plan show` / `th.py plan commit --expect-version N --file F` | Read or save the current plan |
| `th.py journal add --json '<event>'` | Log a workout reported in chat (append-only journal) |

See [`skills/training-hub/SKILL.md`](skills/training-hub/SKILL.md) for the full procedure the
agent follows.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `TH_DATA` | bundled sample fixture | Path to a Training Hub backup JSON |
| `TH_STATE_DIR` | `~/.th-state` | Plan, rebase offset and journal |
| `TH_JOURNAL_DIR` | `$TH_STATE_DIR/journal` | Where logged workouts are appended |
| `TH_LAT` / `TH_LON` | Los Angeles | Forecast location |
| `TH_WEATHER` | `1` | `0` disables the forecast call |
| `TH_TODAY` | today | Date override for demos |

## Safety

The skill only reads the backup file and appends to its own journal directory. It never
sends data anywhere except the anonymous Open-Meteo forecast request (latitude/longitude).

## License

MIT, see [LICENSE](LICENSE). Privacy notice for the companion test assistant:
[PRIVACY.md](PRIVACY.md).
