"""Learn NEW tag classes from the user's own history — with consent.

Gil's design (2026-09-05): the tag registry is a finite class set, but it
should be able to GROW from real usage. When enough untagged tasks share a
theme, the app may ask — once, in a small popup, while the user is actively
using it — "add 'Pharmacy' as a tag?" yes/no.

Politeness is structural, not best-effort:

  • a candidate needs MIN_EVIDENCE distinct untagged tasks behind it, none of
    which the existing classifier could already file;
  • at most one ask per COOLDOWN_DAYS — and fetching a suggestion COSTS the
    cooldown whether or not it is answered, so a glitchy client can never nag;
  • a refused name is recorded and never proposed again;
  • the server never pushes: clients pull `GET /tags/suggestion` only when the
    app is foregrounded, which is what "actively using it" means here.

State lives in a small table inside the calendar DB (so tests inherit the
scratch isolation automatically).
"""
from __future__ import annotations

import datetime
import json
import re
from collections import Counter, defaultdict

MIN_EVIDENCE = 5
COOLDOWN_DAYS = 7

_LAST_ASKED = "__last_asked__"

_STOP = frozenset(
    "the a an my your for with and then also this that from about need to buy "
    "get pick up add put new list today tomorrow week next call text send make "
    "some more please remember don't dont have has was were will would".split())

_STATE_SQL = """CREATE TABLE IF NOT EXISTS tag_suggestion_state (
    name TEXT PRIMARY KEY,
    status TEXT NOT NULL,          -- refused | accepted | (or the ask stamp)
    ts TEXT NOT NULL,
    hidden INTEGER NOT NULL DEFAULT 0
)"""


def _ensure_hidden(conn) -> None:
    try:
        conn.execute("ALTER TABLE tag_suggestion_state ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass


def _words(title: str) -> "set[str]":
    return {w for w in re.findall(r"[a-z][a-z']{3,}", (title or "").lower())
            if w not in _STOP}


def _ensure(conn) -> None:
    conn.execute(_STATE_SQL)
    _ensure_hidden(conn)


def candidate() -> "dict | None":
    """The one suggestion worth asking about right now, or None.

    None whenever: the cooldown hasn't elapsed, no theme reaches
    MIN_EVIDENCE, or every qualifying name was already decided."""
    from assistant.actions.todo.tagging import resolve_tags, suggest_tags
    from assistant.db import get_db

    db = get_db()
    with db._conn() as conn:
        _ensure(conn)
        row = conn.execute("SELECT ts FROM tag_suggestion_state WHERE name = ?",
                           (_LAST_ASKED,)).fetchone()
        if row:
            last = datetime.datetime.fromisoformat(row["ts"])
            if datetime.datetime.now() - last < datetime.timedelta(days=COOLDOWN_DAYS):
                return None
        decided = {r["name"].lower() for r in conn.execute(
            "SELECT name FROM tag_suggestion_state WHERE name != ?", (_LAST_ASKED,))}
        todos = conn.execute("SELECT title, tags FROM todos").fetchall()

    palette = [r["name"] for r in db.get_tags()]
    counts: Counter = Counter()
    samples: dict = defaultdict(set)
    for r in todos:
        try:
            tags = json.loads(r["tags"] or "[]")
        except json.JSONDecodeError:
            tags = []
        title = r["title"] or ""
        if tags:
            continue                                # already classified
        if suggest_tags(title, palette):
            continue                                # an existing class covers it
        for w in _words(title):
            samples[w].add(title.strip())
    for w, titles in samples.items():
        counts[w] = len(titles)                     # distinct tasks, not mentions

    for word, n in counts.most_common():
        if n < MIN_EVIDENCE:
            break
        if word in decided:
            continue
        name = word.capitalize()
        if resolve_tags([name], palette):
            continue                                # near-miss of an existing class
        return {"name": name, "evidence": n,
                "samples": sorted(samples[word])[:3]}
    return None


def record_ask() -> None:
    """Stamp the cooldown — called when a suggestion is HANDED OUT, so even an
    unanswered popup counts as this week's one ask."""
    from assistant.db import get_db
    with get_db()._conn() as conn:
        _ensure(conn)
        conn.execute(
            "INSERT INTO tag_suggestion_state (name, status, ts) VALUES (?, 'asked', ?) "
            "ON CONFLICT(name) DO UPDATE SET ts = excluded.ts",
            (_LAST_ASKED, datetime.datetime.now().isoformat()))


def answer(name: str, accept: bool) -> "dict | None":
    """Record the verdict. Yes → the class joins the registry (and is returned);
    no → the name is never proposed again."""
    from assistant.db import get_db
    db = get_db()
    with db._conn() as conn:
        _ensure(conn)
        conn.execute(
            "INSERT INTO tag_suggestion_state (name, status, ts) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET status = excluded.status, ts = excluded.ts",
            (name.strip().lower(), "accepted" if accept else "refused",
             datetime.datetime.now().isoformat()))
    if accept:
        return db.create_tag(name.strip())
    return None


def change_answer(name: str, accept: bool) -> "dict | None":
    """Reverse or change a past verdict from the history view (Gil,
    2026-09-05): un-refusing creates the class after all; un-accepting removes
    it from the registry again (delete_tag also strips it from todos — the
    same behaviour as deleting it by hand)."""
    from assistant.db import get_db
    db = get_db()
    key = name.strip().lower()
    with db._conn() as conn:
        _ensure(conn)
        row = conn.execute("SELECT status FROM tag_suggestion_state WHERE name = ?",
                           (key,)).fetchone()
    was_accepted = bool(row and row["status"] == "accepted")
    if was_accepted and not accept:
        db.delete_tag(name.strip().capitalize())
        db.delete_tag(name.strip())
    return answer(name, accept)


def set_hidden(name: str, hidden: bool) -> None:
    """Hide an entry from the visible history — it stays in the record."""
    from assistant.db import get_db
    with get_db()._conn() as conn:
        _ensure(conn)
        conn.execute("UPDATE tag_suggestion_state SET hidden = ? WHERE name = ?",
                     (1 if hidden else 0, name.strip().lower()))


def history() -> list:
    """Every past suggestion and its verdict, newest first — the reviewable
    record behind the app's history view. Hidden entries are included with
    their flag; the client decides how to fold them away."""
    from assistant.db import get_db
    with get_db()._conn() as conn:
        _ensure(conn)
        rows = conn.execute(
            "SELECT name, status, ts, hidden FROM tag_suggestion_state "
            "WHERE name != ? ORDER BY ts DESC", (_LAST_ASKED,)).fetchall()
    return [{"name": r["name"].capitalize(), "status": r["status"],
             "ts": r["ts"], "hidden": bool(r["hidden"])} for r in rows]
