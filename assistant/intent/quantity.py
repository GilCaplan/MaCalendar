"""How many of a thing, when the thing is said once.

"buy pasta times 5" is one task for five packets of pasta. Both parse paths got
it wrong in the same way and for the same reason — neither had any notion of a
quantity, so the only way either could represent "five" was five tasks:

    create_todo(titles=['buy pasta', 'buy pasta', 'buy pasta',
                        'buy pasta', 'buy pasta'])

Five identical rows are worse than merely untidy. Ticking one off tells you
nothing about which of the five it was, so the list stops being a record of
what is left to do.

Two jobs here. `split_quantity` reads a count out of one title, and
`collapse_repeats` folds a run of identical titles back into one — the LLM keeps
emitting those, and no amount of prompt wording has stopped it reliably.

Deliberately conservative. A false positive silently changes what the user
asked for, so a count is only read when it is unambiguous:

  * an explicit multiplier, anywhere — "x5", "5x", "times 5", "×5";
  * a leading count, but only after a verb that implies buying a quantity of
    something ("buy 5 apples", never "call 911").

Counts outside 2-99 are ignored: 1 is the default and means nothing, and three
digits is far more likely a phone number, a house number, or a year.
"""

from __future__ import annotations

import re

MAX_QUANTITY = 99

# Verbs after which a bare number is a count of the thing, not part of its name.
# "buy 5 apples" is five apples; "call 5 people" is not something we guess at.
_PURCHASE_VERBS = frozenset({
    "buy", "get", "grab", "order", "pick", "collect", "purchase", "bring",
})

_NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "dozen": 12, "fifteen": 15, "twenty": 20,
}
_NUM = r"(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")"

# "pasta x5", "pasta × 5", "pasta times five"
_TRAILING = re.compile(rf"\s*[,\-–—]?\s*(?:[x×*]\s*|times\s+){_NUM}\s*$", re.IGNORECASE)
# "x5 pasta", "5x pasta"
_LEADING_MULT = re.compile(rf"^\s*(?:[x×]\s*{_NUM}|{_NUM}\s*[x×])\s+", re.IGNORECASE)
# "buy 5 apples" — the verb is kept, the count is not
_LEADING_COUNT = re.compile(rf"^(\w+(?:\s+up)?)\s+(?:an?\s+)?{_NUM}\s+(?=\S)", re.IGNORECASE)


def _as_int(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        n = int(token)
    else:
        n = _NUMBER_WORDS.get(token, 0)
    return n if 2 <= n <= MAX_QUANTITY else None


def split_quantity(title: str) -> tuple[str, int]:
    """Return the title with any count removed, and the count (1 if none)."""
    text = (title or "").strip()
    if not text:
        return text, 1

    m = _TRAILING.search(text)
    if m and (n := _as_int(m.group(1))):
        return _tidy(text[: m.start()]) or text, n

    m = _LEADING_MULT.match(text)
    if m and (n := _as_int(m.group(1) or m.group(2))):
        return _tidy(text[m.end():]) or text, n

    m = _LEADING_COUNT.match(text)
    if m and m.group(1).lower() in _PURCHASE_VERBS and (n := _as_int(m.group(2))):
        return _tidy(f"{m.group(1)} {text[m.end():]}") or text, n

    return text, 1


def _tidy(part: str) -> str:
    """Trim the punctuation a removed count leaves behind."""
    return re.sub(r"\s{2,}", " ", part).strip(" ,-–—\t")


def collapse_repeats(titles: list[str]) -> tuple[list[str], list[int]]:
    """Fold identical titles into one, counting them.

    Order is the order each title was *first* seen, so "milk, bread, milk"
    stays milk-then-bread rather than being re-sorted. Comparison ignores case
    and surrounding space; the first spelling seen is the one kept.
    """
    order: list[str] = []
    counts: dict[str, int] = {}
    seen: dict[str, str] = {}
    for raw in titles:
        clean, qty = split_quantity(raw)
        key = clean.strip().lower()
        if not key:
            continue
        if key not in seen:
            seen[key] = clean
            order.append(key)
            counts[key] = 0
        counts[key] += qty
    return ([seen[k] for k in order],
            [min(counts[k], MAX_QUANTITY) for k in order])
