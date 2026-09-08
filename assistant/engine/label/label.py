"""Step 7 — labels: event category/colour, task tag.

Contract (see DOCUMENTATION/ENGINE.md):
  reads   state.executed
  writes  item.labels, trace steps (VALIDATE)

The heavy lifting already lives where it belongs and is NOT duplicated here:
`assistant/actions/calendar/categories.py` categorises and colours every new
event as it is written (adjacent events never identical, hand-picked colours
never overridden), and `assistant/actions/todo/tagging.py` tags each task.
This stage reads the results back onto the items so the reply, the trace and
the audit can see what each item was labelled — and it is the seam where the
two-level hierarchy (row 58) will land when that work happens.
"""

from __future__ import annotations

from assistant.engine.state import EngineState


def run(state: EngineState, cfg) -> EngineState:
    from assistant.trace import VALIDATE

    by_id = {it.id: it for it in state.items}
    noted = []
    try:
        from assistant.db import get_db
        db = get_db()
        for ex in state.executed:
            if not ex.record:
                continue
            kind, row_id = ex.record[0], ex.record[1]
            item = by_id.get(ex.item_id)
            if item is None:
                continue
            if kind == "event":
                row = db.get_event(row_id)
                if row and row.get("category"):
                    item.labels["category"] = row["category"]
                    noted.append(f"{item.id}: {row['category']}")
            elif kind == "todo":
                row = db.get_todo(row_id)
                if row and row.get("tags"):
                    item.labels["tags"] = list(row["tags"])
                    noted.append(f"{item.id}: {', '.join(row['tags'])}")
    except Exception:
        pass   # labels are reporting, never worth failing a command over

    if state.trace and noted:
        state.trace.step(VALIDATE, "Labels", "; ".join(noted))
    return state
