# training-hub (Hermes skill)

A Hermes Agent skill that coaches from a [Training Hub](https://github.com/is-ClarkHu/training-hub)
JSON export: where you are in your split, days since each body part was trained, weekly
volume, PRs, sport load, active injuries, and rule-based daily / weekly plans that respect
your calendar's free slots and the outdoor weather (Open-Meteo, no API key).

- Python 3.11+ standard library only; no installs.
- Ships with synthetic demo data (`assets/sample-backup.json`); point `TH_DATA` at your own export.
- All numbers come from `scripts/th.py` (JSON output), so the model narrates instead of computing.

## Install

```bash
hermes skills install <tap>/training-hub   # or copy this folder to ~/.hermes/skills/training-hub
hermes chat -q "/training-hub what should I train today?"
```

## Try it without Hermes

```bash
python3 scripts/th.py status
python3 scripts/th.py today
python3 scripts/th.py week
python3 scripts/th.py journal add --json '{"type":"workout","date":"2026-11-20","items":[{"exercise":"Back squat","sets":[{"weight":100,"reps":5}]}]}'
```

See `SKILL.md` for commands, environment variables and the planner rules.
