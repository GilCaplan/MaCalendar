#!/usr/bin/env python3
"""Collapse duplicate tasks that a token-less client stacked into the list.

Between 2026-08-31 and 2026-09-07 the unit suite's HUD-revert click POSTed
`{"title": "buy groceries"}` to the RUNNING api on every `pytest tests/unit`
run, and 45 copies of one task accumulated in the real Today list. The leak is
closed (tests/conftest.py refuses the live API; POST /todos folds a token-less
repeat of an open task). This tidies up what it already made.

    python -m scripts.dedup_todos                 # dry run — prints the plan
    python -m scripts.dedup_todos --apply         # back up, then delete
    python -m scripts.dedup_todos --title "buy groceries"   # one task only
    python -m scripts.dedup_todos --include-completed       # also collapse
                                                            # completed clusters

A cluster is the rows sharing one normalised title (case- and spacing-
insensitive) in one list with one completed state. **The oldest row of each
cluster survives** — it is the one the person actually asked for, and it holds
the original created_at and list position; the later copies are the accidents.
A row carrying notes, a due date, a non-default priority or tags the survivor
lacks is never deleted: it is reported and left alone, because the duplicate
may have been edited into something real.

Nothing is written without `--apply`, and `--apply` copies the database file
first (`<db>.dedup-backup-<timestamp>`).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import sqlite3
import sys


def _db_path() -> str:
    env = os.environ.get("MACALENDAR_DB")
    if env:
        return env
    return os.path.expanduser("~/.assistant_tools/calendar.db")


def _norm(title: str) -> str:
    return " ".join((title or "").split()).lower()


def _distinct_content(row: dict) -> dict:
    """The fields that would make a duplicate worth keeping on its own.

    Tags are deliberately not among them: POST /todos infers a tag from the
    title when the client sends none, so every machine-made copy of
    "buy groceries" carries ["Groceries"] without anyone having chosen it.
    Notes, a due date and a non-default priority only ever get there by hand.
    """
    return {"notes": (row.get("notes") or "").strip(),
            "due_date": (row.get("due_date") or "").strip(),
            "priority": (row.get("priority") or "none")}


def _tags(row: dict) -> list:
    try:
        return sorted(json.loads(row.get("tags") or "[]"))
    except ValueError:
        return []


def _clusters(conn: sqlite3.Connection, title_filter: str | None,
              include_completed: bool) -> list:
    conn.row_factory = sqlite3.Row
    where = "" if include_completed else " WHERE completed = 0"
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM todos{where} ORDER BY id").fetchall()]
    if title_filter:
        key = _norm(title_filter)
        rows = [r for r in rows if _norm(r["title"]) == key]
    buckets: dict = {}
    for r in rows:
        buckets.setdefault((_norm(r["title"]), r["list"], r["completed"]), []).append(r)
    return [(k, v) for k, v in buckets.items() if len(v) > 1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually delete (default: print the plan and exit)")
    ap.add_argument("--title", default=None,
                    help="only collapse clusters of this task title")
    ap.add_argument("--include-completed", action="store_true",
                    help="also collapse clusters of completed tasks")
    ap.add_argument("--db", default=None, help="database file (default: the real one)")
    args = ap.parse_args(argv)

    path = args.db or _db_path()
    if not os.path.exists(path):
        print(f"No database at {path}", file=sys.stderr)
        return 2
    print(f"database: {path}")

    # Read-only for the survey, always: a dry run must not so much as touch the
    # file it is reporting on (a plain connect would create -wal/-shm beside it).
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        clusters = _clusters(conn, args.title, args.include_completed)
    finally:
        conn.close()

    if not clusters:
        print("No duplicate clusters found — nothing to do.")
        return 0

    doomed: list = []
    kept_rows: list = []
    skipped: list = []
    for (title, list_name, completed), rows in sorted(clusters):
        rows.sort(key=lambda r: (r["created_at"], r["id"]))
        survivor, copies = rows[0], rows[1:]
        base = _distinct_content(survivor)
        state = "completed" if completed else "open"
        print(f"\n{title!r} in {list_name!r} ({state}) — {len(rows)} rows")
        print(f"  KEEP   #{survivor['id']:<5} created {survivor['created_at']}")
        kept_rows.append(survivor["id"])
        for r in copies:
            if _distinct_content(r) != base:
                skipped.append(r["id"])
                print(f"  skip   #{r['id']:<5} created {r['created_at']}"
                      f"  — has its own notes/due date/priority, left alone")
            else:
                doomed.append(r["id"])
                extra = ""
                if _tags(r) != _tags(survivor):
                    extra = f"  (tags {_tags(r)} -> survivor has {_tags(survivor)})"
                print(f"  DELETE #{r['id']:<5} created {r['created_at']}{extra}")

    print(f"\n{len(doomed)} row(s) to delete, {len(kept_rows)} kept"
          + (f", {len(skipped)} skipped as edited" if skipped else ""))
    if not doomed:
        return 0

    ids = ",".join(str(i) for i in doomed)
    print(f"\nSQL: DELETE FROM todos WHERE id IN ({ids});")

    if not args.apply:
        print("\nDry run — nothing written. Re-run with --apply to do it.")
        return 0

    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{path}.dedup-backup-{stamp}"
    shutil.copyfile(path, backup)
    print(f"\nbacked up to {backup}")

    conn = sqlite3.connect(path)
    try:
        with conn:
            cur = conn.execute(f"DELETE FROM todos WHERE id IN ({ids})")
        print(f"deleted {cur.rowcount} row(s).")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
