"""The user's own words, carrying what they mean.

The vocabulary already knew "Haxaga" and "Malag" were words this user says —
374 of them, hand-curated. It had nowhere to record what they were *about*, so
the tagger could not use any of it, and half the untagged tasks were course
work that the system already had the word for.

Three things can be true of a personal word, and they behave differently:

  aliases     fix a mishearing. "hexagon" was never what you said, so the
              transcript is rewritten and nothing is lost.
  expands_to  is shorthand. "MT" *is* what you said, so it is never
              substituted — expanding it would edit your words. It is context.
  label       is what the word implies. "Haxaga" is a course.
"""
from __future__ import annotations

import json

import pytest

from assistant.stt.vocab import VocabEntry, VocabStore


@pytest.fixture
def vocab(tmp_path, monkeypatch):
    path = tmp_path / "vocab.json"
    monkeypatch.setenv("MACALENDAR_VOCAB", str(path))
    s = VocabStore(str(path))
    # infer_tag reaches for the process-wide singleton, and VOCAB_PATH is read
    # at import — setting the environment variable afterwards changes neither.
    # Inject the store, or the tagger reads the real vocabulary.
    import assistant.stt.vocab as _v
    monkeypatch.setattr(_v, "_store", s)
    for word, label, expands in [
        ("Haxaga", "Coursework", ""),
        ("Malag", "Coursework", ""),
        ("MCV", "Coursework", "Modern Computer Vision"),
        ("MT", "Coursework", "Mishnah Torah"),
        ("Kyra", "", ""),                       # a name, no label
    ]:
        s.add_word(word)
        e = next(e for e in s.entries if e.word == word)
        e.label, e.expands_to = label, expands
    s._save()
    return s


# ------------------------------------------------------------ storage shape

def test_an_entry_without_the_new_fields_is_written_as_before(tmp_path):
    """374 existing entries must not grow empty fields."""
    e = VocabEntry.from_dict({"word": "Kyra", "aliases": [], "hits": 0, "added": 1.0})
    assert e.to_dict() == {"word": "Kyra", "aliases": [], "hits": 0, "added": 1.0}


def test_the_new_fields_round_trip(tmp_path):
    e = VocabEntry.from_dict({"word": "MT", "expands_to": "Mishnah Torah",
                              "label": "Coursework", "hits": 3, "added": 1.0})
    assert e.to_dict()["expands_to"] == "Mishnah Torah"
    assert e.to_dict()["label"] == "Coursework"
    assert e.is_acronym is True


def test_a_word_with_no_expansion_is_not_an_acronym():
    assert VocabEntry(word="Haxaga", label="Coursework").is_acronym is False


# ----------------------------------------------------------------- labelling

@pytest.mark.parametrize("title", [
    "Check Ori's Haxaga Assignments",
    "Close Malag",
    "MCV lecture notes",
    "read a chapter of MT",
])
def test_a_personal_word_carries_its_label(vocab, title):
    assert vocab.label_for(title) == "Coursework"


def test_a_word_without_a_label_says_nothing(vocab):
    assert vocab.label_for("walk Kyra") == ""


def test_text_with_no_personal_words_says_nothing(vocab):
    assert vocab.label_for("buy zucchini and canola oil") == ""


def test_a_partial_word_does_not_match(vocab):
    """"MTV" is not "MT"; matching inside words would label half the calendar."""
    assert vocab.label_for("watch MTV") == ""
    assert vocab.label_for("Malaga holiday") == ""


def test_the_longest_word_wins(tmp_path, monkeypatch):  # noqa: D401
    """So a multi-word entry beats a single word inside it, rather than the
    answer depending on dictionary order."""
    path = tmp_path / "v.json"
    monkeypatch.setenv("MACALENDAR_VOCAB", str(path))
    s = VocabStore(str(path))
    for w, lab in (("vision", "Work"), ("modern computer vision", "Coursework")):
        s.add_word(w)
        next(e for e in s.entries if e.word == w).label = lab
    s._save()
    assert s.label_for("modern computer vision assignment") == "Coursework"


# ------------------------------------------------------------------ acronyms

def test_acronyms_are_listed_longest_first(vocab):
    words = [e.word for e in vocab.acronyms()]
    assert set(words) == {"MCV", "MT"}
    assert words == sorted(words, key=lambda w: -len(w))


def test_shorthand_is_explained_not_substituted(vocab):
    """The task still says what you wrote. The model is told what it means."""
    note = vocab.expansion_note("Chapter of MT")
    assert "MT = Mishnah Torah" in note
    assert vocab.label_for("Chapter of MT") == "Coursework"


def test_no_shorthand_means_no_note(vocab):
    assert vocab.expansion_note("buy milk") == ""


# ------------------------------------------------------------- the tagger

def test_the_tagger_uses_a_personal_label(vocab):
    from assistant.actions.todo.tagging import infer_tag
    assert infer_tag("Check Ori's Haxaga Assignments") == "Coursework"
    assert infer_tag("Close Malag") == "Coursework"


def test_a_personal_label_outranks_the_shipped_keywords(vocab):
    """They said Haxaga is a course. That beats a word list from the app."""
    from assistant.actions.todo.tagging import infer_tag
    e = next(e for e in vocab.entries if e.word == "Haxaga")
    e.label = "Work"
    vocab._save()
    assert infer_tag("Haxaga homework assignment") == "Work"


def test_tasks_with_no_personal_words_are_unaffected(vocab):
    from assistant.actions.todo.tagging import infer_tag
    assert infer_tag("buy zucchini") == "Groceries"
    assert infer_tag("pick up the package") == "Errands"
