# Artifact brief

What the explainer artifacts are for, who reads them, and the rules they have
to obey. Written down because the brief changed three times mid-build and each
change invalidated work that was already done.

## The two artifacts

| | Big picture | Internals |
|---|---|---|
| file | `architecture.html` | `internals.html` |
| answers | *what is this thing* | *how does it actually decide* |
| length | one screen of diagram + captions | long-form, sectioned |
| reader leaves knowing | the shape of the system | why a given command went the way it did |

They are companions. Neither should require the other, but the internals page
may assume the reader has seen a system diagram somewhere.

## Who is reading

**Someone who has never seen this project and has no idea what it is.** Not the
author. Not a teammate. Not "you, six months from now". A stranger.

Consequences, all of which were violated in the first drafts:

- Nothing may be referred to before it is introduced. No "the sentence that
  broke it" — *which* sentence, and broke *what*?
- Component names are not explanations. "The rule parser" needs a clause the
  first time it appears.
- Every threshold, weight and constant that appears needs its unit and its
  meaning, not just its value.
- Start with what the thing *is* — a paragraph a reader can stop after and still
  have learned something true.

## The privacy rule

**No personal detail of the author reaches these pages.** They are published to
a URL. That means, concretely, none of:

- real names of people, whether contacts, friends or family
- real place names, institutions, or course names
- acronyms the author personally uses, and their expansions
- actual event or task titles taken from the live database
- anything that reveals routine — training distances, prayer times, standing
  commitments

Examples must be **invented and ordinary**: "book a haircut tomorrow",
"call Mark about the report at 4pm", "buy milk and bread". The point a real
example makes can always be made by a fabricated one; if it cannot, the point
was leaking something.

This applies to the SVG figures and `aria-label`s too — that is where four of
them survived the first sweep.

The Jewish calendar is **in scope and should be included** — but as a
capability of the system ("it computes sundown from a configured latitude, so
it knows when Shabbat begins"), never as a fact about the author's observance.

## Accuracy rules

- **The LLM validates every command.** There is no confidence score high enough
  to skip it. Any phrasing resembling "above the threshold the rules answer
  alone" is wrong: above the threshold the rules answer *first*, the record is
  written immediately, and the model reviews it afterwards.
- **Advisory, not applied.** `self_check_apply: false`. The self-check reasons
  and reports; it does not silently rewrite. Say so.
- Numbers come from `DOCUMENTATION/ASSISTANT_AUDIT_SUMMARY.md` or a script that
  is checked in. If a figure cannot be traced to one of those, cut it.
- Model facts come from `DOCUMENTATION/MODELS.md` — three models, six LLM jobs,
  no embedding model, no classifier model. Include this; the reader asks "how
  many models" almost immediately and the first draft never answered it.
- Where something is unmeasured, say it is unmeasured. The confidence
  multipliers are hand-picked and never validated; that is more interesting
  than pretending otherwise.

## Interactivity

Static figures are the default; interaction has to earn its place by teaching
something a picture cannot. Three that do:

1. **Confidence, live.** Sliders for the multipliers and a sentence to score.
   The reader sees what actually pushes a command over 0.85, and can make the
   formula misbehave — which is the honest thing to show, since it is uncalibrated.
2. **Verb lookup, stepped.** Walk rules 1→4 over a sentence and watch which one
   fires. The failure mode (rule 4 matching a person's name against a verb) is
   only obvious when you step it.
3. **Sundown scrubber.** Drag through a year, watch candle-lighting move, and
   see which occurrences of a repeating event get skipped. A static figure can
   show one date; the whole point is that the boundary moves.

Constraints: plain JS on inline SVG, no libraries, `prefers-reduced-motion`
respected, and every interactive figure must still make its point with JS
disabled — the initial render is the static version.

## Coverage checklist

The internals page has to cover all of these. Items marked ✗ were missing from
a draft that was otherwise finished, and each omission was reported as a gap.

- [x] what the system is, in a paragraph
- [x] the three models and what each decides
- [x] speech → text, and what transcription does to times ("230PM")
- [x] the rule parser: POS tags, slots, the verb table
- [x] the confidence formula, term by term, and that it is uncalibrated
- [x] the routing decision, and that validation is unconditional
- [x] the self-check: what it may and may not change
- [x] escalation when an action matches nothing
- [x] ✗ multiple events in one utterance — splitting, batching, one task per item
- [x] ✗ the two queues: offline command queue, and the background LLM queue
- [x] ✗ tasks as a first-class path, not a variant of events
- [x] ✗ reading the day back — how "what's on today" is answered
- [x] ✗ the personalisation layer: four stores, what each one may do
      (rewrite / annotate / classify / recall)
- [x] the Jewish calendar: sundown, boundaries, what a repeat skips
- [ ] label hierarchy (two levels) — *not built yet; describe as designed, not shipped*
- [ ] the harness and what is still unmeasured

## Publishing

- `internals.html` updates in place at artifact `90addd1e-64fa-4a3f-af4c-ceadddb28dd5`.
- Read before publishing if the session did not publish it (a publish to an
  unread artifact is refused).
- Do not publish a half-genericised page. The privacy rule is all-or-nothing;
  an intermediate state on a live URL is worse than a stale one.
