# Decompose · Validate

Combined into one folder (Gil, 2026-09-08) because they are one concern:
turning items into things that can actually be built, and repairing them when
they are wrong. **The functions stay separate** — this is a folder, not a
merge.

## The shape, which is not a straight line

`validate` runs **twice**, and that is deliberate:

```
segmentation -> decompose -> validate (TEXT pass) -> generate -> validate_objects
```

The second pass runs **after** generate because its rules need `item.intent` to
exist. That is where date resolution lives: `relative_dates()` reads the RAW
TRANSCRIPT deterministically, `_rule_relative_date_pin` attaches each date to
the right event in order, and `_rule_past_date_bump` rolls anything still past.

Reading the transcript rather than trusting the model is why `"the 15th"` is
reliable: on the 8th it resolves to the 15th of this month, on the 20th to the
15th of next, and on 20 December to 15 January. A named month is explicitly
guarded so a bare-ordinal rule cannot hijack `"the 12th of August"`.

## decompose

Recursive per-item breakdown, bounded depth 2, ids `item_1-1`:

- two times → two events
- quantity → one task with units
- recurrence → cadence + date range + times (`daily|weekly|monthly` only, and
  the rounding is **announced in the reply**, never done quietly)
- multi-item verb sharing
- guests kept with their event

Deterministic where possible; the model only when the item is ambiguous.

## validate

Three jobs, each an ordered pipeline of named, unit-tested rules with signature
`(items, transcript, ctx) -> (items, list[Fix])`. Every fix lands in the trace.

1. **Format** — schema, `past_date_bump`, `ordinal_month_guard`, `am_pm_fix`,
   `end_before_start`, `until_exclusive` / `through_inclusive`,
   `weekly_start_day`, `anaphor_guard`, `cadence_round_and_announce`
2. **Text repair** — garbled fragments cleaned before generation
3. **Observance gate — AI-created events only.** An event landing inside
   Shabbat or yom tov must be leyning, a meal or davening; on a fast day a meal
   must not be booked before the fast ends. A disallowed item is **not silently
   dropped or moved** — the reply says why, and offers the nearest legal slot.
   Manual edits through the GUI stay unrestricted.

## Status

**Gil is designing this next.** The folder is ready; the pipeline is unchanged.

An open question already on the table: date **reading** is arguably structural
and belongs in `decompose` (which already reads times to split "two times → two
events"), while date **repair** is a fix and belongs in `validate`. Today
decompose reads the times and throws the reading away, and validate re-derives
it from the transcript with index-pinning gymnastics — which is the fragile
machinery that broke in commit `a987aba`. Moving it is a CONTRACT change, not
a cleanup.
