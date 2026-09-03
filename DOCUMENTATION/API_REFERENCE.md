# API reference

Generated from `assistant/api/server.py` by `python -m scripts.gen_api_reference` — do not edit by hand.
All endpoints are served by the Mac at `http://<tailscale-ip>:8080`; the iOS app is the only client. Path parameters use Flask syntax (`<int:id>`).

## /health

| Method | Path | What it does |
|---|---|---|
| `GET` | `/health` |  |

## /voice

| Method | Path | What it does |
|---|---|---|
| `POST` | `/voice` | Accept a multipart audio file, transcribe via Whisper, then execute. |
| `POST` | `/voice/stream` | Same as POST /voice but streams the thinking trace live as NDJSON. |
| `POST` | `/voice/text` | Accept a JSON transcript and execute directly (skips STT). |
| `GET` | `/voice/verify/<token>` | Poll for background LLM verification of a rule-path voice command. |

## /vocab

| Method | Path | What it does |
|---|---|---|
| `GET` | `/vocab` |  |
| `POST` | `/vocab` |  |
| `DELETE` | `/vocab/<path:word>` |  |
| `PATCH` | `/vocab/<path:word>` | Edit a word the settings screens are showing. |
| `POST` | `/vocab/alias` | Teach a correction: {"wrong": "Kyira", "right": "Kyra"}. |
| `POST` | `/vocab/bulk` | Add many words at once: {"words": ["Kyra", ...]} |
| `POST` | `/vocab/import` | Mine vocabulary candidates. Body: {"text": "..."} (WhatsApp export / notes) |
| `GET` | `/vocab/onboarding` |  |
| `POST` | `/vocab/onboarding` | {"answers": {"people": ["Kyra"], ...}, "presets": ["tefillah"], "done": true} |
| `POST` | `/vocab/preview` | Dry-run: what would the corrector do to this text? (no learning) |
| `PATCH` | `/vocab/settings` |  |

## /changes

| Method | Path | What it does |
|---|---|---|
| `GET` | `/changes` | A cheap "has anything changed?" token for the phone to poll. |

## /pending

| Method | Path | What it does |
|---|---|---|
| `GET` | `/pending` |  |
| `DELETE` | `/pending/<int:pending_id>` |  |
| `POST` | `/pending/<int:pending_id>/retry` |  |

## /memory

| Method | Path | What it does |
|---|---|---|
| `GET` | `/memory` |  |
| `DELETE` | `/memory/<int:example_id>` |  |
| `POST` | `/memory/<int:example_id>/feedback` | {"feedback": "approved"\|"corrected"\|"rejected", "correction": [...]?, "notes": "..."} |
| `GET` | `/memory/similar` |  |
| `GET` | `/memory/unreviewed` | Commands with no feedback yet (for the phone's review screen). |
| `POST` | `/memory/unreviewed/skip` | Dismiss the whole review backlog (e.g. stale seeded history). |

## /timers

| Method | Path | What it does |
|---|---|---|
| `GET` | `/timers` |  |
| `POST` | `/timers` |  |
| `DELETE` | `/timers/<int:tid>` |  |
| `PATCH` | `/timers/<int:tid>` |  |
| `GET` | `/timers/<int:tid>/sessions` |  |
| `POST` | `/timers/<int:tid>/sessions` | Log a session that already happened ("I forgot to start the timer"). |
| `POST` | `/timers/<int:tid>/start` |  |
| `POST` | `/timers/<int:tid>/stop` |  |

## /timer_sessions

| Method | Path | What it does |
|---|---|---|
| `DELETE` | `/timer_sessions/<int:sid>` |  |
| `PATCH` | `/timer_sessions/<int:sid>` |  |

## /counters

| Method | Path | What it does |
|---|---|---|
| `GET` | `/counters` |  |
| `POST` | `/counters` |  |
| `DELETE` | `/counters/<int:cid>` |  |
| `PATCH` | `/counters/<int:cid>` |  |
| `POST` | `/counters/<int:cid>/cashout` |  |
| `GET` | `/counters/<int:cid>/payouts` |  |
| `POST` | `/counters/<int:cid>/press` |  |
| `GET` | `/counters/<int:cid>/presses` |  |

## /counter_presses

| Method | Path | What it does |
|---|---|---|
| `DELETE` | `/counter_presses/<int:pid>` |  |

## /categories

| Method | Path | What it does |
|---|---|---|
| `GET` | `/categories` |  |
| `POST` | `/categories` | {"name": "Volunteering", "color": "#…", "alt": "#…", "keywords": [...], "add_keywords": [...]} |
| `DELETE` | `/categories/<path:name>` |  |
| `POST` | `/categories/classify` |  |
| `POST` | `/categories/recolor` | Apply categories/colours to existing events. ?force=1 re-does everything. |

## /events

| Method | Path | What it does |
|---|---|---|
| `GET` | `/events` |  |
| `POST` | `/events` |  |
| `DELETE` | `/events/<int:event_id>` |  |
| `GET` | `/events/<int:event_id>` |  |
| `PATCH` | `/events/<int:event_id>` |  |

## /todos

| Method | Path | What it does |
|---|---|---|
| `GET` | `/todos` |  |
| `POST` | `/todos` |  |
| `DELETE` | `/todos/<int:todo_id>` |  |
| `PATCH` | `/todos/<int:todo_id>` |  |
| `PATCH` | `/todos/<int:todo_id>/toggle` |  |
| `DELETE` | `/todos/completed` |  |
| `POST` | `/todos/reorder` |  |
| `POST` | `/todos/sync` |  |

## /tags

| Method | Path | What it does |
|---|---|---|
| `GET` | `/tags` |  |
| `POST` | `/tags` |  |
| `DELETE` | `/tags/<path:name>` |  |

## /courses

| Method | Path | What it does |
|---|---|---|
| `GET` | `/courses` |  |
| `POST` | `/courses` |  |
| `DELETE` | `/courses/<int:course_id>` |  |
| `PATCH` | `/courses/<int:course_id>` |  |
| `GET` | `/courses/<int:course_id>/assignments` |  |

## /assignments

| Method | Path | What it does |
|---|---|---|
| `GET` | `/assignments` | Return all assignments across every course. |
| `POST` | `/assignments` |  |
| `DELETE` | `/assignments/<int:asgn_id>` |  |
| `PATCH` | `/assignments/<int:asgn_id>` |  |
| `PATCH` | `/assignments/<int:asgn_id>/toggle` |  |
| `DELETE` | `/assignments/completed` |  |

## /workout

| Method | Path | What it does |
|---|---|---|
| `GET` | `/workout/exercises` |  |
| `POST` | `/workout/exercises` |  |
| `GET` | `/workout/plan-items` | Scheduled sessions in a date range — what the phone's day view asks for. |
| `PATCH` | `/workout/plan-items/<item_id>` |  |
| `GET` | `/workout/plans` |  |
| `DELETE` | `/workout/plans/<plan_id>` |  |
| `GET` | `/workout/plans/<plan_id>` |  |
| `GET` | `/workout/sessions` |  |
| `POST` | `/workout/sessions` |  |
| `DELETE` | `/workout/sessions/<session_id>` |  |
| `PATCH` | `/workout/sessions/<session_id>` |  |
| `GET` | `/workout/templates` |  |
| `POST` | `/workout/templates` |  |
| `DELETE` | `/workout/templates/<template_id>` |  |
| `PATCH` | `/workout/templates/<template_id>` |  |
| `PATCH` | `/workout/templates/<template_id>/approve` |  |

## /observance

| Method | Path | What it does |
|---|---|---|
| `GET` | `/observance` | Training availability per day: what is blocked, and which windows remain. |
| `DELETE` | `/observance/location` | Forget the reported position and go back to the configured place. |
| `GET` | `/observance/location` | Where sundown is currently computed for, and where that came from. |
| `POST` | `/observance/location` | A device reporting where it is. |

## /config

| Method | Path | What it does |
|---|---|---|
| `GET` | `/config` |  |
| `PATCH` | `/config` |  |

## /holidays

| Method | Path | What it does |
|---|---|---|
| `GET` | `/holidays` |  |

## /calendar_sources

| Method | Path | What it does |
|---|---|---|
| `GET` | `/calendar_sources` |  |
| `POST` | `/calendar_sources` |  |
| `DELETE` | `/calendar_sources/<int:source_id>` |  |
| `PATCH` | `/calendar_sources/<int:source_id>` |  |
