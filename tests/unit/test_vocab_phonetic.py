"""Speech fails phonetically; the matcher compared letters.

Every one of these was a real command that produced a wrong record, and in
every case the word the speaker meant was ALREADY in the personal word list:

    heard "bugroot", meant "Bagrut"    0.62 by letters, needed 0.90
    heard "makabi",  meant "Maccabi"   0.77
    heard "ofeer",    meant "Ofir"      0.75
    heard "yotem",   meant "Yotam"     0.80

None was reachable, so none was corrected, so the alias was never learned, and
the same command failed identically the next day. The learning loop was sound
and could never start.

Lowering the letter threshold is not the fix — that is what previously rewrote
correct names to wrong ones. Instead a word is coded by how it SOUNDS, and a
match on that code is allowed at a much lower letter threshold, behind three
guards. The guards are the interesting part: each one stopped a real mistake
found while measuring this against the whole command history.
"""
from __future__ import annotations

import pytest

from assistant.stt.vocab import VocabStore, phonetic_key


@pytest.fixture
def vocab(tmp_path):
    """A word list holding the words these transcripts should resolve to."""
    v = VocabStore(str(tmp_path / "vocab.json"))
    for word in ("Bagrut", "Maccabi", "Ofir", "Yotam", "Nachman", "Doron", "daven"):
        v.add_word(word)
    return v


def _fix(vocab: VocabStore, heard: str) -> str:
    _, corrections = vocab.correct(f"meeting with {heard} tomorrow", learn=False)
    return corrections[0].replacement if corrections else ""


# ---------------------------------------------------------------------------
# The failures this exists for — all on FIRST encounter, before any learning
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("heard, meant", [
    ("bugroot", "Bagrut"),
    ("makabi",  "Maccabi"),
    ("ofeer",    "Ofir"),
    ("yotem",   "Yotam"),
    ("Doran",   "Doron"),
    ("Doven",   "daven"),
])
def test_a_misheard_name_is_recovered_the_first_time(vocab, heard, meant):
    assert _fix(vocab, heard) == meant


def test_the_letter_matcher_still_handles_what_it_always_did(vocab):
    """'nahman' scores 0.92 and never needed phonetics. It must not regress."""
    assert _fix(vocab, "nahman") == "Nachman"


# ---------------------------------------------------------------------------
# The guards. Each of these stopped a real false positive.
# ---------------------------------------------------------------------------

def test_an_ordinary_word_is_not_rewritten_to_a_short_code_twin(tmp_path):
    """The one that nearly shipped: 'pasta' and 'pset' share the code P-S-T.

    Soundex discards vowels, which is exactly the difference between them.
    Requiring the same number of vowel runs separates them, and this was found
    by replaying the whole command history rather than by reasoning about it.
    """
    v = VocabStore(str(tmp_path / "v.json"))
    v.add_word("pset")
    assert _fix(v, "pasta") == "", "'pasta' was rewritten to a word it does not sound like"


def test_a_multi_word_entry_is_never_matched_phonetically(tmp_path):
    """Word boundaries move when a phrase is misheard, so a code over a phrase
    is not comparable to one over the transcript. Caught 'set meeting for'
    being rewritten to 'set a meeting'."""
    v = VocabStore(str(tmp_path / "v.json"))
    v.add_word("set a meeting")
    _, corrections = v.correct("set meeting for tomorrow", learn=False)
    assert not [c for c in corrections if c.reason == "phonetic"]


def test_a_real_english_word_is_left_alone(tmp_path):
    """The pre-existing guard, which the phonetic branch must not bypass."""
    v = VocabStore(str(tmp_path / "v.json"))
    v.add_word("Mira")
    assert _fix(v, "meter") == ""


def test_when_two_words_sound_alike_the_letters_decide(tmp_path):
    """A bucket of one is unambiguous; a bucket of several is not, so the
    closest spelling wins rather than whichever happened to be checked first."""
    v = VocabStore(str(tmp_path / "v.json"))
    v.add_word("Doron")
    v.add_word("Duran")
    assert phonetic_key("Doron") == phonetic_key("Duran"), "test needs a real collision"
    assert _fix(v, "Doran") == "Doron"


# ---------------------------------------------------------------------------
# The loop this unblocks
# ---------------------------------------------------------------------------

def test_a_phonetic_hit_is_remembered_so_the_next_one_is_instant(vocab):
    """The whole point. The correction was never made, so it was never learned.

    Once made, the existing auto-learn stores the misheard spelling as an
    alias and every later occurrence is an exact hit rather than a guess.
    """
    vocab.correct("meeting with bugroot tomorrow", learn=True)
    entry = next(e for e in vocab.entries if e.word == "Bagrut")
    assert "bugroot" in [a.lower() for a in entry.aliases], \
        "the recovered mishearing was not learned"

    _, corrections = vocab.correct("bugroot exam friday", learn=False)
    assert corrections and corrections[0].reason == "alias", \
        "the second encounter should be an exact alias hit, not another guess"


# ---------------------------------------------------------------------------
# The coding itself
# ---------------------------------------------------------------------------

def test_words_that_sound_alike_share_a_code():
    assert phonetic_key("bugroot") == phonetic_key("Bagrut")
    assert phonetic_key("makabi") == phonetic_key("Maccabi")


def test_words_that_merely_look_alike_do_not():
    assert phonetic_key("Tal") != phonetic_key("Talk")


def test_non_latin_script_has_no_code_and_is_never_matched(tmp_path):
    """The coding table is meaningless for Hebrew, and 54 entries are in it.

    An empty key must never match another empty key, or every Hebrew word in
    the list would be interchangeable with every other.
    """
    assert phonetic_key("בוקר") == ""
    v = VocabStore(str(tmp_path / "v.json"))
    v.add_word("בוקר")
    v.add_word("מנחה")
    _, corrections = v.correct("meeting with מנחה tomorrow", learn=False)
    assert not [c for c in corrections if c.reason == "phonetic"]
