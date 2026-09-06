"""Consent-based tag discovery (Gil, 2026-09-05).

The registry may GROW from usage, but only by asking — and asking politely:
MIN_EVIDENCE distinct uncovered tasks, one ask per cooldown window (charged
on hand-out, not on answer), refusals remembered forever.
"""
from __future__ import annotations

import pytest

import assistant.actions.todo.tag_discovery as disc
import assistant.api.server as server


@pytest.fixture
def db():
    from assistant.db import get_db
    d = get_db()
    with d._conn() as conn:
        for table in ("todos", "tag_suggestion_state"):
            try:
                conn.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        conn.execute("DELETE FROM todo_tags WHERE builtin = 0")
    return d


def _seed(db, titles):
    for t in titles:
        db.create_todo(title=t, list_name="today", priority="none",
                       due_date="", notes="", tags=[])


# a theme the existing keyword classifier genuinely does not know — "pharmacy"
# turned out to be covered by Errands already, which is itself the point of the
# exclusion rule (see test_tasks_an_existing_class_covers_do_not_count).
THEME = ["mist the terrarium", "terrarium soil order", "buy terrarium plants",
         "clean terrarium glass", "terrarium light timer"]


def test_a_shared_theme_with_enough_evidence_is_proposed(db):
    _seed(db, THEME)
    c = disc.candidate()
    assert c and c["name"] == "Terrarium" and c["evidence"] == 5
    assert len(c["samples"]) == 3


def test_below_the_evidence_bar_stays_silent(db):
    _seed(db, THEME[:4])
    assert disc.candidate() is None


def test_tasks_an_existing_class_covers_do_not_count(db):
    # "milk"/"eggs" would be filed under Groceries by the classifier already —
    # frequency there is not evidence for a new class.
    _seed(db, ["buy milk", "buy milk again", "milk for shabbat",
               "more milk", "milk and stuff"])
    c = disc.candidate()
    assert c is None or c["name"].lower() != "milk"


def test_a_refusal_is_forever_and_asking_costs_the_cooldown(db):
    _seed(db, THEME)
    c = disc.candidate()
    assert c["name"] == "Terrarium"
    disc.record_ask()
    disc.answer("Terrarium", accept=False)
    assert disc.candidate() is None            # cooldown active
    # even with the cooldown expired, a refused name never returns
    import datetime
    with db._conn() as conn:
        old = (datetime.datetime.now() - datetime.timedelta(days=30)).isoformat()
        conn.execute("UPDATE tag_suggestion_state SET ts = ? WHERE name = ?",
                     (old, disc._LAST_ASKED))
    assert disc.candidate() is None


def test_yes_adds_the_class_to_the_registry(db):
    _seed(db, THEME)
    created = disc.answer("Terrarium", accept=True)
    assert created and created["name"] == "Terrarium"
    assert "Terrarium" in [r["name"] for r in db.get_tags()]


def test_the_endpoints_hand_out_and_record(db):
    _seed(db, THEME)
    app = server.create_app()
    app.config.update(TESTING=True)
    client = app.test_client()
    got = client.get("/tags/suggestion").get_json()
    assert got.get("name") == "Terrarium"
    # handing out charged the cooldown: an immediate second ask is empty
    assert client.get("/tags/suggestion").get_json() == {}
    resp = client.post("/tags/suggestion/answer",
                       json={"name": "Terrarium", "accept": True}).get_json()
    assert resp["accepted"] and resp["tag"]["name"] == "Terrarium"


def test_history_review_reverse_and_hide(db):
    _seed(db, THEME)
    disc.answer("Terrarium", accept=False)
    h = disc.history()
    assert h and h[0]["name"] == "Terrarium" and h[0]["status"] == "refused"
    # reverse the refusal → the class joins the registry after all
    disc.change_answer("Terrarium", accept=True)
    assert "Terrarium" in [r["name"] for r in db.get_tags()]
    # reverse the acceptance → the class leaves the registry again
    disc.change_answer("Terrarium", accept=False)
    assert "Terrarium" not in [r["name"] for r in db.get_tags()]
    # hide keeps it in the record, flagged
    disc.set_hidden("Terrarium", True)
    h = disc.history()
    assert h[0]["hidden"] is True and h[0]["status"] == "refused"
