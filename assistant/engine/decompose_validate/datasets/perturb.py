"""Injected defects — the dataset for VALIDATE, built out of decompose's gold.

Validate's job is not to resolve; it is to notice that a completed item and the
words disagree, repair what it can prove, and flag what it cannot. So its dataset
cannot be "text -> values" like decompose's. It has to be:

    (a BROKEN item, the transcript)  ->  (the repaired item, or a flag)

which is exactly what the existing gold gives, once a defect is injected into it.
Each perturbation is a defect class validate is supposed to catch, taken from the
settled check table in PLAN.md §4c rather than invented here.

WHY CONTROL ROWS MATTER MOST
`kind="none"` leaves the item ALONE, and roughly a third of rows get it. Those are
the rows that measure the failure mode that actually matters: a repair rule which
damages an item that was already correct. Board G never sums "improved" with
"BROKE" for the same reason — a rule that fixes three items and breaks two has not
earned +1. Without control rows a rule that rewrites everything scores perfectly.

Deterministic: the kind is chosen by a stable hash of the row id, so a run is
reproducible and a fix can be compared against the same defects it faced before.
"""
from __future__ import annotations

import datetime as dt
import hashlib

#: Every defect class, and the check that is supposed to catch it. A kind is only
#: applied to an item it can actually break — `quantity_wrong` needs a quantity —
#: so `applicable()` filters first and the row falls back to a control otherwise.
KINDS = (
    "none",                    # control: validate must not touch this
    "date_shifted",            # date no longer matches the words
    "date_dropped",            # a clock with no day — completeness
    "clock_shifted",           # start_time no longer matches the words
    "clock_dropped",           # the words named a time and no value carries it
    "end_before_start",        # cross-field arithmetic
    "series_day_mismatch",     # weekly series starting on a day it never names
    "until_before_date",       # a series that ends before it begins
    "until_orphaned",          # recur_until with no recurrence
    "quantity_wrong",          # "5 apples" -> 3
    "lead_time_wrong",         # "half an hour before" -> 45
    "recurrence_wrong",        # cadence disagrees with the words
)

_WEEKDAY = ("monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday")


def applicable(item: dict, kind: str, anchor: "str | None" = None) -> bool:
    """Can this defect be injected into this item at all?

    "Can" means REPAIRABLE IN PRINCIPLE, not merely "the field exists". A defect
    with no evidence to recover it from is not a test of validate, it is a test of
    clairvoyance, and counting it as a failure would push validate toward guessing.
    """
    if kind == "none":
        return True
    if kind == "date_shifted":
        # A date equal to the anchor came from the FLOOR, which means the words
        # named no day at all. Shifting it produces an item validate cannot fix
        # and must not try to: with no day in the words, the value it holds is
        # the only information there is. Dropping such a date IS repairable —
        # the floor puts it back — so only the shift is excluded.
        return bool(item.get("date")) and item.get("date") != anchor
    if kind == "date_dropped":
        return bool(item.get("date"))
    if kind in ("clock_shifted", "clock_dropped"):
        return bool(item.get("start_time"))
    if kind == "end_before_start":
        return bool(item.get("start_time") and item.get("end_time"))
    if kind == "series_day_mismatch":
        return bool(item.get("recur_days")) and bool(item.get("date"))
    if kind == "until_before_date":
        return bool(item.get("recur_until") and item.get("date"))
    if kind == "until_orphaned":
        return bool(item.get("recur_until"))
    if kind == "quantity_wrong":
        return item.get("quantity") is not None
    if kind == "lead_time_wrong":
        return item.get("reminder_minutes") is not None
    if kind == "recurrence_wrong":
        return bool(item.get("recurrence"))
    return False


def _shift_clock(hhmm: str, hours: int) -> str:
    h, mi = (int(x) for x in hhmm.split(":"))
    return f"{(h + hours) % 24:02d}:{mi:02d}"


def perturb(item: dict, kind: str) -> dict:
    """One defect, injected. Returns a NEW item; the input is never mutated."""
    out = dict(item)
    if kind == "none":
        return out
    if kind == "date_shifted":
        out["date"] = (dt.date.fromisoformat(item["date"])
                       + dt.timedelta(days=3)).isoformat()
    elif kind == "date_dropped":
        out["date"] = None
    elif kind == "clock_shifted":
        out["start_time"] = _shift_clock(item["start_time"], 5)
    elif kind == "clock_dropped":
        out["start_time"] = None
        out["end_time"] = None
    elif kind == "end_before_start":
        out["end_time"] = _shift_clock(item["start_time"], -1)
    elif kind == "series_day_mismatch":
        # Move the start to a weekday the series never names.
        d = dt.date.fromisoformat(item["date"])
        days = item["recur_days"]
        for step in range(1, 8):
            cand = d + dt.timedelta(days=step)
            if _WEEKDAY[cand.weekday()] not in days:
                out["date"] = cand.isoformat()
                break
    elif kind == "until_before_date":
        out["recur_until"] = (dt.date.fromisoformat(item["date"])
                              - dt.timedelta(days=5)).isoformat()
    elif kind == "until_orphaned":
        out["recurrence"] = None
        out["recur_days"] = []
    elif kind == "quantity_wrong":
        out["quantity"] = int(item["quantity"]) + 2
    elif kind == "lead_time_wrong":
        out["reminder_minutes"] = int(item["reminder_minutes"]) + 17
    elif kind == "recurrence_wrong":
        out["recurrence"] = {"daily": "weekly", "weekly": "monthly",
                             "monthly": "daily"}[item["recurrence"]]
    return out


def kind_for(row_id: str, index: int, item: dict, control_share: float = 0.34,
             anchor: "str | None" = None) -> str:
    """Which defect this item gets — stable, and biased toward controls.

    A third of items are left alone deliberately (see the module docstring): the
    BROKE column is the one that catches a rule doing more harm than good, and it
    can only see items that started out correct.
    """
    seed = hashlib.sha256(f"{row_id}:{index}".encode()).hexdigest()
    if int(seed[:8], 16) / 0xFFFFFFFF < control_share:
        return "none"
    order = sorted(KINDS[1:], key=lambda k: hashlib.sha256(
        f"{seed}:{k}".encode()).hexdigest())
    for kind in order:
        if applicable(item, kind, anchor):
            return kind
    return "none"


def perturb_row(row: dict) -> "tuple[list, list]":
    """A gold row -> (broken items, the defect kind applied to each)."""
    broken, kinds = [], []
    for i, g in enumerate(row["gold"]):
        kind = kind_for(row["id"], i, g, anchor=row.get("today"))
        broken.append(perturb(g, kind))
        kinds.append(kind)
    return broken, kinds
