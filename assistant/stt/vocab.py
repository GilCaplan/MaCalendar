"""Personal vocabulary — teaches the STT layer your names and non-English words.

Two mechanisms, both driven by one shared store (~/.assistant_tools/vocab.json):

1. **Whisper biasing** — every vocab word is fed to faster-whisper as
   ``initial_prompt`` so the decoder is nudged towards spelling them correctly
   in the first place (works surprisingly well for names like "Kyra", "Shaul").

2. **Post-transcription auto-correct** — each transcript is scanned for tokens
   that are (a) a known *alias* of a vocab word (something Whisper previously
   produced and you corrected), or (b) fuzzy-similar to a vocab word above a
   threshold. Matches are replaced and the misheard form is remembered as a
   new alias so it becomes an exact hit next time — the system learns.

The store is a JSON file rather than the SQLite DB so the Mac app process and
the iOS API process can both read/write it without schema coordination.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# MACALENDAR_VOCAB lets tests/audits point at a scratch file, the same way
# MACALENDAR_DB and MACALENDAR_MEMORY_DB do — without it, anything that
# exercised the pipeline wrote into the user's real personal vocabulary.
VOCAB_PATH = os.environ.get("MACALENDAR_VOCAB") or os.path.expanduser("~/.assistant_tools/vocab.json")

DEFAULT_THRESHOLD = 0.80   # difflib ratio; 1.0 = identical
MIN_FUZZY_LEN = 3          # never fuzzy-match tokens shorter than this
RECENT_LIMIT = 20          # transcripts kept for the "fix a word" UI

# Very common English words that must never be fuzzy-replaced by a vocab word
# (e.g. vocab "Kyra" vs transcript "data"). Exact alias hits still win.
_PROTECTED = {
    "the", "and", "for", "from", "with", "that", "this", "then", "than", "them",
    "there", "their", "they", "have", "has", "had", "was", "were", "will", "what",
    "when", "where", "who", "why", "how", "data", "date", "day", "days", "time",
    "today", "tomorrow", "week", "month", "year", "meeting", "event", "task",
    "todo", "add", "set", "make", "create", "delete", "remove", "move", "change",
    "morning", "noon", "afternoon", "evening", "night", "next", "last", "every",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "one", "two", "three", "four",
    "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "half",
    "quarter", "past", "till", "until", "before", "after", "about", "around",
    "execute", "done", "stop", "go", "submit", "confirm", "please", "walk", "call",
    "with", "into", "onto", "over", "under", "also", "some", "more", "note",
}


_ENGLISH: set[str] | None = None


def _english() -> set[str]:
    """System dictionary — a fuzzy match must never rewrite a real English word."""
    global _ENGLISH
    if _ENGLISH is None:
        try:
            with open("/usr/share/dict/words", encoding="utf-8", errors="ignore") as f:
                _ENGLISH = {w.strip().lower() for w in f if w.strip()}
        except OSError:
            _ENGLISH = set()
    return _ENGLISH


def _norm(s: str) -> str:
    """Lowercase, strip punctuation/diacritics-ish noise for comparison."""
    return re.sub(r"[^a-z0-9֐-׿' ]+", "", s.lower()).strip()


@dataclass
class VocabEntry:
    """A word this user says that English does not know.

    Three things can be true of such a word, and they are deliberately
    separate because they behave differently:

    `aliases` fix a mishearing. "hexagon" was never what you said, so the
    transcript is rewritten and nothing is lost.

    `expands_to` is shorthand. "MT" *is* what you said and meant, so it is
    never substituted into your text — expanding it would edit your words
    rather than correct them. It is context: what the acronym means, for
    labelling, for search, and for telling the model.

    `label` is what the word implies about a task or event. "Haxaga" is a
    course, so a task mentioning it is Coursework. This is the field that was
    missing: the vocabulary already knew Haxaga and Malag were your words, and
    the tagger could not use that, so both systems learned about the same 374
    words separately.
    """

    word: str
    aliases: list[str] = field(default_factory=list)
    hits: int = 0
    added: float = field(default_factory=time.time)
    expands_to: str = ""
    label: str = ""

    @property
    def is_acronym(self) -> bool:
        return bool(self.expands_to)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"word": self.word, "aliases": self.aliases,
                             "hits": self.hits, "added": self.added}
        # Written only when set, so 374 existing entries keep the shape they
        # have and a hand-edited vocab.json does not grow empty fields.
        if self.expands_to:
            d["expands_to"] = self.expands_to
        if self.label:
            d["label"] = self.label
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "VocabEntry":
        return cls(
            word=str(d.get("word", "")).strip(),
            aliases=[str(a) for a in d.get("aliases", []) if str(a).strip()],
            hits=int(d.get("hits", 0)),
            added=float(d.get("added", time.time())),
            expands_to=str(d.get("expands_to", "") or "").strip(),
            label=str(d.get("label", "") or "").strip(),
        )


@dataclass
class Correction:
    original: str
    replacement: str
    reason: str  # "alias" | "fuzzy"
    score: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {"from": self.original, "to": self.replacement, "reason": self.reason,
                "score": round(self.score, 3)}


class VocabStore:
    """Thread-safe, file-backed vocabulary. Reloads if the file changes on disk."""

    def __init__(self, path: str = VOCAB_PATH) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._entries: list[VocabEntry] = []
        self._recent: list[dict[str, Any]] = []
        self.auto_correct: bool = True
        self.learn_aliases: bool = True
        self.threshold: float = DEFAULT_THRESHOLD
        self.onboarded: bool = False
        self._mtime: float = -1.0
        self._load()

    # ---------------------------------------------------------------- I/O

    def _load(self) -> None:
        with self._lock:
            try:
                mtime = os.path.getmtime(self._path)
            except OSError:
                self._entries, self._recent, self._mtime = [], [], -1.0
                return
            if mtime == self._mtime:
                return
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:  # corrupt file — don't crash the assistant
                logger.warning("Vocab file unreadable (%s); starting empty", e)
                data = {}
            self._entries = [VocabEntry.from_dict(d) for d in data.get("entries", [])]
            self._entries = [e for e in self._entries if e.word]
            self._recent = list(data.get("recent", []))[-RECENT_LIMIT:]
            self.auto_correct = bool(data.get("auto_correct", True))
            self.learn_aliases = bool(data.get("learn_aliases", True))
            self.threshold = float(data.get("threshold", DEFAULT_THRESHOLD))
            self.onboarded = bool(data.get("onboarded", False))
            self._mtime = mtime

    def _save(self) -> None:
        with self._lock:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            data = {
                "auto_correct": self.auto_correct,
                "learn_aliases": self.learn_aliases,
                "threshold": self.threshold,
                "onboarded": self.onboarded,
                "entries": [e.to_dict() for e in self._entries],
                "recent": self._recent[-RECENT_LIMIT:],
            }
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
            try:
                self._mtime = os.path.getmtime(self._path)
            except OSError:
                pass

    def reload(self) -> None:
        self._load()

    # ---------------------------------------------------------- accessors

    @property
    def entries(self) -> list[VocabEntry]:
        self._load()
        with self._lock:
            return sorted(self._entries, key=lambda e: e.word.lower())

    @property
    def recent(self) -> list[dict[str, Any]]:
        self._load()
        with self._lock:
            return list(reversed(self._recent))

    def to_dict(self) -> dict[str, Any]:
        return {
            "auto_correct": self.auto_correct,
            "learn_aliases": self.learn_aliases,
            "threshold": self.threshold,
            "onboarded": self.onboarded,
            "words": [e.to_dict() for e in self.entries],
            "recent": self.recent,
        }

    def _find(self, word: str) -> VocabEntry | None:
        key = _norm(word)
        for e in self._entries:
            if _norm(e.word) == key:
                return e
        return None

    # ---------------------------------------------------------- mutators

    def add_word(self, word: str, aliases: list[str] | None = None) -> VocabEntry:
        word = word.strip()
        if not word:
            raise ValueError("Word cannot be empty")
        self._load()
        with self._lock:
            entry = self._find(word)
            if entry is None:
                entry = VocabEntry(word=word)
                self._entries.append(entry)
            for a in aliases or []:
                self._add_alias_to(entry, a)
            self._save()
            return entry

    def _add_alias_to(self, entry: VocabEntry, alias: str) -> bool:
        alias = alias.strip()
        if not alias or _norm(alias) == _norm(entry.word):
            return False
        if any(_norm(a) == _norm(alias) for a in entry.aliases):
            return False
        entry.aliases.append(alias)
        return True

    def add_alias(self, wrong: str, right: str) -> VocabEntry:
        """Record that STT heard ``wrong`` when you said ``right``.

        Creates ``right`` as a vocab word if it doesn't exist yet.
        """
        self._load()
        with self._lock:
            entry = self._find(right) or self.add_word(right)
            self._add_alias_to(entry, wrong)
            self._save()
            return entry

    def remove_word(self, word: str) -> bool:
        self._load()
        with self._lock:
            entry = self._find(word)
            if entry is None:
                return False
            self._entries.remove(entry)
            self._save()
            return True

    def remove_alias(self, word: str, alias: str) -> bool:
        self._load()
        with self._lock:
            entry = self._find(word)
            if entry is None:
                return False
            before = len(entry.aliases)
            entry.aliases = [a for a in entry.aliases if _norm(a) != _norm(alias)]
            if len(entry.aliases) != before:
                self._save()
                return True
            return False

    def update_settings(self, *, auto_correct: bool | None = None,
                        learn_aliases: bool | None = None,
                        threshold: float | None = None) -> None:
        self._load()
        with self._lock:
            if auto_correct is not None:
                self.auto_correct = bool(auto_correct)
            if learn_aliases is not None:
                self.learn_aliases = bool(learn_aliases)
            if threshold is not None:
                self.threshold = max(0.5, min(1.0, float(threshold)))
            self._save()

    def set_onboarded(self, value: bool) -> None:
        self._load()
        with self._lock:
            self.onboarded = bool(value)
            self._save()

    def record_recent(self, original: str, corrected: str,
                      corrections: list[Correction], source: str) -> None:
        """Remember a transcript so the UI can offer "tap a word to fix it"."""
        self._load()
        with self._lock:
            self._recent.append({
                "ts": time.time(),
                "source": source,
                "original": original,
                "corrected": corrected,
                "corrections": [c.to_dict() for c in corrections],
            })
            self._recent = self._recent[-RECENT_LIMIT:]
            self._save()

    # ---------------------------------------------------------- whisper

    def whisper_prompt(self, max_words: int = 60) -> str | None:
        """Comma-separated vocab for faster-whisper's ``initial_prompt``.

        Whisper treats the prompt as preceding text, so listing the words
        biases the decoder toward those spellings. Kept short — the prompt
        eats into the 448-token context window.
        """
        # Whisper's prompt window is small (~224 tokens): prefer words that have
        # actually needed correcting, then the most recently added.
        ranked = sorted(self.entries, key=lambda e: (-e.hits, -e.added))
        words = [e.word for e in ranked[:max_words]]
        if not words:
            return None
        return "Names and words: " + ", ".join(words) + "."

    # ---------------------------------------------------------- correct

    def correct(self, transcript: str, *, learn: bool | None = None) -> tuple[str, list[Correction]]:
        """Apply alias + fuzzy corrections. Returns (fixed_text, corrections).

        Multi-word vocab entries ("Minchat Maariv") are matched against
        same-length token windows of the transcript.
        """
        self._load()
        if not transcript or not self._entries:
            return transcript, []
        learn = self.learn_aliases if learn is None else learn

        # Tokenise keeping the original spans so we can rebuild the sentence.
        tokens = [(m.group(0), m.start(), m.end())
                  for m in re.finditer(r"[^\s]+", transcript)]
        if not tokens:
            return transcript, []

        # Word part of each token (strip surrounding punctuation), normalised.
        def core(tok: str) -> tuple[str, str, str]:
            m = re.match(r"^([^\w֐-׿]*)(.*?)([^\w֐-׿]*)$", tok)
            return (m.group(1), m.group(2), m.group(3)) if m else ("", tok, "")

        with self._lock:
            entries = list(self._entries)

        # Longest entries first so "Minchat Maariv" beats "Maariv".
        entries.sort(key=lambda e: -len(e.word.split()))
        vocab_keys = {_norm(e.word) for e in entries}
        english = _english()

        replaced = [False] * len(tokens)
        out_tokens = [t[0] for t in tokens]
        corrections: list[Correction] = []
        dirty = False

        for entry in entries:
            n = len(entry.word.split())
            target = _norm(entry.word)
            alias_keys = {_norm(a) for a in entry.aliases}
            i = 0
            while i + n <= len(tokens):
                if any(replaced[i:i + n]):
                    i += 1
                    continue
                parts = [core(tokens[j][0]) for j in range(i, i + n)]
                window = " ".join(_norm(p[1]) for p in parts)
                if not window or window == target:
                    i += 1
                    continue

                reason, score = None, 0.0
                if window in alias_keys:
                    reason, score = "alias", 1.0
                elif (len(window) >= MIN_FUZZY_LEN and window not in _PROTECTED
                      and window not in vocab_keys                      # another known word
                      and not (n == 1 and window in english)            # a real English word
                      and abs(len(window) - len(target)) <= 2):
                    score = difflib.SequenceMatcher(None, window, target).ratio()
                    # Short targets need near-identity: "Tal"/"Talk", "Rei"/"Idol"…
                    thr = self.threshold + (0.08 if len(target) <= 5 else 0.04 if len(target) <= 7 else 0.0)
                    # First letter must agree — mishearings keep the onset far more often than not
                    if score >= thr and window[:1] == target[:1]:
                        reason = "fuzzy"

                if reason is None:
                    i += 1
                    continue

                # Preserve leading punct of first token and trailing punct of last.
                lead, _, _ = parts[0]
                _, _, trail = parts[-1]
                original_text = " ".join(p[1] for p in parts)
                out_tokens[i] = lead + entry.word + trail
                for j in range(i + 1, i + n):
                    out_tokens[j] = ""
                for j in range(i, i + n):
                    replaced[j] = True
                corrections.append(Correction(original_text, entry.word, reason, score))
                entry.hits += 1
                if learn and reason == "fuzzy" and score >= 0.9 and self._add_alias_to(entry, original_text):
                    logger.info("Vocab learned alias %r → %r", original_text, entry.word)
                dirty = True
                i += n

        if dirty:
            try:
                self._save()
            except Exception as e:
                logger.warning("Vocab save failed: %s", e)

        fixed = " ".join(t for t in out_tokens if t)
        return fixed, corrections


    # ---------------------------------------------------------- suggest

    def label_for(self, text: str) -> str:
        """The label implied by any of this user's own words in *text*.

        Checked before the generic keyword lists, because a word the user
        curated by hand outranks a word that ships with the app: "Haxaga" is a
        course because they said so, whatever else the sentence looks like.

        Longest word first, so "Modern Computer Vision" wins over a "vision"
        entry rather than depending on dictionary order.
        """
        self._load()
        if not text:
            return ""
        hay = " " + re.sub(r"[^\w\s'-]", " ", text.lower()) + " "
        with self._lock:
            labelled = [e for e in self._entries if e.label]
            for e in sorted(labelled, key=lambda x: -len(x.word)):
                needle = " " + e.word.lower() + " "
                if needle in hay:
                    return e.label
        return ""

    def acronyms(self) -> list[VocabEntry]:
        """Shorthand this user uses, longest first. Never substituted into
        their text — see VocabEntry — but worth telling the model about."""
        self._load()
        with self._lock:
            return sorted((e for e in self._entries if e.expands_to),
                          key=lambda x: -len(x.word))

    def expansion_note(self, text: str) -> str:
        """A one-line gloss of any shorthand in *text*, for the LLM prompt.

        "Chapter of MT" stays exactly that in the task; the model is simply
        told, alongside it, that MT means Mishnah Torah.
        """
        if not text:
            return ""
        hay = " " + re.sub(r"[^\w\s'-]", " ", text.lower()) + " "
        found = [e for e in self.acronyms() if " " + e.word.lower() + " " in hay]
        if not found:
            return ""
        return "Shorthand this user uses: " + ", ".join(
            f"{e.word} = {e.expands_to}" for e in found)

    def suggestions(self, transcript: str, floor: float = 0.6) -> list[dict[str, Any]]:
        """Words the user may want to check: near-misses of vocab words below
        the auto-correct threshold, plus capitalised mid-sentence tokens that
        aren't known (likely names Whisper guessed at)."""
        self._load()
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        tokens = re.findall(r"[^\s]+", transcript)
        with self._lock:
            entries = list(self._entries)
        known = {_norm(e.word) for e in entries} | {_norm(a) for e in entries for a in e.aliases}
        for i, tok in enumerate(tokens):
            core = re.sub(r"^[^\w֐-׿]+|[^\w֐-׿]+$", "", tok)
            key = _norm(core)
            if not key or key in seen or key in known or key in _PROTECTED or len(key) < MIN_FUZZY_LEN:
                continue
            best, best_score = None, 0.0
            for e in entries:
                if len(e.word.split()) != 1:
                    continue
                sc = difflib.SequenceMatcher(None, key, _norm(e.word)).ratio()
                if sc > best_score:
                    best, best_score = e.word, sc
            if best is not None and floor <= best_score < self.threshold + (0.05 if len(best) <= 4 else 0):
                out.append({"heard": core, "candidate": best, "score": round(best_score, 2), "reason": "near-miss"})
                seen.add(key)
            elif i > 0 and core[:1].isupper() and not core.isupper() and core.isalpha():
                out.append({"heard": core, "candidate": None, "score": 0.0, "reason": "unknown-name"})
                seen.add(key)
        return out[:6]


_store: VocabStore | None = None
_store_lock = threading.Lock()


def get_vocab() -> VocabStore:
    """Process-wide singleton."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = VocabStore()
    return _store


def apply_vocab(transcript: str, source: str = "mac") -> tuple[str, list[Correction]]:
    """Convenience: correct (if enabled) + record recent. Never raises."""
    try:
        store = get_vocab()
        if store.auto_correct:
            fixed, corrections = store.correct(transcript)
        else:
            fixed, corrections = transcript, []
        store.record_recent(transcript, fixed, corrections, source)
        if corrections:
            logger.info("Vocab corrections (%s): %s", source,
                        ", ".join(f"{c.original}→{c.replacement}" for c in corrections))
        return fixed, corrections
    except Exception as e:
        logger.warning("Vocab correction skipped: %s", e)
        return transcript, []
