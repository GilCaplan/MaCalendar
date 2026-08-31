"""Multi-item task commands: one task per thing, tagged.

"I want to buy chicken and rice" used to produce a single task — at best one
called "rice" alongside "buy chicken", at worst an invented summary, "buy
groceries". Each item is its own task now, the shared verb is repeated, and the
tag is inferred from the title.
"""

from __future__ import annotations

import pytest

from assistant.intent.list_split import split_items
from assistant.actions.todo.tagging import infer_tag, resolve_tags


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phrase,expected", [
    # the bug that started this
    ("buy chicken and rice", ["buy chicken", "buy rice"]),
    ("buy chicken, rice and olive oil", ["buy chicken", "buy rice", "buy olive oil"]),
    # the same shape with other verbs
    ("call mom and dad", ["call mom", "call dad"]),
    ("email alon and ravid", ["email alon", "email ravid"]),
    ("pick up the laundry and the dry cleaning",
     ["pick up the laundry", "pick up the dry cleaning"]),
    # a conjunct with its own verb keeps it
    ("wash the dishes and call the dentist", ["wash the dishes", "call the dentist"]),
    # single item, untouched
    ("renew passport", ["renew passport"]),
])
def test_splits_and_shares_the_verb(phrase, expected):
    assert split_items(phrase) == expected


@pytest.mark.parametrize("phrase", [
    # "and" joining the object of a preposition, not two tasks
    "buy a birthday gift for mom and dad",
    "send the syllabus to guri and ravid",
    # one thing whose name contains "and"
    "buy fish and chips",
    "make mac and cheese",
])
def test_does_not_split_an_internal_and(phrase):
    assert split_items(phrase) == [phrase]


def test_strips_a_dangling_conjunction():
    # The rule parser cuts spans before the conjunction, so a span can end on it.
    assert split_items("wash the dishes and") == ["wash the dishes"]


def test_drop_set_is_applied_before_the_verb_is_shared():
    assert split_items("buy milk and it", drop={"it"}) == ["buy milk"]


# ---------------------------------------------------------------------------
# Tag inference
# ---------------------------------------------------------------------------

PALETTE = ["Coursework", "Groceries", "Errands", "Work", "Personal"]


@pytest.mark.parametrize("title,tag", [
    ("buy chicken", "Groceries"),
    ("buy rice", "Groceries"),
    ("get milk and eggs", "Groceries"),
    ("submit NLP homework", "Coursework"),
    ("pick up a package from the post office", "Errands"),
    ("prepare the sprint standup", "Work"),
])
def test_infers_a_tag_from_the_title(title, tag):
    assert infer_tag(title, PALETTE) == tag


@pytest.mark.parametrize("title", ["call mom", "think about it", "xyzzy"])
def test_no_tag_when_nothing_matches(title):
    # An untagged task is the honest answer; a wrong tag has to be undone by hand.
    assert infer_tag(title, PALETTE) is None


def test_never_infers_personal():
    assert infer_tag("personal admin", ["Personal"]) is None


def test_only_returns_tags_that_exist():
    # The user deleted Groceries — nothing should come back in its place.
    assert infer_tag("buy chicken", ["Coursework", "Work"]) is None


def test_a_custom_tag_matches_on_its_own_name():
    assert infer_tag("renew gym membership", PALETTE + ["Gym"]) == "Gym"


def test_resolve_tags_keeps_only_real_names_and_fixes_casing():
    assert resolve_tags(["groceries", "nonsense"], PALETTE) == ["Groceries"]


# ---------------------------------------------------------------------------
# End to end: command → rows in the DB
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path, monkeypatch):
    from assistant import db as db_module
    from assistant.db import CalendarDB
    real = CalendarDB(path=str(tmp_path / "todo_split_test.db"))
    monkeypatch.setattr(db_module, "get_db", lambda *a, **k: real)
    return real


def _create(intent_kwargs, config):
    from assistant.actions.todo.action import CreateTodoAction
    from assistant.actions.todo.intent import CreateTodoIntent
    return CreateTodoAction().execute(CreateTodoIntent(**intent_kwargs), config)


def test_two_items_become_two_tagged_tasks(db, sample_config):
    speech = _create({"titles": ["buy chicken", "buy rice"]}, sample_config)

    rows = db.get_todos()
    assert [r["title"] for r in rows] == ["buy chicken", "buy rice"]
    assert all(r["tags"] == ["Groceries"] for r in rows)
    # The confirmation names them — after a multi-item command "Added 2 tasks"
    # doesn't tell you whether it understood.
    assert "buy chicken" in speech and "buy rice" in speech
    assert "Groceries" in speech


def test_each_task_is_tagged_on_its_own_merits(db, sample_config):
    _create({"titles": ["buy chicken", "submit NLP homework"]}, sample_config)
    by_title = {r["title"]: r["tags"] for r in db.get_todos()}
    assert by_title["buy chicken"] == ["Groceries"]
    assert by_title["submit NLP homework"] == ["Coursework"]


def test_a_spoken_tag_beats_inference(db, sample_config):
    _create({"titles": ["buy chicken"], "tags": ["errands"]}, sample_config)
    assert db.get_todos()[0]["tags"] == ["Errands"]


def test_an_unknown_spoken_tag_falls_back_to_inference(db, sample_config):
    _create({"titles": ["buy chicken"], "tags": ["nonsense"]}, sample_config)
    assert db.get_todos()[0]["tags"] == ["Groceries"]


def test_tag_mode_still_wins_over_inference(db, sample_config):
    sample_config.todo.auto_tag = "Work"
    _create({"titles": ["buy chicken"]}, sample_config)
    assert db.get_todos()[0]["tags"] == ["Work"]


def test_inference_can_be_switched_off(db, sample_config):
    sample_config.todo.auto_tag_infer = False
    _create({"titles": ["buy chicken"]}, sample_config)
    assert db.get_todos()[0]["tags"] == []


def test_multi_item_subtasks_become_one_subtask_each(db, sample_config):
    from assistant.actions.todo.action import AddSubtaskAction
    from assistant.actions.todo.intent import AddSubtaskIntent

    parent = db.create_todo(title="Shabbat cooking", list_name="today",
                            priority="none", due_date="")
    AddSubtaskAction().execute(
        AddSubtaskIntent(parent_title="Shabbat cooking", subtask_title="buy chicken and rice"),
        sample_config,
    )
    assert [s["title"] for s in db.get_subtasks(parent)] == ["buy chicken", "buy rice"]


# ---------------------------------------------------------------------------
# The rule parser, on the phrasings that reported the bug
# ---------------------------------------------------------------------------

@pytest.fixture
def parser(isolated_registry):
    from assistant.actions.calendar.action import (
        CreateEventAction, UpdateEventAction, DeleteEventAction, QueryScheduleAction,
    )
    from assistant.actions.todo.action import (
        CreateTodoAction, CompleteTodoAction, DeleteTodoAction, UpdateTodoAction,
        QueryTodoAction, AddSubtaskAction, CompleteSubtaskAction, DeleteSubtaskAction,
    )
    from assistant.intent.rule_parser import RuleBasedParser

    for cls in [CreateEventAction, UpdateEventAction, DeleteEventAction,
                QueryScheduleAction, CreateTodoAction, CompleteTodoAction,
                DeleteTodoAction, UpdateTodoAction, QueryTodoAction,
                AddSubtaskAction, CompleteSubtaskAction, DeleteSubtaskAction]:
        isolated_registry._actions[cls.action_name] = cls
    return RuleBasedParser(isolated_registry)


def _titles(parser, text):
    from assistant.intent.rule_parser import RULE_THRESHOLD
    result = parser.analyze(text, current_view="todo")
    assert result.confidence >= RULE_THRESHOLD, result.missing_slots
    titles = []
    for name, intent in result.intents:
        assert name == "create_todo"
        titles.extend(intent.titles)
    return [t.lower() for t in titles]


@pytest.mark.parametrize("text", [
    "I want to buy chicken and rice",
    "I need to buy chicken and rice",
    "remind me to buy chicken and rice",
    "add a task to buy chicken and rice",
])
def test_the_reported_command_makes_two_tasks(parser, text):
    assert _titles(parser, text) == ["buy chicken", "buy rice"]


def test_comma_list_shares_the_verb(parser):
    assert _titles(parser, "remind me to buy chicken, rice and olive oil") == [
        "buy chicken", "buy rice", "buy olive oil"]


def test_other_verbs_split_the_same_way(parser):
    assert _titles(parser, "remind me to call mom and dad") == ["call mom", "call dad"]


def test_a_named_list_becomes_a_tag(parser):
    result = parser.analyze("put milk and bananas on the groceries list", current_view="todo")
    _, intent = result.intents[0]
    assert [t.lower() for t in intent.titles] == ["milk", "bananas"]
    assert intent.tags == ["groceries"]


def test_one_errand_for_two_people_stays_one_task(parser):
    assert _titles(parser, "remind me to buy a birthday gift for mom and dad") == [
        "buy a birthday gift for mom and dad"]


# ---------------------------------------------------------------------------
# The REST path the phone uses — same precedence as voice
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MACALENDAR_DB", str(tmp_path / "todo_split_api.db"))
    import assistant.db as _db
    monkeypatch.setattr(_db, "_db_instance", None)
    from assistant.api.server import create_app
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.mark.parametrize("payload", [{"title": "buy chicken"},
                                     {"title": "buy chicken", "tags": []}])
def test_post_todos_infers_a_tag_when_none_was_sent(client, payload):
    # The phone always sends the key, empty when the user picked nothing.
    assert client.post("/todos", json=payload).status_code == 201
    assert client.get("/todos").get_json()[0]["tags"] == ["Groceries"]


def test_post_todos_leaves_an_explicit_tag_alone(client):
    client.post("/todos", json={"title": "buy chicken", "tags": ["Work"]})
    assert client.get("/todos").get_json()[0]["tags"] == ["Work"]


# ---------------------------------------------------------------------------
# The Mac tasks panel — same precedence again
# ---------------------------------------------------------------------------

def test_mac_panel_tag_precedence(db):
    pytest.importorskip("PyQt6")
    from assistant.calendar_ui.todo_view import TodoListWidget, UNTAGGED_KEY

    class Panel:            # only the three attributes _new_task_tags reads
        _auto_tag = ""
        _auto_tag_infer = True
        _tag_filter: list = []

    pick = TodoListWidget._new_task_tags
    panel = Panel()

    assert pick(panel, "buy chicken") == ["Groceries"]
    assert pick(panel, "call mom") == []

    panel._tag_filter = ["Work"]                 # the filter you're looking at wins
    assert pick(panel, "buy chicken") == ["Work"]

    panel._tag_filter = [UNTAGGED_KEY]           # …and Untagged means untagged
    assert pick(panel, "buy chicken") == []

    panel._tag_filter = []
    panel._auto_tag = "Errands"                  # tag mode wins over inference
    assert pick(panel, "buy chicken") == ["Errands"]

    panel._auto_tag = ""
    panel._auto_tag_infer = False
    assert pick(panel, "buy chicken") == []
