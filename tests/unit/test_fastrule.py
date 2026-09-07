"""FastRule — the selective classifier's gates, unit-level (no LLM).

conftest.py has already pointed every store at scratch before this import.
"""
import pytest

from assistant.engine.fastrule import FastRule


@pytest.fixture
def fastrule(registry_with_real_actions):
    # the autouse isolated_registry empties the action registry; intents are
    # built from it, so FastRule needs the real actions restored
    return FastRule(0.80)

def test_f4a_polite_imperative_is_not_a_question(fastrule):
    """"Can you create X" wants X created — the interrogative gate must not
    read the courtesy as a question. Real questions still abstain."""
    r = fastrule.run("Can you create a new list in my podcast?")
    assert r.committed and r.intents[0][0] == "create_todo"
    r = fastrule.run("Do I need to be reminded of any meetings on Monday?")
    assert not r.committed and r.reason == "interrogative-create"


def test_f4b_marking_a_date_never_completes_a_task(fastrule):
    """"mark 13 october as my birthday" marks a DAY; it fast-committed
    complete_todo at 0.95 (would tick off an unrelated task). Now it must
    never commit a complete_* — abstaining to deep is the accepted outcome."""
    r = fastrule.run("mark 13 october of this year as my birthday")
    assert not any(n.startswith("complete_") for n, _ in r.intents)
    # F15 improved the outcome: it now COMMITS this as an all-day event
    # (a dated create with no spoken clock time). The rule being pinned is
    # "never tick a task off", not the old inability to handle it at all.
    if r.committed:
        assert r.intents[0][0] == "create_event"
    r = fastrule.run("mark groceries as done")
    assert r.committed and r.intents[0][0] == "complete_todo"


def test_f5_plain_and_clause_coordination_abstains(fastrule):
    """F5: a plain "and" joining two asks (no cue words) must defer — the
    regex gate only knows announced joiners. Names and lists never trip it."""
    r = fastrule.run("book the gym for tomorrow at 6 and remind me to buy milk")
    assert not r.committed and r.reason == "clause-coordination"
    r = fastrule.run("schedule meeting with Tal and Sam tomorrow at 3pm")
    assert r.reason != "clause-coordination"  # NP-coordination: one event,
    # two guests - whatever else the parser decides, the F5 gate stays out


def test_f7_rename_never_commits_a_create(fastrule):
    """"rename flu shot to sales call" fast-committed create_todo at 0.95 —
    and FastRule can't know which store holds the old title anyway. Renames
    abstain; deep's matcher searches both stores."""
    r = fastrule.run("rename flu shot to sales call")
    assert not r.committed and r.reason == "rename-misroute"


def test_f7_priority_setting_is_an_update(fastrule):
    """"set X as high priority" read as create at 1.00 — it's a structured
    update: match_title + priority, phrase-delimited."""
    r = fastrule.run("set pick up the dry cleaning as high priority")
    assert r.committed and r.intents[0][0] == "update_todo"
    it = r.intents[0][1]
    assert getattr(it, "new_priority", None) == "high"
    assert "dry cleaning" in (getattr(it, "match_title", "") or "")
    # the rename extractor must not read "as high priority" as a new name
    assert not getattr(it, "new_title", None)


def test_f10_mutation_phrases_delimit_multiword_titles(fastrule):
    """Noun-chunking drops multi-word titles in mutations; the phrase itself
    delimits them. Generic targets still abstain (the veto judges captures)."""
    assert fastrule.run("delete wedding rehearsal from my calendar").committed
    assert fastrule.run("reschedule haircut to this weekend").committed
    assert fastrule.run("mark walk the dog complete").intents[0][0] == "complete_todo"
    assert not fastrule.run("delete this event").committed


def test_f11_model_tier_fires_only_where_rules_found_nothing(fastrule):
    """Q10: verbless/unseen phrasings route via the model tier at the
    inference-billed confidence; rule-covered commands are byte-identical."""
    # verbless remind-speak + occasion + date: rules find no verb to route,
    # both model margins clear the SAFE floors (2.5/1.5 — the dual-gate
    # tightening), so the model tier composes new×event
    r = fastrule.run("don't forget the parent teacher conference wednesday 5pm")
    assert r.committed and r.intents[0][0] == "create_event"
    # model-routed commits are billed as inference (the ×0.85 channel) —
    # never at rule-tier confidence. (Margins shift with refits; behavior,
    # not specific margins, is what this test pins.)
    r2 = fastrule.run("gym session friday 6pm")
    if r2.committed:
        assert r2.intents[0][0] == "create_event" and r2.confidence <= 0.9
    r = fastrule.run("book gym tomorrow at 7am")   # rules tier, unchanged
    assert r.committed and r.confidence > 0.9


def test_f16_lead_time_no_longer_eats_the_title(fastrule):
    """The lead-time strip lived only in decompose (a deep-track stage), so
    FastRule failed 100% of lead-time rows: "remind me 5 minutes before
    about X" routed a titleless todo. Shared now (intent/lead_time.py), and
    the pinned convention applies — a clock-timed reminder is an EVENT."""
    r = fastrule.run("remind me 5 minutes before about product demo tonight at 7pm")
    assert r.committed and r.intents[0][0] == "create_event"
    assert fastrule.run("remind me to buy milk").intents[0][0] == "create_todo"
    # "remind me in 5 minutes" IS the request, not a lead time on something else
    assert not fastrule.run("remind me in 5 minutes").committed


def test_f16_marking_a_day_is_a_calendar_create(fastrule):
    """"mark/label ‹when› … as ‹occasion›" was 36% of committed-but-wrong
    atomic rows (routed complete_todo / update_event / query_schedule).
    Completions must be unaffected."""
    assert fastrule.run("mark march 5th on my calendar as the tax deadline"
                        ).intents[0][0] == "create_event"
    assert fastrule.run("mark groceries as done").intents[0][0] == "complete_todo"


def test_f16_sentence_initial_calendar_verb_wins(fastrule):
    """"book sales call…" routed create_todo because the NOUN "call" was read
    as the verb. An imperative opening with book/schedule is a calendar
    create; reschedule stays an update (regression caught in F16)."""
    assert fastrule.run("book sales call this friday all day"
                        ).intents[0][0] == "create_event"
    assert fastrule.run("reschedule haircut to this weekend"
                        ).intents[0][0] == "update_event"


def test_f17_recurrence_is_a_slot_not_n_items(fastrule):
    """Gil's architecture call: a recurring command is ONE atomic item that
    repeats — db.create_event expands the series. FastRule never filled the
    slot, so "every monday" produced no cadence AND no date and deferred.
    The anchor is the soonest named day (the project's weekly-series rule)."""
    r = fastrule.run("book haircut every monday at 9am")
    assert r.committed and len(r.intents) == 1          # ONE item, not N
    intent = r.intents[0][1]
    assert intent.recurrence == "weekly"
    import datetime
    assert datetime.date.fromisoformat(intent.date).weekday() == 0   # a Monday
    # a cadence we do not support is ROUNDED, never invented
    assert fastrule.run("book yoga every other tuesday at 6pm"
                        ).intents[0][1].recurrence == "weekly"
    # non-recurring commands are untouched
    assert fastrule.run("book gym tomorrow at 7am").intents[0][1].recurrence is None
