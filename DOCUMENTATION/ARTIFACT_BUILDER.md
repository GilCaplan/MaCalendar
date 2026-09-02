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

## Compliance: the pages are downstream of the code

The artifacts describe a system that changes weekly. Every constant they quote
— the routing threshold, the multipliers, how many verbs are in the table, how
many past commands are retrieved — is a number someone can change in an
afternoon without ever opening the HTML. Two had already drifted before anyone
checked: the pages claimed 706 tests when there were 793, and 55% of the
example pool unreviewed when purging the test entries had moved it to 48%.
Neither error mattered on its own. Both are the kind that make a reader stop
trusting the parts they cannot check.

So the agreement is enforced, not promised.

**`tests/unit/test_artifact_claims.py` is the contract.** It reads each value
out of the code and asserts the artifact says the same thing. It runs in CI. If
you change a constant the pages quote, that test goes red and names the file to
edit. Currently mechanised:

| Claim in the artifact | Read from |
|---|---|
| routing threshold | `rule_parser.RULE_THRESHOLD` |
| the four confidence multipliers | the body of `_compute_confidence` |
| size of the verb table | `len(INTENT_MAP)` |
| actions reachable by rule | `len(set(INTENT_MAP.values()))` |
| "eight of the fifteen actions are tasks" | subclasses of `BaseAction` |
| how many past commands are retrieved | default `k` of `CommandMemory.retrieve` |
| the 60/40 similarity weights | the scoring line in `memory.py` |
| candidate pool size | the `LIMIT` in the retrieval query |
| the three model names and sizes | `config.example.yaml`, `spacy.load(...)` |
| "no embedding model" | that retrieval still uses `SequenceMatcher` |
| the test count | collecting the suite |
| every measured accuracy | that the run is still in `ASSISTANT_AUDIT_SUMMARY.md` |
| no personal vocabulary on a public page | the real word list, minus `public_words.txt` |

**When you add a claim, add its check.** A number in the artifact with no row
in that table is a number that will be wrong within a month. If a claim is
genuinely unmechanisable, it belongs in the summary document with a date, and
the artifact cites it from there.

### Where measured numbers live

`ASSISTANT_AUDIT.md` is **regenerated on every run**, so it can never be the
source for a published figure. Copy the conclusion into
`ASSISTANT_AUDIT_SUMMARY.md` — which is append-only — and cite that. The
compliance test checks the artifact's headline accuracy still appears there,
which is what stops a stale number outliving the run that produced it.

### The two accuracy rules that keep being got wrong

- **The LLM validates every command.** There is no confidence score high enough
  to skip it. Any phrasing resembling "above the threshold the rules answer
  alone" is wrong: above the threshold the rules answer *first*, the record is
  written immediately, and the model reviews it afterwards.
- **Advisory, not applied.** `self_check_apply: false`. The self-check reasons
  and reports; it does not silently rewrite. Say so.

Where something is unmeasured, say it is unmeasured. The confidence multipliers
are hand-picked and have never been validated against outcomes; that is more
interesting than pretending otherwise, and it is the honest reason the page has
a section called "what is not measured".

## Structure: abstract first, then down one level at a time

The failure mode of a technical explainer is starting at the level the author
last worked at. The pages are layered instead, and **a reader may stop at the
end of any layer with a true, complete picture at that resolution** — each one
is a whole answer, not a fragment of the next.

**Layer 0 — what it is.** One paragraph, no components named beyond "a
laptop". A reader who stops here can describe the system to someone else.

**Layer 1 — the parts.** The three models, what each decides, and the shape of
the path from speech to a saved record. Names introduced, no mechanism yet.
A reader who stops here knows what is doing the deciding.

**Layer 2 — the decisions.** One section per decision the system makes, in the
order it makes them: how a sentence is read, what routes it, what is checked
before writing, what happens afterwards. This is where numbers appear, and
every one of them is in the compliance table above.

**Layer 3 — the seams.** The cases that only exist because the layers meet:
several things in one sentence, the two queues, tasks behaving unlike events,
what happens when an action refers to something that does not exist. These
are the sections a reader skips unless they hit the behaviour — and the
sections that make the page worth keeping when they do.

**Layer 4 — what is not known.** Everything unmeasured, with the reason. Last,
because it is only meaningful once the reader knows what was measured.

Two rules that keep the layers from collapsing into each other:

- **Nothing is referred to before it is introduced.** No "the sentence that
  broke it" before the sentence, and no component name without a clause the
  first time it appears.
- **Detail goes down, not sideways.** If a section needs a fact from a deeper
  layer, that fact is in the wrong place — move the section, or state the fact
  at the resolution the section is written at. Completeness is a property of
  the whole page, not of each paragraph, and a paragraph that tries to be
  complete on its own is how these pages overflow.

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
