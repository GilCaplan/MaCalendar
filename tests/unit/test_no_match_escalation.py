"""Escalating to the LLM when a confident rule parse matches nothing.

"Walk Mark's dog today at 2:30PM" answered "I couldn't find a task matching
'walk mark stalk'" because INTENT_MAP routes the verb "mark" to complete_todo.
The rules scored it 1.00 with every slot filled, so none of the three
pre-execution handoff signals — low confidence, missing slots, a crash — fired.
The parse was confident, complete and wrong, and only running it revealed that.

Escalation therefore has to happen *after* execution comes up empty, which is
what TargetNotFound signals. These tests drive the real Flask route, because
that is the only place this logic lives now: the Mac GUI posts here too.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from assistant.actions.calendar.intent import CalendarIntent
from assistant.actions.todo.intent import CompleteTodoIntent
from assistant.exceptions import TargetNotFound
import assistant.api.server as server

SAID = "Walk Mark Stalk today at 230PM"


class _RuleResult:
    """What the rule parser hands back for this sentence: confident and wrong."""

    def __init__(self, intents):
        self.confidence = 1.0
        self.missing_slots = []
        self.intents = intents
        self.raw_slots = {n: {} for n, _ in intents}
        self.transcript = SAID


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_get_rule_parser", lambda: None)
    app = server.create_app()
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture(autouse=True)
def no_verify(monkeypatch):
    """The background self-check is a separate concern; keep it out of the way."""
    cfg = server.load_config()
    cfg.verify_fast_path = False
    monkeypatch.setattr(server, "load_config", lambda *a, **k: cfg)


def _wire(monkeypatch, rule_intents, reparse, execute_results):
    """Point the server at a fake rule parser, LLM parser and action registry."""
    rp = MagicMock()
    rp.analyze.return_value = _RuleResult(rule_intents)
    monkeypatch.setattr(server, "_get_rule_parser", lambda: rp)

    parser = MagicMock()
    parser.parse.return_value = reparse
    parser.last_llm_ms = 0
    parser.last_examples_used = 0
    parser.last_raw_response = ""
    monkeypatch.setattr(server, "_get_parser", lambda: parser)

    registry = MagicMock()

    def _get(name):
        cls = MagicMock()
        cls.return_value.execute.side_effect = execute_results[name]
        cls.view_switch = None
        return cls

    registry.get.side_effect = _get
    monkeypatch.setattr(server, "_get_registry", lambda: registry)
    return parser


def test_a_confident_wrong_parse_that_matches_nothing_is_re_read(monkeypatch, client):
    """The reported failure: answer an event, not "I couldn't find a task"."""
    parser = _wire(
        monkeypatch,
        rule_intents=[("complete_todo", CompleteTodoIntent(match_title="walk mark stalk"))],
        reparse=[("create_event", CalendarIntent(title="Walk Mark Stalk", date="2026-09-02",
                                                 start_time="14:30", end_time="15:30"))],
        execute_results={
            "complete_todo": TargetNotFound("I couldn't find a task matching 'walk mark stalk'."),
            "create_event": ["Created event 'Walk Mark Stalk'."],
        },
    )
    r = client.post("/voice/text", json={"transcript": SAID})
    body = r.get_json()

    assert r.status_code == 200
    assert "Created event" in body["message"]
    assert body["actions"] == ["create_event"]
    parser.parse.assert_called_once_with(SAID)
    titles = [s["title"] for s in body["trace"]]
    assert "Nothing matched — rechecking" in titles


def test_the_escalation_step_is_not_reported_as_a_failure(monkeypatch, client):
    """It is a recovery, and it works. Rendering it red says the command broke."""
    _wire(
        monkeypatch,
        rule_intents=[("complete_todo", CompleteTodoIntent(match_title="walk mark stalk"))],
        reparse=[("create_event", CalendarIntent(title="x", date="2026-09-02",
                                                 start_time="14:30", end_time="15:30"))],
        execute_results={
            "complete_todo": TargetNotFound("I couldn't find a task matching 'walk mark stalk'."),
            "create_event": ["Created event 'x'."],
        },
    )
    body = client.post("/voice/text", json={"transcript": SAID}).get_json()
    step = next(s for s in body["trace"] if s["title"] == "Nothing matched — rechecking")
    assert step["ok"] is True


def test_a_retry_that_agrees_keeps_the_original_answer(monkeypatch, client):
    """If the LLM also says complete_todo, the task really is absent."""
    _wire(
        monkeypatch,
        rule_intents=[("complete_todo", CompleteTodoIntent(match_title="walk mark stalk"))],
        reparse=[("complete_todo", CompleteTodoIntent(match_title="walk mark stalk"))],
        execute_results={
            "complete_todo": TargetNotFound("I couldn't find a task matching 'walk mark stalk'."),
        },
    )
    body = client.post("/voice/text", json={"transcript": SAID}).get_json()

    assert "couldn't find a task" in body["message"]
    assert body["actions"] == []


def test_a_not_found_is_an_answer_not_an_error(monkeypatch, client):
    """TargetNotFound is a result. The bare `except Exception` below it used to
    turn this sentence into "Error: I couldn't find …" on a failed step."""
    _wire(
        monkeypatch,
        rule_intents=[("complete_todo", CompleteTodoIntent(match_title="nope"))],
        reparse=[],
        execute_results={"complete_todo": TargetNotFound("I couldn't find a task matching 'nope'.")},
    )
    body = client.post("/voice/text", json={"transcript": SAID}).get_json()

    assert body["message"].startswith("I couldn't find")
    assert "Error:" not in body["message"]
