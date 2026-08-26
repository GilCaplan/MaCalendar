"""Mine vocabulary candidates from text the user already has.

Sources:
  • WhatsApp chat exports (iOS/Android formats) — sender names + words
  • any pasted text (notes, a bio, emails)
  • the user's own calendar/todo titles (from the local DB)
  • a list of contact names (sent by the iOS app from the Contacts framework)

Everything runs locally and returns *candidates* with counts and a reason;
nothing is added until the user ticks it. Heuristics, not NLP: a word is a
candidate if it's in Hebrew script, is a WhatsApp sender, is capitalised
away from sentence start, or is a lowercase word that isn't in the system
English dictionary (transliterated Hebrew: "yalla", "bagrut", "beseder").
"""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import Any

# WhatsApp line formats:
#   [26/08/2026, 10:26:08] Rocky: message          (iOS)
#   26/08/2026, 10:26 - Rocky: message              (Android)
#   8/26/26, 10:26 AM - Rocky Caplan: message
_WA_LINE = re.compile(
    r"^\[?\d{1,2}[./]\d{1,2}[./]\d{2,4},? \d{1,2}:\d{2}(?::\d{2})?(?: ?[AP]M)?\]?\s*[-–]?\s*"
    r"(?P<sender>[^:\n]{1,40}?):\s(?P<msg>.*)$"
)
_SYSTEM_MSG = re.compile(r"(Messages and calls are end-to-end encrypted|created group|added|left|changed the subject|"
                         r"joined using this group|image omitted|video omitted|audio omitted|sticker omitted|"
                         r"document omitted|GIF omitted|<Media omitted>|This message was deleted|‎)", re.I)
_URL = re.compile(r"https?://\S+|www\.\S+")
_WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]{1,}|[֐-׿][֐-׿'\"״׳]{1,}")
_HEBREW = re.compile(r"[֐-׿]")

_STOP = set("""
i me my mine myself we our ours you your yours he him his she her hers it its they them their this that these those
am is are was were be been being have has had do does did will would shall should can could may might must
a an the and or but if then else so as of at by for from in into on onto out over to up with without about
after before during until while when where why how what which who whom whose not no yes ok okay lol haha hahaha
yeah yep nope hey hi hello bye thanks thank please sorry good great nice fine cool sure maybe just also very really
today tomorrow yesterday tonight morning afternoon evening night week month year time day days
monday tuesday wednesday thursday friday saturday sunday
january february march april may june july august september october november december
one two three four five six seven eight nine ten first second third
omitted media message deleted image video audio sticker document gif call missed voice
nah kinda gonna wanna gotta lemme dunno ya yea yeah kk omg ily ur pls plz thx tho tbh idk lmk btw rn omw ppl hrs mins
min sec jk ngl imo smh bruh bro dude yo yep nope noice oof ooof sheesh dayum dang hehe haha hahah lmao lmfao xd ofc
prob probs def deffo nvm ily tyty tysm cya ttyl gg ez sus fr frfr bet cap lowkey highkey vibe vibes mhm mhmm mmm hmm
ooo oooh aah ahh ugh meh eh oi aye yas yass whoo whooo woo yay yayyy nooo noooo pshh psshh pshhh
""".split())

_MIN_COUNT_LOWER = 2      # unknown lowercase words must repeat to count

# Hebrew function words / fillers that are never useful vocabulary
_HEBREW_STOP = set("""אני אתה את אתם אתן הוא היא הם הן אנחנו זה זאת זו אלה אלו לא כן של על עם מה יש אין גם רק כל אבל או
אם כי מי איך למה כמה איפה מתי עכשיו היום מחר אתמול טוב לי לך לו לה לנו לכם להם שלי שלך שלו שלה שלנו שלכם שלהם
אז אוקיי אוקי בסדר סבבה יאללה יופי נכון ככה כאן שם פה עוד כבר אולי בטח ממש יותר פחות הכי מאוד קצת הרבה
היה היתה היו יהיה תהיה בוא בואי בואו איזה אחד אחת שני שתי שלוש ארבע חמש שש שבע שמונה תשע עשר
מ ב ל ה ו ש כ""".split())

_CONTRACTIONS = ("'s", "'t", "'ll", "'re", "'ve", "'d", "'m", "n't")


def _is_english(word: str, words: set[str]) -> bool:
    """Dictionary check that survives real chat text: contractions,
    plurals, verb forms, comparatives. Conservative on purpose — if any
    plausible base form is English, the word is English."""
    w = word.lower().replace("’", "'").replace("‘", "'")
    if w in words:
        return True
    for suf in _CONTRACTIONS:
        if w.endswith(suf):
            base = w[: -len(suf)]
            if base in words or base + "n" in words:   # don't → do / don
                return True
    for suf, repl in (("ies", "y"), ("es", ""), ("s", ""), ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e"),
                      ("d", ""), ("er", ""), ("er", "e"), ("est", ""), ("ly", ""), ("ies", "ie")):
        if w.endswith(suf) and len(w) - len(suf) >= 3 and (w[: -len(suf)] + repl) in words:
            return True
    # doubled consonant before -ing/-ed: running → run
    for suf in ("ing", "ed"):
        if w.endswith(suf) and len(w) > len(suf) + 3 and w[-len(suf) - 1] == w[-len(suf) - 2] and w[: -len(suf) - 1] in words:
            return True
    return False
_MAX_CANDIDATES = 200


def _english_words() -> set[str]:
    """System dictionary (macOS/Linux) — used to spot non-English words."""
    for path in ("/usr/share/dict/words", "/usr/dict/words"):
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                return {w.strip().lower() for w in f if w.strip()}
        except OSError:
            continue
    return set()


_DICT: set[str] | None = None


def _dict() -> set[str]:
    global _DICT
    if _DICT is None:
        _DICT = _english_words()
    return _DICT


def _clean(word: str) -> str:
    return word.strip("'’\"-").strip()


_MOJIBAKE_HINT = re.compile(r"[âÃ×ð]")


def repair_encoding(text: str) -> str:
    """Undo UTF-8-read-as-Latin-1 mojibake (very common in WhatsApp exports
    opened on a Mac): 'donât' → 'don’t', '×©×××' → 'שלום'. No-op when the
    text is already clean."""
    if not _MOJIBAKE_HINT.search(text):
        return text
    try:
        fixed = text.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
    except Exception:
        return text
    # Accept only if it actually reduced the junk
    return fixed if len(_MOJIBAKE_HINT.findall(fixed)) < len(_MOJIBAKE_HINT.findall(text)) else text


_SENDER_JUNK = re.compile(r"[~>‎‏\u202a-\u202e]+|[“”\"'‘’][^“”\"'‘’]*[“”\"'‘’]")


def clean_sender(sender: str) -> str:
    """'~ Gil', '~>Gil~>', 'Ravid “the Cutie” Neeman' → 'Gil', 'Ravid Neeman'."""
    s = _SENDER_JUNK.sub(" ", sender)
    return re.sub(r"\s+", " ", s).strip()


def extract(text: str, known: set[str] | None = None) -> list[dict[str, Any]]:
    """Return ranked candidates: {word, count, reason, sample}."""
    text = repair_encoding(text)
    known = {k.lower() for k in (known or set())}
    words = _dict()
    senders: Counter[str] = Counter()
    hits: Counter[str] = Counter()
    reason: dict[str, str] = {}
    sample: dict[str, str] = {}
    midcap: dict[str, bool] = {}   # capitalised somewhere other than message start

    for raw in text.splitlines():
        line = raw.strip().lstrip("‎‏\u202a\u202c")
        if not line:
            continue
        m = _WA_LINE.match(line)
        if m:
            sender, msg = clean_sender(m.group("sender")), m.group("msg")
            if not _SYSTEM_MSG.search(msg) and not sender.lower().startswith("you"):
                senders[sender] += 1
            if _SYSTEM_MSG.search(msg):
                continue
        else:
            msg = line
        msg = _URL.sub(" ", msg)
        toks = _WORD.findall(msg)
        for i, tok in enumerate(toks):
            w = _clean(tok)
            if len(w) < 3 or w.lower() in _STOP or w.lower() in known:
                continue
            key = w.lower()
            if _HEBREW.search(w):
                if w in _HEBREW_STOP or len(w) < 3:
                    continue
                r = "hebrew"
            elif w[0].isupper() and not w.isupper():
                # Capitalised. Message-initial capitals are just sentence case —
                # only count them when the word is not English; mid-sentence
                # capitals are names/places regardless.
                if _is_english(w, words):
                    if i == 0:
                        continue
                    midcap[key] = True
                    r = "name"
                else:
                    r = "name"
                    if i > 0:
                        midcap[key] = True
            elif w.islower() and not _is_english(w, words):
                r = "non-english"
            else:
                continue
            hits[key] += 1
            # keep the most common surface form (prefer capitalised)
            if key not in reason or (r == "name" and reason[key] != "name"):
                reason[key] = r
            if key not in sample or (w[0].isupper() and not sample[key][0].isupper()):
                sample[key] = w

    out: list[dict[str, Any]] = []
    for s, c in senders.most_common():
        # first name only: "Rocky Caplan" → Rocky (full name kept as sample)
        first = _clean(s.split()[0]) if s.split() else s
        if len(first) >= 2 and first.lower() not in known and not _SYSTEM_MSG.search(first):
            out.append({"word": first, "count": c, "reason": "sender", "sample": s})
            known.add(first.lower())
    for key, c in hits.most_common():
        if key in known:
            continue
        r = reason[key]
        if r == "non-english" and c < _MIN_COUNT_LOWER:
            continue
        if r == "name" and key in words and not midcap.get(key):
            continue   # an English word only ever seen at message start
        if r == "name" and c < 2 and len(key) < 4:
            continue
        out.append({"word": sample[key], "count": c, "reason": r, "sample": ""})
        known.add(key)
        if len(out) >= _MAX_CANDIDATES:
            break
    return out


def from_calendar(known: set[str] | None = None) -> list[dict[str, Any]]:
    """Candidates mined from the user's own event/todo titles in the local DB."""
    try:
        from assistant.db import get_db
        db = get_db()
        with db._conn() as conn:  # noqa: SLF001 — read-only mining
            titles = [r[0] for r in conn.execute("SELECT title FROM events") if r[0]]
            titles += [r[0] for r in conn.execute("SELECT title FROM todos") if r[0]]
    except Exception:
        return []
    # Titles are short; treat each as one line so every word is "mid-sentence"
    text = "\n".join(". " + t for t in titles)
    return [c for c in extract(text, known) if c["reason"] != "sender"]


def from_names(names: list[str], known: set[str] | None = None) -> list[dict[str, Any]]:
    """Contact names from the phone → first names (+ distinctive surnames)."""
    known = {k.lower() for k in (known or set())}
    words = _dict()
    seen: set[str] = set()
    out = []
    for full in names:
        parts = [_clean(p) for p in re.split(r"[\s,]+", full) if _clean(p)]
        for i, p in enumerate(parts):
            key = p.lower()
            if len(p) < 2 or key in known or key in seen or key in _STOP:
                continue
            if i > 0 and key in words:      # skip surname-like ordinary words ("Baker")
                continue
            seen.add(key)
            out.append({"word": p, "count": 1, "reason": "contact", "sample": full})
    return out
