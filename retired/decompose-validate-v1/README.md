# decompose_validate v1 — retired 2026-09-08

The **ported** v1 implementation of the stage. It came across from the old brain
unchanged when the engine was rebuilt, so the v2 rewrite replaced the
orchestration around it and left its interior alone. `PLAN.md` in the live folder
was written to track exactly that debt.

    validate.py    880 lines, 17 named rules, the transcript-wide date machinery
    decompose.py   the item-splitting and text-repair pass

## Why it was replaced

`validate.py` decided dates by reading the WHOLE transcript, building a flat list
of date expressions, and matching them to events **by order**:

```python
rel = relative_dates(transcript)
orig_event_dates = {getattr(i, "date", None) for _, a, i in pairs if a == "create_event"}
ev_idx = 0
...
_rule_relative_date_pin(state, intent, rel, recur, ev_idx, n_events,
                        orig_event_dates, transcript)
```

That is a bug class rather than a bug. The list is legitimately **shorter** than
the number of events — the bare-ordinal branch correctly refuses to claim a
month-named ordinal — so on

> "add gym on tuesday … and add yoga on tuesday … and add my conference on the
> 20th of November"

two dates are produced for three events and the conference lands in September. It
caused commit `a987aba` ("a repeated relative date silently overwriting other
events' real dates").

## What replaced it

`resolve.py` (decompose) and `checks.py` (validate), which take **one item's own
words** and never ask which event a date belongs to — segmentation already
decided that. Measured on the stage's own dataset before being wired: 99.9% train
/ 98.7% sealed all-fields-exact, 0 inventions, 0 contradictions, 0 model calls.

The swap was accepted on the audit regression floor showing **parity** — 72%
exact / 75% recall, the same 7 failures as this code produced.

## What did NOT come from here

Nine date rules were deleted outright. The rest were never value resolution and
moved to modules named for what they do:

| went to | rules |
|---|---|
| `targeting.py` | `anaphor_guard`, `move_time_fill`, `create_from_remove_guard`, `relative_dates` (now only to answer "does the command name a date at all?") |
| `object_rules.py` | `junk_event_drop`, `question_creates_nothing`, `interrogative_create_asks_first`, `morning_title_guard`, `cadence_round_and_announce`, `past_date_bump`, `now_means_now` |
| `observance_gate.py` | `_observance_verdict` — logic unchanged, but it now produces a **FLAG** instead of blocking the item (Gil: a blocked item is a command that silently did nothing) |
| `text_helpers.py` | `end_is_exclusive`, `named_weekdays`, `unsupported_cadence`, `at_times`, `spoken_times`, `is_placeholder_title`, `bare_hour_pm` |

## Reverting or comparing

`git tag decompose-validate-v1` marks the last commit that ran this code. The tag
is the full-fidelity truth; these two files are the quick reference.
