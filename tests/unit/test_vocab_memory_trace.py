"""Unit tests: personal vocabulary, command memory (RAG), trace, and the
vocab/memory/pending API endpoints (Flask test client, no LLM needed)."""

from __future__ import annotations

import json
import os

import pytest

from assistant.stt.vocab import VocabStore
from assistant.intent.memory import CommandMemory
from assistant.trace import Trace, STT, LLM


# --------------------------------------------------------------------- vocab

@pytest.fixture
def vocab(tmp_path):
    return VocabStore(str(tmp_path / "vocab.json"))


def test_alias_and_fuzzy_correction_learns(vocab):
    vocab.add_word("Kyra")
    vocab.add_word("Minchat Maariv", ["Minchan Maribat"])
    text = "walk Kyira the dog then Minchan Maribat at 7"
    fixed, fixes = vocab.correct(text)
    assert fixed == "walk Kyra the dog then Minchat Maariv at 7"
    reasons = {c.original: c.reason for c in fixes}
    assert reasons == {"Kyira": "fuzzy", "Minchan Maribat": "alias"}
    # fuzzy hits are only memorised as aliases when they are near-identical (≥0.9);
    # 0.889 stays fuzzy (still corrected each time, but not learned)
    assert "Kyira" not in vocab._find("Kyra").aliases
    _, fixes2 = vocab.correct("Kyira again")
    assert fixes2[0].reason == "fuzzy"
    vocab.correct("Kyrah")           # 0.889 too… use an explicit teach for the learned path
    vocab.add_alias("Kyira", "Kyra")
    assert vocab.correct("Kyira again")[1][0].reason == "alias"


def test_protected_common_words_not_replaced(vocab):
    vocab.add_word("Kyra")
    fixed, fixes = vocab.correct("add the data to the meeting today")
    assert fixed == "add the data to the meeting today"
    assert fixes == []


def test_punctuation_preserved(vocab):
    vocab.add_word("Shaul")
    fixed, _ = vocab.correct("go to Shaull, then home.")
    assert fixed == "go to Shaul, then home."


def test_english_words_and_known_words_are_never_rewritten(vocab):
    vocab.add_word("Shaul"); vocab.add_word("Tal"); vocab.add_word("Nachman"); vocab.add_word("Shacharit")
    text = "a shawl for Tal, talk to Nachman after Shacharit"
    fixed, fixes = vocab.correct(text)
    assert fixed == text and fixes == []


def test_raising_the_threshold_tightens_matching(vocab):
    """The strictness dial governs the phonetic path as well as the letter one.

    This test used to assert that a threshold of 0.95 left "Shaull" alone. It
    no longer does, and the change is deliberate: "Shaull" and "Shaul" have the
    same sound code and the same syllable count, and nothing else in the list
    sounds like them, so they are the same name written two ways. Refusing that
    was never the point of the dial.

    What the dial does control is how far a spelling may drift, and that is
    what is asserted here — at 0.95 a word the letters cannot reach is refused,
    where at the default it would be corrected.
    """
    vocab.add_word("Shaul")
    vocab.add_word("Bagrut")
    vocab.update_settings(threshold=0.95)

    # Same name, differently spelled: still corrected.
    fixed, fixes = vocab.correct("go to Shaull")
    assert fixed == "go to Shaul" and [f.replacement for f in fixes] == ["Shaul"]

    # A spelling far from the word: the tightened dial refuses it.
    fixed, fixes = vocab.correct("bugroot exam friday")
    assert fixes == [] and fixed == "bugroot exam friday"


def test_turning_auto_correct_off_stops_every_kind_of_correction(vocab, monkeypatch):
    """The off switch has to cover the phonetic path too, or it is not off.

    Checked at `apply_vocab`, which is where the switch lives — `correct()` is
    the mechanism and always corrects; the entry point decides whether to call
    it. Asserting against `correct()` would test the wrong layer and pass
    whatever the switch did.
    """
    import assistant.stt.vocab as V
    vocab.add_word("Bagrut")
    monkeypatch.setattr(V, "get_vocab", lambda: vocab)

    vocab.update_settings(auto_correct=True)
    fixed, fixes = V.apply_vocab("bugroot exam friday")
    assert fixed == "Bagrut exam friday", "the phonetic path should be on here"

    vocab.update_settings(auto_correct=False)
    fixed, fixes = V.apply_vocab("bugroot exam friday")
    assert fixes == [] and fixed == "bugroot exam friday"


def test_whisper_prompt_and_persistence(tmp_path):
    path = str(tmp_path / "v.json")
    v = VocabStore(path)
    assert v.whisper_prompt() is None
    v.add_word("Kyra")
    v.add_alias("Shawl", "Shaul")
    assert set(v.whisper_prompt().removeprefix("Names and words: ").rstrip(".").split(", ")) == {"Kyra", "Shaul"}
    # a second store (other process) sees the same data
    v2 = VocabStore(path)
    assert [e.word for e in v2.entries] == ["Kyra", "Shaul"]
    assert v2._find("Shaul").aliases == ["Shawl"]
    assert v2.remove_word("Kyra") and not v2.remove_word("nope")


def test_suggestions_near_miss_and_unknown_name(vocab):
    vocab.add_word("Shaul")
    vocab.update_settings(threshold=0.9)  # so "Shawl" (0.8) is a near-miss, not a fix
    s = vocab.suggestions("dinner with Shawl and Amichai tomorrow")
    kinds = {x["heard"]: x["reason"] for x in s}
    assert kinds["Shawl"] == "near-miss"
    assert kinds["Amichai"] == "unknown-name"
    assert "tomorrow" not in kinds


def test_recent_recorded(vocab):
    vocab.add_word("Kyra")
    fixed, fixes = vocab.correct("Kyira walk")
    vocab.record_recent("Kyira walk", fixed, fixes, "ios")
    r = vocab.recent[0]
    assert r["corrected"] == "Kyra walk" and r["source"] == "ios"


# -------------------------------------------------------------------- memory

@pytest.fixture
def memory(tmp_path):
    return CommandMemory(str(tmp_path / "mem.db"))


def _ev(title, start="15:30"):
    return {"title": title, "date": "2026-08-26", "start_time": start, "end_time": "16:30"}


def test_record_retrieve_and_mask_dates(memory):
    memory.record(transcript="walk Kyra the dog at 3:30 pm today", parse_path="llm",
                  actions=[("create_event", _ev("Walk Kyra the dog"))])
    memory.record(transcript="buy milk and eggs", parse_path="rule",
                  actions=[("create_todo", {"titles": ["buy milk", "eggs"]})])
    hits = memory.retrieve("walk kyra at 5 pm tomorrow")
    assert [h["transcript"] for h in hits][0].startswith("walk Kyra")
    block = memory.few_shot_block("walk kyra at 5 pm tomorrow", k=1)
    assert "2026-08-26" not in block and '"date"' not in block and "15:30" in block
    assert "buy milk" not in block


def test_identical_transcript_not_returned(memory):
    memory.record(transcript="lunch at noon", actions=[("create_event", _ev("Lunch", "12:00"))])
    assert memory.retrieve("lunch at noon") == []


def test_implicit_feedback_from_record_edit_and_delete(memory):
    ex = memory.record(transcript="walk kyra at 3", actions=[("create_event", _ev("Walk kyra"))],
                       records=[("event", 42, "create_event", 0)])
    assert memory.feedback_for_record("event", 42, "corrected", {"title": "Walk Kyra", "color": "#fff"}) == ex
    row = memory.get(ex)
    assert row["feedback"] == "corrected"
    assert row["correction"][0]["parameters"]["title"] == "Walk Kyra"
    assert "color" not in row["correction"][0]["parameters"]
    # retrieval uses the corrected version and ranks it first
    hit = memory.retrieve("walk kyra at 4")[0]
    assert hit["actions"][0]["parameters"]["title"] == "Walk Kyra"
    # unknown record → no-op
    assert memory.feedback_for_record("event", 999, "rejected") is None
    memory.feedback_for_record("event", 42, "rejected")
    assert memory.retrieve("walk kyra at 4") == []


def test_correcting_one_record_in_a_batch_leaves_the_others_alone(memory):
    # "book gym at 6, then a meeting at 9, then dinner at 7" — three
    # create_event actions in one example. Editing the meeting used to
    # overwrite all three with the meeting's fields, because the match was
    # by action type ("create_event") with nothing to say which of the three
    # a given edit belonged to.
    ex = memory.record(
        transcript="gym, a meeting, and dinner",
        actions=[("create_event", _ev("Gym", "06:00")),
                 ("create_event", _ev("Meeting", "09:00")),
                 ("create_event", _ev("Dinner", "19:00"))],
        records=[("event", 1, "create_event", 0),
                 ("event", 2, "create_event", 1),
                 ("event", 3, "create_event", 2)],
    )
    assert memory.feedback_for_record("event", 2, "corrected", {"title": "Team sync"}) == ex
    row = memory.get(ex)
    titles = [a["parameters"]["title"] for a in row["correction"]]
    assert titles == ["Gym", "Team sync", "Dinner"]

    # a legacy row with no recorded index (-1, pre-migration) refuses to
    # guess rather than repeat the bug
    legacy = memory.record(
        transcript="two calls",
        actions=[("create_event", _ev("Call A")), ("create_event", _ev("Call B"))],
        records=[("event", 10, "create_event", -1), ("event", 11, "create_event", -1)],
    )
    assert memory.feedback_for_record("event", 11, "corrected", {"title": "Call B fixed"}) is None
    assert memory.get(legacy)["feedback"] == "none"


def test_explicit_feedback_and_stats(memory):
    ex = memory.record(transcript="gym at 6", actions=[("create_event", _ev("Gym", "06:00"))], llm_ms=1200, total_ms=1500)
    assert memory.set_feedback(ex, "approved")
    with pytest.raises(ValueError):
        memory.set_feedback(ex, "meh")
    st = memory.stats()
    assert st["total"] == 1 and st["feedback"] == {"approved": 1} and st["avg_llm_ms"] == 1200


def test_pending_queue(memory):
    a = memory.add_pending("call mom tomorrow", "Ollama offline")
    assert memory.add_pending("call mom tomorrow", "again") == a  # dedup
    assert [p["id"] for p in memory.pending()] == [a]
    memory.bump_pending(a)
    memory.resolve_pending(a, "done", "Created event")
    assert memory.pending() == []
    assert memory.get_pending(a)["attempts"] == 2


# --------------------------------------------------------------------- trace

def test_trace_steps_and_listener():
    t = Trace(source="ios")
    seen = []
    t.on_step(seen.append)
    t.step(STT, "Heard", "hello", transcript="hello")
    t.step(LLM, "LLM", ok=False)
    out = t.to_list()
    assert [s["stage"] for s in out] == [STT, LLM]
    assert out[0]["data"] == {"transcript": "hello"} and out[1]["ok"] is False
    assert len(seen) == 2 and "Heard" in t.summary()


# ----------------------------------------------------------------------- API

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MACALENDAR_NO_WARMUP", "1")
    import assistant.stt.vocab as vocab_mod
    import assistant.intent.memory as mem_mod
    monkeypatch.setattr(vocab_mod, "_store", VocabStore(str(tmp_path / "vocab.json")))
    monkeypatch.setattr(mem_mod, "_memory", CommandMemory(str(tmp_path / "mem.db")))
    from assistant.api.server import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_vocab_endpoints(client):
    r = client.post("/vocab", json={"word": "Kyra"})
    assert r.status_code == 201
    r = client.post("/vocab/alias", json={"wrong": "Shawl", "right": "Shaul"})
    assert r.get_json()["aliases"] == ["Shawl"]
    # explicit aliases always win, even for English words; fuzzy fixes Kyira→Kyra
    r = client.post("/vocab/preview", json={"text": "walk Kyira and Shawl"})
    assert r.get_json()["corrected"] == "walk Kyra and Shaul"
    words = {w["word"] for w in client.get("/vocab").get_json()["words"]}
    assert words == {"Kyra", "Shaul"}
    assert client.patch("/vocab/settings", json={"auto_correct": False}).get_json()["auto_correct"] is False
    assert client.delete("/vocab/Kyra").status_code == 200
    assert client.delete("/vocab/Kyra").status_code == 404
    assert client.post("/vocab", json={}).status_code == 400


def test_memory_and_pending_endpoints(client, tmp_path):
    from assistant.intent.memory import get_memory
    ex = get_memory().record(transcript="gym at 6", actions=[("create_event", _ev("Gym", "06:00"))])
    r = client.post(f"/memory/{ex}/feedback", json={"feedback": "approved"})
    assert r.get_json()["feedback"] == "approved"
    assert client.post(f"/memory/{ex}/feedback", json={"feedback": "bad"}).status_code == 400
    assert client.get("/memory").get_json()["stats"]["total"] == 1
    assert client.get("/memory/similar?q=gym%20at%207").get_json()[0]["id"] == ex
    pid = get_memory().add_pending("call mom", "offline")
    assert client.get("/pending").get_json()["pending"][0]["id"] == pid
    assert client.delete(f"/pending/{pid}").get_json()["ok"] is True
    assert client.get("/pending").get_json()["pending"] == []
    assert client.delete(f"/memory/{ex}").get_json()["ok"] is True


# ---------------------------------------------------------------- onboarding

def test_onboarding_apply_and_payload(vocab):
    from assistant.stt import vocab_onboarding as ob
    vocab.add_word("Mincha")
    pl = ob.payload(vocab)
    assert pl["done"] is False and pl["word_count"] == 1
    assert next(p for p in pl["presets"] if p["id"] == "tefillah")["already"] == 1
    res = ob.apply(vocab, {"people": ["Kyra", " Shaul ", ""], "bogus": ["x"]}, ["family"])
    words = {e.word for e in vocab.entries}
    assert {"Kyra", "Shaul", "Ima", "Abba", "Mincha"} <= words and "x" not in words
    assert res["done"] is True and vocab.onboarded is True
    # idempotent
    assert ob.apply(vocab, {"people": ["Kyra"]}, ["family"])["added"] == 0


def test_onboarding_endpoints(client):
    r = client.get("/vocab/onboarding").get_json()
    assert r["done"] is False and len(r["questions"]) == 6
    r = client.post("/vocab/onboarding", json={"answers": {"places": ["Technion"]}, "presets": ["chagim"]}).get_json()
    assert r["added"] > 1 and r["done"] is True
    assert client.get("/vocab/onboarding").get_json()["done"] is True
    assert client.get("/vocab").get_json()["onboarded"] is True


# -------------------------------------------------------------------- import

WA = """[26/08/2026, 10:26:08] Rocky Caplan: yalla we're going to Shul for Mincha
[26/08/2026, 10:27:11] Ofir Levi: beseder, Yotam has his bagrut tomorrow
[26/08/2026, 10:27:40] Rocky Caplan: image omitted
[26/08/2026, 10:28:02] Ofir Levi: אחלה, נתראה בטכניון
26/08/2026, 10:29 - Adin: yalla bagrut at the technion then pizza at Edo's
"""


def test_extract_whatsapp(vocab, monkeypatch):
    from assistant.stt import vocab_import
    # The macOS dictionary is huge (235k words, includes "yalla"); pin a small one
    monkeypatch.setattr(vocab_import, "_DICT", {"we're", "going", "for", "has", "his", "tomorrow", "then", "pizza", "the", "image"})
    vocab.add_word("Technion")
    cands = vocab_import.extract(WA, {e.word for e in vocab.entries})
    by = {c["word"].lower(): c for c in cands}
    assert by["rocky"]["reason"] == "sender" and by["ofir"]["reason"] == "sender" and by["adin"]["reason"] == "sender"
    assert by["yalla"]["reason"] == "non-english" and by["yalla"]["count"] == 2
    assert by["bagrut"]["reason"] == "non-english"
    assert by["shul"]["reason"] == "name" and by["yotam"]["reason"] == "name"
    assert any(c["reason"] == "hebrew" for c in cands)
    assert "technion" not in by and "image" not in by and "omitted" not in by


def test_from_names(monkeypatch):
    from assistant.stt import vocab_import
    monkeypatch.setattr(vocab_import, "_DICT", {"baker", "sarah"})
    out = vocab_import.from_names(["Ofir Levi", "Sarah Baker", "Ima"], {"ima"})
    words = [c["word"] for c in out]
    assert "Ofir" in words and "Levi" in words and "Sarah" in words   # first names always kept
    assert "Baker" not in words and "Ima" not in words                  # dictionary surname / already known


def test_import_endpoints(client):
    r = client.post("/vocab/import", json={"text": WA}).get_json()
    assert any(c["word"] == "Rocky" for c in r["candidates"])
    r = client.post("/vocab/import", json={"names": ["Ofir Levi"]}).get_json()
    assert r["candidates"][0]["reason"] == "contact"
    r = client.post("/vocab/bulk", json={"words": ["Ofir", "Ofir", " ", "Yotam"]}).get_json()
    assert r["added"] == 2


def test_repair_encoding_and_sender_cleanup():
    from assistant.stt import vocab_import as vi
    clean = "[26/08/2026, 10:26:08] Ravid “the Cutie” Neeman: don’t know שלום\n[26/08/2026, 10:27:00] ~ Gil: hi"
    garbled = clean.encode("utf-8").decode("latin-1")
    assert vi.repair_encoding(garbled) == clean
    assert vi.repair_encoding("plain ascii") == "plain ascii"
    assert vi.clean_sender("Ravid “the Cutie” Neeman") == "Ravid Neeman"
    assert vi.clean_sender("~>Gil~>") == "Gil" and vi.clean_sender("~ Rocky Caplan") == "Rocky Caplan"
    cands = vi.extract(garbled)
    assert {c["word"] for c in cands if c["reason"] == "sender"} == {"Ravid", "Gil"}
    assert any(c["reason"] == "hebrew" and c["word"] == "שלום" for c in cands)
