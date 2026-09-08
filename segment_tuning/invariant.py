"""The no-loss / no-invention invariant — ONE definition, used everywhere.

    tokens(action) u tokens(time)  covers every content token of the item
                                   and contains nothing that is not in `text`

It is the dataset's metric, the generator's validator and the runtime guard in
`llmseg.accept`, and it has to be the same function in all three. When it was
three copies, the copies disagreed: the guard rejected a model answer for
defaulting an untimed item to "today" — which is what SPEC.md tells it to do —
while the generator's copy dropped 47 template families for the same reason.

A token MAY appear in more than one item; that is what a shared modifier is.
"""
from __future__ import annotations

import re

#: Function words carry no content, so losing one is not losing information.
#: The joiners are here too: "buy milk and eggs" splits on "and", and no item
#: should have to keep it to satisfy the check.
_STOP = frozenset(
    "a an the and or then also plus as well to of for on at in by with my me "
    "i please can you it that this".split()
    # Disfluencies. Dropping "um" is not losing information, and counting it as
    # loss made 35 of the 66 content-loss rows noise — which would have sent
    # the next cycle chasing a splitter bug that does not exist.
    + "um uh er hmm yeah yep okay ok so like oh".split())

#: SPEC.md: "an item with no time reference at all gets today". The default is
#: therefore a legal value that is NOT expected to appear in the text, and the
#: check must not treat it as an invention. Every other word still must be
#: grounded — this is one named exemption, not a general amnesty.
DEFAULT_TIME = "today"


def content(s: str) -> "set[str]":
    return {w for w in re.findall(r"[a-z0-9']+", (s or "").lower())
            if w not in _STOP}


def violations(text: str, items: "list[dict]") -> "list[str]":
    """Empty list means the decomposition is faithful to `text`."""
    src = content(text)
    out: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(items, 1):
        got = content(item.get("action", "")) | content(item.get("time", ""))
        # The date floor is exempt wherever it appears, not only when it is the
        # whole field: SPEC floors a clock-only item to "today at 7", so an
        # exemption keyed on `time == "today"` still called that an invention
        # and cost 15 template families. When the speaker DID say "today" the
        # word is in `src` anyway, so this cannot hide a real loss.
        if DEFAULT_TIME not in src:
            got -= {DEFAULT_TIME}
        invented = got - src
        if invented:
            out.append(f"item {i} invented {sorted(invented)}")
        seen |= got
    missing = src - seen
    if missing:
        out.append(f"lost {sorted(missing)}")
    return out
