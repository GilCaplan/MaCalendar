"""The words the assistant has learned must be visible and editable.

The vocabulary gained two fields beyond spelling corrections — a label that
decides how a task is tagged, and an expansion for shorthand — and both were
reachable only by editing a JSON file by hand. That is the wrong shape for
something that silently changes how commands are interpreted: if a label is
wrong, tasks are filed wrongly, and the only symptom is tasks in the wrong
place with no clue as to why.

The rules the settings screens depend on:

  * omitting a field leaves it alone, so a client that predates a field
    cannot wipe it;
  * passing an empty string clears it, which is how "remove this label" works
    without a second endpoint;
  * passing aliases replaces the list, because the screen shows all of them
    and a partial update would drop what it was not told about.
"""
from __future__ import annotations

import pytest

from assistant.stt.vocab import VocabStore


@pytest.fixture
def vocab(tmp_path):
    return VocabStore(str(tmp_path / "vocab.json"))


@pytest.fixture
def client():
    """The API both settings screens talk to.

    conftest already points MACALENDAR_VOCAB at a scratch file, so this writes
    to that and never to the hand-curated real word list.
    """
    from assistant.api import server
    app = server.create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_a_new_word_can_carry_a_label_and_an_expansion(vocab):
    entry = vocab.add_word("MCV", label="Coursework", expands_to="Modern Computer Vision")
    assert entry.label == "Coursework"
    assert entry.expands_to == "Modern Computer Vision"


def test_re_adding_a_word_to_add_an_alias_keeps_its_label(vocab):
    """The path that would silently undo a label: add the word again later."""
    vocab.add_word("MCV", label="Coursework")
    again = vocab.add_word("MCV", ["em see vee"])
    assert again.label == "Coursework", "adding an alias wiped the label"
    assert "em see vee" in again.aliases


def test_editing_one_field_leaves_the_others_alone(vocab):
    vocab.add_word("MCV", ["em see vee"], label="Coursework",
                   expands_to="Modern Computer Vision")
    edited = vocab.update_word("MCV", label="Study")
    assert edited.label == "Study"
    assert edited.expands_to == "Modern Computer Vision"
    assert edited.aliases == ["em see vee"]


def test_an_empty_string_clears_a_field(vocab):
    """Distinct from omitting it — this is the 'remove this label' button."""
    vocab.add_word("MCV", label="Coursework")
    assert vocab.update_word("MCV", label="").label == ""


def test_aliases_are_replaced_not_merged(vocab):
    """The screen shows every alias, so it always sends the whole list."""
    vocab.add_word("MCV", ["em see vee", "emcee vee"])
    edited = vocab.update_word("MCV", aliases=["em see vee"])
    assert edited.aliases == ["em see vee"]


def test_editing_a_word_that_does_not_exist_reports_it(vocab):
    assert vocab.update_word("nosuchword", label="x") is None


def test_an_alias_equal_to_the_word_is_not_stored(vocab):
    """It would make the corrector rewrite the word to itself."""
    edited = vocab.update_word("MCV", aliases=["MCV"]) if vocab.add_word("MCV") else None
    assert edited is not None and edited.aliases == []


def test_changes_survive_a_reload(vocab, tmp_path):
    """The file is the store; an edit that only lives in memory is lost."""
    vocab.add_word("MCV", label="Coursework")
    vocab.update_word("MCV", expands_to="Modern Computer Vision")
    fresh = VocabStore(str(tmp_path / "vocab.json"))
    entry = next(e for e in fresh.entries if e.word == "MCV")
    assert (entry.label, entry.expands_to) == ("Coursework", "Modern Computer Vision")


# ---------------------------------------------------------------------------
# Through the API, which is what both settings screens actually talk to
# ---------------------------------------------------------------------------

def test_the_api_can_add_and_edit_a_word(client):
    r = client.post("/vocab", json={"word": "MCV", "label": "Coursework",
                                    "expands_to": "Modern Computer Vision"})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["label"] == "Coursework"

    r = client.patch("/vocab/MCV", json={"label": "Study"})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["label"] == "Study"
    assert body["expands_to"] == "Modern Computer Vision", "an omitted field was wiped"


def test_the_api_refuses_to_edit_an_unknown_word(client):
    assert client.patch("/vocab/nosuchword", json={"label": "x"}).status_code == 404


def test_the_api_refuses_an_empty_edit(client):
    """A PATCH with nothing in it is a client bug, not a no-op to swallow."""
    assert client.patch("/vocab/MCV", json={}).status_code == 400


def test_the_word_list_comes_back_with_the_new_fields(client):
    client.post("/vocab", json={"word": "MCV", "label": "Coursework"})
    entries = client.get("/vocab").get_json()["words"]
    entry = next(e for e in entries if e["word"] == "MCV")
    assert entry["label"] == "Coursework"
