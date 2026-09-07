# External datasets for training/eval data

> **Standing conversion rule (Q9, 2026-09-07):** these corpora label
> first-person create questions as creates; our ruling makes them PROPOSALS.
> Every converter must run `segment.is_interrogative_create` on each row and
> remap matches to `action: "propose"` — before the conventions-pass sample
> goes to Gil, so he reviews residual disagreements, not ones already ruled.

Research pass (2026-09-07) looking for **public** datasets that can be adapted into
rows matching our schema:

```
{ text: "<spoken-style utterance>",
  expect: { events: N, tasks: M,
            action: create_event | create_todo | query | delete_* | complete_todo | update_* | mixed,
            atomic: bool,
            slots: { title, date_phrase, time_phrase, quantity, recurrence, attendee } } }
```

Everything below was checked against the real dataset card, README, or a
downloaded sample — not just a paper abstract. Samples were pulled to a local
scratch dir (never into this repo) with `curl`/`tar`/`unzip`; a few raw rows
are quoted where the license allows it. This file is standalone research —
nothing here has been wired into `dataset/` (that tree is owned by another
work stream right now; see `CLAUDE.md` "Two work streams, two checkouts").

15 candidates assessed. Ranked TOP 5 and adoption plans are at the bottom;
dead ends and lower-priority items are grouped after that.

---

## 1. MASSIVE (Amazon Science)

- **Link:** [huggingface.co/datasets/AmazonScience/massive](https://huggingface.co/datasets/AmazonScience/massive) · [github.com/alexa/massive](https://github.com/alexa/massive) · raw data: `https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz` (the HF loader script points here directly — no login, no LFS auth needed; the naive `resolve/main/data/*.jsonl.gz` path on the HF repo 404s, the loader fetches from S3 instead).
- **License:** CC-BY-4.0 (Amazon-owned copyright, confirmed from the LICENSE file in the tarball).
- **Size:** ~1.19M utterances across 51/52 locales, ~16.5k per locale. **en-US: 16,520 rows** (downloaded and inspected in full).
- **Domains/intents relevant to us** (en-US counts, verified by direct count over all 16,520 rows):
  - `calendar` scenario — **2,370** rows: `calendar_set` 1,150, `calendar_query` 794, `calendar_remove` 426
  - `alarm` scenario — 550 rows: `alarm_set` 254, `alarm_query` 183, `alarm_remove` 113
  - `lists` scenario — 793 rows: `lists_createoradd` 241, `lists_query` 299, `lists_remove` 253
  - `datetime` scenario — 578 rows: `datetime_query` 502, `datetime_convert` 76
  - (18 scenarios / 60 intents total; the rest — `play`, `qa`, `email`, `iot`, `weather`, `transport`, `news`, `social`, `music`, `audio`, `cooking`, `takeaway`, `recommendation`, `general` — are off-domain but still contribute wording variety for a general-purpose voice-assistant register.)
- **Annotation shape:** intent + scenario labels, **slots kept as inline bracketed spans in the text** (not pre-resolved to ISO), e.g. `remind me at [time : one p. m.]`. Also ships `utt` (plain) and `annot_utt` (bracketed) side by side, which is exactly the "spoken text with slot spans, not resolved dates" shape we want. Quality-checked by multiple crowdworkers (intent/slot/grammar/spelling scores per row) rather than raw crowdsource dump.
- **Spoken-style:** yes — natural utterances, not templated. Verified rows:
  ```
  {"utt": "remind me after ten minutes", "annot_utt": "remind me [time : after ten minutes]", "intent": "calendar_set"}
  {"utt": "set a notification for sports game", "annot_utt": "set a notification for [event_name : sports game]", "intent": "calendar_set"}
  {"utt": "create a new to do list", "annot_utt": "create a new [list_name : to do] list", "intent": "lists_createoradd"}
  ```
- **Mapping sketch:**
  - `calendar_set` → `create_event` (or `create_todo` when the object is a reminder-to-self with no clock time — see note below); `event_name` → `title`, `time`/`date` slots → `time_phrase`/`date_phrase`.
  - `calendar_remove` → `delete_event`; `calendar_query` → `query`.
  - `alarm_set`/`alarm_remove`/`alarm_query` → same three actions, alarms fold into our `create_event`/`delete_event`/`query` since we don't model a separate alarm kind.
  - `lists_createoradd`/`lists_remove`/`lists_query` → `create_todo`/`delete_todo`/`query`; `list_name` slot doesn't map cleanly to `title` (it names the *list*, not a task) — needs a small heuristic (single-item add → `title`=item; bare "create a list" → no clean single-task mapping, drop or treat as `mixed`/skip).
  - `datetime_query` → `query` (pure time-lookup, no event) — useful negative/edge examples for the kind-decision problem (a "what time is it" utterance must NOT become a calendar row).
  - **Underivable directly:** `atomic`/`events`/`tasks` counts (every MASSIVE row is single-intent by construction, so `events`/`tasks` are always 0 or 1 and `atomic` is always true — MASSIVE contributes zero multi-intent examples); `recurrence` and `attendee` are present in the text sometimes but not tagged as their own slot types (would need to notice `date`/`time` slot text containing "every"/recurrence words, or scan free text for names).
  - Note: MASSIVE's calendar/alarm rows are visibly drawn from the **same underlying prompt pool** as dataset #3 below (xliuhw/NLU-Evaluation-Data) — e.g. `remind me if anything else happens` and `remind me to do something then` appear verbatim in both. MASSIVE is the cleaner, quality-scored descendant (via SLURP); treat the two as one family rather than double-counting their volume.
- **Adaptation effort:** **S.** One JSON pass: split `scenario`+`intent` into our `action`, regex-extract the `[slot : text]` spans into `slots`, done.
- **What it buys us:** directly hits priority #2 (calendar/alarm/lists domain rows, count in the thousands) and #3 (datetime kept as text). Does **not** touch priority #1 (multi-intent) — every row is single-intent.

## 2. TOPv2 (Facebook/Meta Research)

- **Link:** dataset card / paper: [aclanthology.org (Chen et al. 2020, EMNLP Findings)](https://aclanthology.org/2020.findings-emnlp.10/) · direct download (redirect verified): `https://fb.me/TOPv2Dataset` → `https://dl.fbaipublicfiles.com/topv2/TOPv2_Dataset.zip` (5.3MB, downloaded and unzipped — no signup, no form).
- **License:** **CC-BY-SA 4.0** (LICENSE file present in the zip, verified).
- **Size:** 180,566 rows total (train+eval+test) across 8 domains. Per-domain (all splits): `weather` 31,406, `alarm` 30,491, `navigation` 30,047, `reminder` 26,136, `music` 17,323, `timer` 17,395, `messaging` 14,605, **`event` 13,163**.
- **Domains relevant to us:** `alarm` (30.5k), `reminder` (26.1k), `event` (13.2k), `timer` (17.4k) = **~87k rows** directly calendar/reminder/task-adjacent. Also ships low-resource splits (10/25/50/100/250/500/1000 examples-per-intent) for `reminder` and `weather`, useful if we want to study data-efficiency separately.
- **Annotation shape:** **nested/compositional semantic parse trees** — `domain<TAB>utterance<TAB>semantic_parse`, e.g.:
  ```
  reminder  remind me to take my meds at 8am and 6pm daily  [IN:CREATE_REMINDER remind [SL:PERSON_REMINDED me ] to [SL:TODO take my meds ] [SL:RECURRING_DATE_TIME [IN:GET_RECURRING_DATE_TIME [SL:DATE_TIME at 8 am ] and [SL:DATE_TIME 6 pm ] [SL:FREQUENCY daily ] ] ] ]

  reminder  I need to text Nicquana tonight at 7pm. Can you remind me?  [IN:CREATE_REMINDER I need to [SL:TODO [IN:SEND_MESSAGE text [SL:RECIPIENT Nicquana ] [SL:DATE_TIME tonight at 7 pm ] ] ] . Can you remind [SL:PERSON_REMINDED me ] ? ]

  event  Music events in Minneapolis this weekend  [IN:GET_EVENT [SL:CATEGORY_EVENT Music events ] in [SL:LOCATION Minneapolis ] [SL:DATE_TIME this weekend ] ]

  alarm  set the alarm to ring at 4.30am on Monday  [IN:CREATE_ALARM set the alarm to ring [SL:DATE_TIME at 4.30am on Monday ] ]
  ```
  Reminder-domain intents (verified by scanning all 3 splits): `CREATE_REMINDER`, `DELETE_REMINDER`, `UPDATE_REMINDER`, `UPDATE_REMINDER_DATE_TIME`, `UPDATE_REMINDER_TODO`, `GET_REMINDER*`, plus nested `SEND_MESSAGE`/`GET_EVENT` inside reminder utterances — **this is a real, naturally-occurring compositional/multi-intent set**, not synthetically concatenated. Alarm intents: `CREATE_ALARM`, `DELETE_ALARM`, `UPDATE_ALARM`, `GET_ALARM`, `SNOOZE_ALARM`, `SILENCE_ALARM`.
- **Spoken-style:** yes, crowdsourced natural utterances (typos like "his week" preserved).
- **Mapping sketch:**
  - `CREATE_REMINDER`/`CREATE_ALARM` → `create_event` or `create_todo` (a reminder with a clock `DATE_TIME` reads as an event; a bare "remind me to X" with only a `TODO` slot and no time reads as a todo — needs the same kind-decision heuristic we already need elsewhere).
  - `SL:TODO` → `title`; `SL:DATE_TIME`/`SL:RECURRING_DATE_TIME` → `date_phrase`/`time_phrase`; `SL:FREQUENCY` → `recurrence`; `SL:PERSON_REMINDED`/`SL:RECIPIENT`/`SL:CONTACT` → `attendee`.
  - `DELETE_REMINDER`/`DELETE_ALARM` → `delete_todo`/`delete_event`; `UPDATE_*` → `update_*`; bare `GET_REMINDER`/`GET_ALARM`/`GET_EVENT` → `query`.
  - **The nested `IN:` inside `IN:` rows are our best free source of real `mixed`/multi-intent, multi-slot examples** — a row like the `SEND_MESSAGE`-inside-`CREATE_REMINDER` example above is legitimately two asks in one sentence (send a text, and remind me to do it), which is exactly our weakest family.
  - **Underivable:** exact `events`/`tasks` counts need a small tree-walker (count `IN:CREATE_*`/`IN:GET_*` nodes) rather than a flat mapping — call this Medium, not Small, for the compositional rows specifically; the flat (non-nested) majority of rows map with a one-line regex.
- **Adaptation effort:** **M** overall (S for flat single-intent rows, a short recursive-descent parse of the bracket tree for the nested ~10-15% of rows that carry two `IN:` nodes).
- **What it buys us:** the single best fit for priority #1 (compositional/multi-intent, and it's *real* multi-intent, not synthetic concatenation) **and** priority #2 (alarm/reminder/event domains, ~87k rows) **and** #3 (datetime kept as raw text spans, plus an explicit `FREQUENCY`/`RECURRING_DATE_TIME` slot for recurrence). Recommended top pick.
- Sibling note: **MTOP** (Li et al. 2021, [arxiv.org/abs/2008.09335](https://arxiv.org/abs/2008.09335), download `https://fb.me/mtop_dataset`) is the multilingual extension of the same TOP schema (11 domains incl. `alarm`/`reminder`, 6 languages). Since we're English-only, TOPv2 already gives strictly more English data in the same format — MTOP is redundant for us; only worth revisiting if multilingual becomes a goal.

## 3. NLU-Evaluation-Data (Liu et al., "HWU" home-domain corpus)

- **Link:** [github.com/xliuhw/NLU-Evaluation-Data](https://github.com/xliuhw/NLU-Evaluation-Data) · paper: [Liu et al. 2019, arxiv.org/abs/1903.05566](https://arxiv.org/abs/1903.05566) · raw file: `https://raw.githubusercontent.com/xliuhw/NLU-Evaluation-Data/master/AnnotatedData/NLU-Data-Home-Domain-Annotated-All.csv` (downloaded directly, no auth).
- **License:** CC-BY 4.0 (stated in the repo README).
- **Size:** 25,716 rows, 18 scenarios, 68 intents (confirmed by direct count on the downloaded CSV).
- **Domains relevant to us** (verified counts): `calendar` **2,986** (`set` 1,451, `query` 1,002, `remove` 533), `alarm` 623, `datetime` 723, `lists` 994, plus `email` 1,764, `general` 6,102, `qa` 2,370 for broader assistant-register wording.
- **Annotation shape:** semicolon-delimited CSV — `userid;answerid;scenario;intent;status;answer_annotation;notes;suggested_entities;answer_normalised;answer;question`. `answer_annotation` carries the same `[slot : value]` bracket style MASSIVE uses (unsurprising — MASSIVE's calendar/alarm rows are localizations of this same prompt pool, see #1). Real rows:
  ```
  calendar;query;is the [event_name : meeting] scheduled for [date : tomorrow]
  calendar;set;remind my friend to get the assignment tomorrow  (slots: date, location, time)
  calendar;set;set an alarm for [time : two hours from now]
  ```
- **Spoken-style:** yes — crowdworkers answered prompts like *"Write what you would tell your PDA in the following scenario: to set an alarm"*, so it's free-form natural phrasing, not templated, though it inherits some prompt-echo artifacts (a few `calendar` rows are actually about news/weather because the elicitation prompt was reused across intents — worth a light filter pass).
- **Mapping sketch:** same as MASSIVE (#1) — `scenario`+`intent` → our `action`, bracket spans → `slots`. Because this is the *source* pool (bigger, messier, includes some mis-scoped rows MASSIVE's QA process would have caught), treat it as a bigger, noisier well to draw wording variety from rather than a first choice — pull rows MASSIVE doesn't cover, dedupe against MASSIVE by normalized text.
- **Adaptation effort:** **S**, same regex-based bracket-slot extraction as MASSIVE, plus a light `status`/`notes` != "IRR" quality filter (some rows are marked irrelevant/error in `status`).
- **What it buys us:** same failure family as MASSIVE (#2, #3) plus roughly +2,900 calendar rows and +6,600 general/qa/email rows of assistant-register wording variety that MASSIVE's en-US split doesn't carry (MASSIVE only kept a subset when relabeling).
- Note on **HWU64**: later papers repackage this same corpus as bare `utterance, intent_label` pairs with slots stripped (e.g. [huggingface.co/datasets/DeepPavlov/hwu64](https://huggingface.co/datasets/DeepPavlov/hwu64), 8,954 train / 1,076 test rows, verified — confirmed no slot annotations, e.g. `{"utterance": "what alarms do i have set right now", "label": 0}`). Since it's a strict subset of this richer, slot-annotated original with the slots thrown away, **use the CSV above instead of "HWU64" releases** — dead-end-adjacent, not a separate opportunity.

## 4. MixSNIPS (clean) — construction *recipe*, not domain content

- **Link:** [github.com/LooperXX/AGIF](https://github.com/LooperXX/AGIF) (paper: AGIF, EMNLP Findings 2020) — data at `data/MixSNIPS_clean/` and `data/MixATIS_clean/`; raw file verified: `https://raw.githubusercontent.com/LooperXX/AGIF/master/data/MixSNIPS_clean/train.txt`.
- **License:** repo code is GPL-2.0; underlying content is derived from SNIPS, which is **CC0** (verified — see #7 below), so the data itself is effectively unencumbered even though the repo wrapping it is GPL.
- **Size:** MixSNIPS_clean: [39,776 / 2,198 / 2,199] train/wren/test. MixATIS_clean: [13,162 / 759 / 828].
- **Domains:** SNIPS's 7 intents (`PlayMusic`, `RateBook`, `SearchCreativeWork`, `AddToPlaylist`, `BookRestaurant`, `GetWeather`, `SearchScreeningEvent`) — **not calendar**, but see below for why it still matters.
- **Annotation shape:** CoNLL-style, one token per line with `B-`/`I-` slot tags, blank line between utterances, multi-intent label on its own line as `Intent1#Intent2`. Real verified sample:
  ```
  rate O
  rajinikanth: B-object_name
  the I-object_name
  definitive I-object_name
  biography I-object_name
  one B-rating_value
  out O
  of O
  6 B-best_rating
  stars B-rating_unit
  and O
  then O
  what O
  s O
  the O
  movie B-object_type
  schedule I-object_type
  for O
  b&b B-location_name
  theatres I-location_name
  RateBook#SearchScreeningEvent
  ```
  i.e. **two single-intent SNIPS sentences literally concatenated with "and" / "and then", multi-label joined by `#`.**
- **Why this matters despite the domain mismatch:** this is exactly the compositional-utterance authoring pattern our priority #1 (multi-intent) needs, laid out mechanically: take two independently-labeled single-intent rows from our own domain pool, join them with a connective ("and", "and then", "also", "after that"), concatenate their slot spans, and label the pair with both actions. **MixSNIPS is a template to copy, not text to import.** The construction method (not the SNIPS content) is the deliverable here — cheapest way to manufacture a large compound-utterance training/eval set on top of any of the single-intent sources above (MASSIVE, TOPv2's flat rows, xliuhw), including controlling exactly what `events`/`tasks`/`atomic` counts should be since we're the ones doing the concatenation.
- **Adaptation effort:** **S** to write our own version of this generator (a join-and-relabel script over our existing single-intent rows); **not applicable** to import MixSNIPS content directly (wrong domain).
- **What it buys us:** priority #1 (compositional/multi-intent) at low cost, and lets us control label balance precisely since we generate the pairs ourselves.
- **MixATIS** is the same recipe over ATIS instead of SNIPS — skipped as a content source (see Dead ends: ATIS/MixATIS) but doesn't change the recipe conclusion above.

## 5. CLINC150 (oos-eval)

- **Link:** [github.com/clinc/oos-eval](https://github.com/clinc/oos-eval) (paper: An Evaluation Dataset for Intent Classification and Out-of-Scope Prediction, EMNLP 2019) · raw file: `https://raw.githubusercontent.com/clinc/oos-eval/master/data/data_full.json` (downloaded directly).
- **License:** **CC-BY 3.0** (LICENSE file in repo, verified).
- **Size:** 150 in-scope intents × (100 train + 20 wren + 30 test) = 22,500 in-scope rows, plus 1,200 out-of-scope rows (100 train / 100 wren / 1,000 test).
- **Domains relevant to us** (found by scanning all 150 intent names, verified against real examples): `alarm`, `calendar`, `calendar_update`, `date`, `expiration_date`, `meeting_schedule`, `reminder`, `reminder_update`, `schedule_maintenance`, `schedule_meeting`, `shopping_list_update`, `time`, `timer`, `timezone`, `todo_list`, `todo_list_update` — **16 calendar/reminder/todo-shaped intents**, each with 150 examples (100/20/30 split) = **2,400 rows**. Verified examples:
  ```
  calendar_update: "add my dentist appointment to the calendar", "add a vet appointment for 5 pm on saturday"
  reminder_update: "remind me to call my mother saturday morning", "make a reminder for me to do my resume"
  todo_list_update: "i need to add the chore of vacuuming to my task list", "take doing the dishes off my todo list"
  schedule_meeting: "i want to know if there is meeting room available at 8"
  ```
- **Annotation shape:** flat `[utterance, intent_label]` pairs — **no slots at all**, and the explicit strength of this set is the **out-of-scope (OOS)** class: 1,200 utterances that are plausible-sounding but belong to none of the 150 intents.
- **Spoken-style:** yes, natural phrasing via crowdsourcing.
- **Mapping sketch:** intent name → our `action` almost by inspection (`calendar_update`→`update_event`, `reminder_update`→`update_todo`/`create_todo` depending on phrasing, `todo_list_update`→mixed create/delete todo, `todo_list`/`reminder`(bare) → `query`). No slots to carry over — `title`/`date_phrase`/etc. would need to be pulled from the raw text by our own extractor, so this set is intent-classification signal only, not a slot-training source.
- **Adaptation effort:** **S** for the label mapping; **not usable** for slot supervision (would need re-annotation).
- **What it buys us:** the OOS class is the one thing none of the datasets above have — direct material for the parse-path / kind-decision problem (teaching the classifier what's *not* one of our actions at all, e.g. `cook_time`, `timezone`, `expiration_date` reading like calendar but aren't), which is a distinct failure family from compounds. Good regression/eval material for "does this even belong to our action set."

---

## Other datasets assessed (not top 5, but verified — useful context or partial fits)

### SNIPS / nlu-benchmark (raw, single-intent)
[github.com/sonos/nlu-benchmark](https://github.com/sonos/nlu-benchmark), 2017-06-custom-intent-engines dir. **License: CC0** (LICENSE file verified — full public domain dedication, the most permissive of anything assessed here). ~2,000 crowdsourced queries/intent across 7 intents (`AddToPlaylist`, `GetWeather`, etc.), JSON chunked-span format:
```json
{"data": [{"text": "Add another "}, {"text": "song", "entity": "music_item"}, {"text": " to the "}, {"text": "Cita Romántica", "entity": "playlist"}, {"text": " playlist. "}]}
```
No calendar-shaped intents (closest is `GetWeather`'s datetime references). Given MixSNIPS (#4) already extracts the useful part (the compound-construction recipe) from this same source, raw SNIPS mainly adds generic-assistant register wording variety and its CC0 license makes it a safe "no-risk" filler if volume is ever needed. Adaptation effort: S (convert chunked spans → bracket spans), but low priority given the domain mismatch. Not top 5 only because it duplicates what MixSNIPS already gives us in more useful (multi-intent) form.

### Schema-Guided Dialogue (SGD)
[github.com/google-research-datasets/dstc8-schema-guided-dialogue](https://github.com/google-research-datasets/dstc8-schema-guided-dialogue) (paper: [arxiv.org/abs/1909.05855](https://arxiv.org/abs/1909.05855)). **License: CC-BY-SA 4.0.** Downloaded `train/schema.json` and one real dialogue file (`train/dialogues_001.json`, 128 dialogues) to verify structure. Confirmed **`Calendar_1`** service exists with intents `GetEvents`, `GetAvailableTime`, `AddEvent` and slots `event_date`, `event_time`, `event_location`, `event_name`, `available_start_time`, `available_end_time` — a near-exact match to our `title`/`date_phrase`/`time_phrase` slots. Also `Events_1`/`Events_2` (ticket-buying, not personal calendar) and `Alarm_1` (dev/test only, per the paper's domain-holdout design). Per the paper's appendix, Calendar appears in roughly 1,600 of the ~22.8k total dialogues (sources vary slightly, 773–1,602 depending on which table/split is being read — worth re-verifying against the paper directly before relying on an exact count) and Alarm in ~324–367, confined to dev/test to test zero-shot domain transfer.

**The catch:** SGD is **multi-turn dialogue**, not single-shot commands — a real turn from the sample file:
```
USER: I am feeling hungry so I would like to find a place to eat.
  → frame: INFORM_INTENT (intent=FindRestaurants), no slots yet
SYSTEM: Do you have a specific which you want the eating place to be located at?
USER: I would like for it to be in San Jose.
  → frame: INFORM (city=San Jose), slot span verified in the utterance
```
A usable single-shot "book an event" utterance is scattered across 2-4 turns (intent stated in one turn, slots filled across the next several), so getting one training row out of a `Calendar_1` dialogue means stitching turns together and deciding which slot-fill turns belong to which intent-declaration turn — real engineering, not a mapping script. **Adaptation effort: L.** Worth a second look if we ever want dialogue-level (multi-turn) training data, but not a fit for our current single-utterance schema without that stitching work.

### NLU++ (PolyAI)
[github.com/PolyAI-LDN/task-specific-datasets](https://github.com/PolyAI-LDN/task-specific-datasets), `nlupp/` dir. **License: CC-BY-4.0** (repo-level LICENSE, verified). 3,080 examples across `banking` (2,071) and `hotels` (1,009) domains, 62 intents, 17 slots — **genuinely multi-label** (not concatenation-constructed like MixSNIPS): a single utterance like *"Why can't I amend my booking on tuesday?"* carries three simultaneous intent labels (`why`, `change`, `booking`). Annotation shape:
```json
{"text": "How much did I spend in total until May on amazon prime?",
 "intents": ["how_much", "transfer_payment_deposit"],
 "slots": {"date_to": {"text": "May", "span": [36, 39], "value": {...}}, "company_name": {...}}}
```
Domain is banking/hotels, not calendar — no direct content use. Filed alongside MixSNIPS as a second **recipe** reference: this is what genuine multi-label (as opposed to two-sentences-glued-together) annotation looks like, useful if we ever want a row to carry `["create_event", "create_todo"]` as a real label set rather than inferring compound-ness from `events`+`tasks` counts. Adaptation effort: N/A for content, S to imitate the label shape.

### Facebook Multilingual Task-Oriented Dataset (Schuster et al. 2019)
Paper: [arxiv.org/abs/1810.13327](https://arxiv.org/abs/1810.13327). Direct download verified: `https://download.pytorch.org/data/multilingual_task_oriented_dialog_slotfilling.zip` (8.9MB, no auth). English portion: 30,521 train / 4,181 dev / 8,621 test = ~43.3k rows across **`alarm`** (6 intents: `set_alarm` 4,816, `cancel_alarm` 2,069, `show_alarms` 1,142, `modify_alarm` 439, `snooze_alarm` 432, `time_left_on_alarm` 384), **`reminder`** (`set_reminder` 4,743, `cancel_reminder` 1,151, `show_reminders` 1,006), and `weather` (14,507, off-domain). Annotation is **flat** (one intent per utterance) with character-span slots, e.g.:
```
weather/find	12:26:weather/noun,31:44:location	tell me the weather report for half moon bay	en_XX	{tokenization JSON...}
```
This predates TOPv2 (#2) and looks like an ancestor/sibling corpus covering the same two domains with ~7x less data and a simpler, non-nested annotation (single `intent<TAB>slots<TAB>text` row, no bracket-tree parsing needed). Given TOPv2 already covers `alarm`+`reminder` with far more volume, this is mainly useful as a **smaller, easier-to-parse alternative** if the nested-tree walker for TOPv2's compositional rows turns out to be more effort than it's worth, or as a quick sanity/held-out set drawn from a distinct annotation pipeline. Adaptation effort: S. Not top 5 only because TOPv2 dominates it on volume and domain coverage.

### MTOP
See note under TOPv2 (#2) — multilingual sibling of the same schema, redundant for an English-only project.

---

## Dead ends

- **MultiWOZ** — [github.com/budzianowski/multiwoz](https://github.com/budzianowski/multiwoz). Confirmed via multiple sources: domains are `restaurant`, `hotel`, `attraction`, `taxi`, `train`, `bus`, `hospital`, `police` — **no calendar/reminder/todo domain exists in any MultiWOZ version** (2.0 through 2.2). Booking-adjacent (hotel/restaurant/train booking) but not personal-calendar-shaped, and still multi-turn dialogue like SGD. Not pursued further.
- **Taskmaster (TM-1/2/3)** — [github.com/google-research-datasets/Taskmaster](https://github.com/google-research-datasets/Taskmaster). CC-BY-4.0, 55k+ dialogues, well-annotated — but domains are pizza/coffee/auto-repair/ride-service/movie-tickets/restaurant (TM-1), restaurants/food-ordering/movies/hotels/flights/music/sports (TM-2), movie ticketing (TM-3). **Confirmed no calendar/appointment/reminder domain in any of the three releases.** Dead end for our purposes despite being a large, high-quality, freely-downloadable corpus.
- **Almond / ThingTalk / Genie-toolkit** — [github.com/stanford-oval/genie-toolkit](https://github.com/stanford-oval/genie-toolkit), [github.com/stanford-oval/thingtalk](https://github.com/stanford-oval/thingtalk). This is a **toolchain for synthesizing** a dataset from a skill definition (Thingpedia `.tt` manifests + Genie templates + optional crowdsourced paraphrasing), not a ready-made downloadable corpus — there's no pre-built "calendar skill dataset" sitting in a repo to curl. Getting data out of this would mean writing a ThingTalk calendar-skill manifest and running their generation pipeline ourselves, which is a different (and much larger) project than adapting an existing dataset. Programmatic ground-truth (ThingTalk programs) is an interesting property in the abstract, but not "easy to tune to our means" as instructed — flagged as a dead end for now, not because the idea is bad but because there's no shortcut here.
- **Chirpy Cardinal** — open-domain social chit-chat system (Alexa Prize), not a structured intent/slot corpus at all; its "reminders" handling (if any) is scaffolded dialogue logic, not training data. No public structured dataset to extract. Dead end.
- **ATIS / MixATIS** — original ATIS is LDC-gated (`catalog.ldc.upenn.edu/LDC94S19`, `LDC95S26`), i.e. requires LDC membership/payment to obtain officially. A pre-processed version circulates freely on GitHub (used inside the AGIF repo's `MixATIS_clean`, and separately at `github.com/howl-anderson/ATIS_dataset`) with no LDC login required to `curl` it, but the licensing status of that free-circulating copy relative to the original LDC terms is unclear — per the brief's instruction to flag signup/LDC-payment items as low priority, and given the domain (airline booking) doesn't fit us anyway, **not pursued as a content source.** (The MixATIS *construction recipe* is identical to MixSNIPS's, already captured under #4 using the unambiguously CC0 SNIPS lineage instead.)
- **HWU64 (DeepPavlov re-release)** — see note under #3; a slot-stripped subset of the xliuhw corpus we already have with slots intact. No separate value.

---

## Ranked TOP 5 — adoption plans

**1. TOPv2** (`https://dl.fbaipublicfiles.com/topv2/TOPv2_Dataset.zip`, CC-BY-SA 4.0). Adopt first: pull the `alarm`, `reminder`, `event`, `timer` TSVs (~87k rows), write a small recursive parser for the `[IN:... [SL:... ]]` bracket tree (most rows are 1-2 levels deep, verified by inspection), and split output into two buckets — flat rows map straight to one `expect` object each; the ~10-15% of rows with a nested `IN:` node inside another `IN:` node become our real (not synthetic) multi-intent/`mixed` examples, which is the single scarcest row type in our current eval set. Expect this to move the compounds/multi-intent failure family measurably since these are naturally-occurring compound asks, not generated ones.

**2. MASSIVE en-US** (`https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz`, CC-BY-4.0). Adopt second, in parallel: the `calendar`/`alarm`/`lists`/`datetime` scenarios (~4.3k rows) map to our schema almost by find-and-replace (scenario+intent → action, bracket span regex → slots), and being professionally quality-scored means less manual cleanup than the rawer sources. Best per-hour yield of any candidate here. Use it to bulk up the `create_event`/`delete_event`/`query`/`create_todo`/`delete_todo` single-intent baseline before layering compounds on top.

**3. MixSNIPS-style compound generator (recipe only, not content)**. Once (1) and (2) give us a healthy pool of labeled single-intent rows in our own domain, write our own ~50-line version of AGIF's construction script: sample two rows, join with a connective ("and", "and then", "also", "after that", "oh and"), concatenate slots, set `events`/`tasks`/`atomic` from the two source rows' own labels (which we control exactly, unlike inferring it after the fact). This is the cheapest lever for volume in the compounds family and lets us target specific pairings we know we're weak on (e.g. create_event + create_todo, or query + delete).

**4. NLU-Evaluation-Data / "HWU" corpus** (`https://raw.githubusercontent.com/xliuhw/NLU-Evaluation-Data/master/AnnotatedData/NLU-Data-Home-Domain-Annotated-All.csv`, CC-BY-4.0). Adopt as a top-up source once (1)+(2) are in and we can see what's still thin: draw the ~2,900 calendar rows and the general/email/qa scenarios for wording variety, deduping against MASSIVE by normalized text (the two datasets share a prompt pool, confirmed by identical verbatim rows). Lower priority than 1-3 only because its content mostly overlaps MASSIVE's and needs an extra quality filter pass MASSIVE has already done for us.

**5. CLINC150** (`https://raw.githubusercontent.com/clinc/oos-eval/master/data/data_full.json`, CC-BY 3.0). Adopt last, for a different purpose than 1-4: not for slot training (no slots) but as an **eval/regression set for the kind-decision and out-of-scope problem** — the 16 calendar/reminder/todo-shaped intents (2,400 rows) plus the 1,200 explicit out-of-scope rows are a ready-made stress test for "does this utterance belong to our action set at all, and which of the near-miss kinds (timer vs. alarm vs. calendar vs. todo vs. plain time-lookup) is it." Cheapest way to add negative/near-miss coverage we don't get from any of the other four.
