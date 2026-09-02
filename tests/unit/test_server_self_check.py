"""The self-check that now runs for both surfaces.

These guards used to live only on the Mac's Pipeline._background_verify. The
Mac stopped executing anything when the GUI became a client of the API, so the
server's verify is the only one left — and it is the one that can undo a
record. The guards travelled with it; so did their tests.

The one that matters most is the false alarm. Measured against real commands,
the verifier wanted to redo a correct complete_todo ("mark the report as
finished") as update_todo. Acting on that undoes work the user asked for. So
the verdict decides only *whether* to change something; the parser decides
*what to*, and if the parser agrees with what already ran the verdict is
thrown away.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from assistant.actions.calendar.intent import CalendarIntent
from assistant.actions.todo.intent import CreateTodoIntent
import assistant.api.server as server


@pytest.fixture
def fake_db(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr("assistant.db.get_db", lambda: db)
    return db


@pytest.fixture(autouse=True)
def apply_enabled(monkeypatch):
    """These tests are about what gets applied, so the flag must be on."""
    cfg = MagicMock()
    cfg.self_check_apply = True
    monkeypatch.setattr(server, "load_config", lambda *a, **k: cfg)
    return cfg


def _parser(verdict, reparse=None, reparse_raises=None):
    p = MagicMock()
    p.verify_fast_path_async.return_value = verdict
    p.verify_actions_async.return_value = verdict
    if reparse_raises is not None:
        p.parse.side_effect = reparse_raises
    else:
        p.parse.return_value = reparse if reparse is not None else []
    return p


def _run(monkeypatch, parser, executed, records=(("event", 7, "create_event"),)):
    monkeypatch.setattr(server, "_get_parser", lambda: parser)
    token = "t" * 8
    import time as _t
    server._verify_store[token] = {"ready": False, "correction": None,
                                   "expires": _t.time() + 120}
    server._run_server_verify(token, "mark the report as finished", None,
                              executed=list(executed), records=list(records))
    return server._verify_store.pop(token)["correction"]


_MAJOR = {"severity": "major", "action": "update_todo",
          "parameters": {"match_title": "the report"}, "speech": "I think that was an update."}


def test_a_verdict_the_parser_disagrees_with_is_discarded(monkeypatch, fake_db):
    """The false alarm: the parser lands on what already ran, so nothing moves."""
    parser = _parser(_MAJOR, reparse=[("complete_todo", None)])
    result = _run(monkeypatch, parser, executed=[("complete_todo", None)])

    assert result["applied"] is False
    fake_db.delete_event.assert_not_called()
    fake_db.delete_todo.assert_not_called()


def test_the_replacement_comes_from_the_parser_not_the_verdict(monkeypatch, fake_db):
    """The verifier said update_todo; the parser says create_event. The parser wins.

    This is the "Walk Mark's dog today at 2:30PM" shape: a timed event the
    verifier wanted to file as a task.
    """
    authored = CalendarIntent(title="Walk Mark's dog", date="2026-09-02",
                              start_time="14:30", end_time="15:00")
    parser = _parser(_MAJOR, reparse=[("create_event", authored)])
    _run(monkeypatch, parser, executed=[("create_todo", None)],
         records=(("todo", 3, "create_todo"),))

    # It re-read the sentence rather than trusting the verdict's own parameters.
    parser.parse.assert_called_once()


def test_an_ambiguous_reparse_changes_nothing(monkeypatch, fake_db):
    """Undo-and-redo swaps one record for one record. Two is not that."""
    parser = _parser(_MAJOR, reparse=[
        ("create_event", CalendarIntent(title="a", date="2026-09-02",
                                        start_time="10:00", end_time="11:00")),
        ("create_todo", CreateTodoIntent(titles=["b"])),
    ])
    result = _run(monkeypatch, parser, executed=[("complete_todo", None)])

    assert result["applied"] is False
    fake_db.delete_event.assert_not_called()


def test_an_empty_reparse_changes_nothing(monkeypatch, fake_db):
    parser = _parser(_MAJOR, reparse=[])
    result = _run(monkeypatch, parser, executed=[("complete_todo", None)])

    assert result["applied"] is False
    fake_db.delete_event.assert_not_called()


def test_a_reparse_that_raises_changes_nothing(monkeypatch, fake_db):
    """Ollama dying mid-check must not cost the user their record."""
    parser = _parser(_MAJOR, reparse_raises=RuntimeError("ollama died"))
    result = _run(monkeypatch, parser, executed=[("complete_todo", None)])

    assert result["applied"] is False
    fake_db.delete_event.assert_not_called()


def test_agreement_from_the_verifier_is_silent(monkeypatch, fake_db):
    """ok:true means nothing happened and nothing is said."""
    parser = _parser(None)
    result = _run(monkeypatch, parser, executed=[("create_event", None)])

    assert result == {"ok": True}
    fake_db.delete_event.assert_not_called()
    parser.parse.assert_not_called()


def test_nothing_is_applied_while_the_check_is_advisory(monkeypatch, fake_db, apply_enabled):
    """self_check_apply=false must still detect, and still never touch a record."""
    apply_enabled.self_check_apply = False
    parser = _parser(_MAJOR, reparse=[("create_event", CalendarIntent(
        title="x", date="2026-09-02", start_time="10:00", end_time="11:00"))])
    result = _run(monkeypatch, parser, executed=[("complete_todo", None)])

    assert result["ok"] is False and result["applied"] is False
    fake_db.delete_event.assert_not_called()
    fake_db.delete_todo.assert_not_called()
