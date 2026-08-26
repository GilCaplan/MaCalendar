"""Command memory — a lightweight RAG layer that personalises the LLM parser.

Every voice command is stored with what it turned into (the executed intents)
and how it went. When the user later edits or deletes a record the assistant
created, that becomes feedback on the original example ("corrected" with the
final fields, or "rejected"). The most similar past examples are then injected
into the LLM prompt as few-shot demonstrations, so over time the model parses
*this* user's phrasing, names, and habits the way they actually meant them —
no fine-tuning required, and it works for any LLM backend.

Storage: ~/.assistant_tools/nlu_memory.db (own SQLite file, shared by the
Mac app and the iOS API server).
Retrieval: token-overlap + sequence similarity (stdlib only, sub-millisecond).
"""

from __future__ import annotations

import datetime as _dt
import difflib
import json
import logging
import os
import re
import sqlite3
import threading
import time
from typing import Any, Iterable

logger = logging.getLogger(__name__)

MEMORY_PATH = os.environ.get("MACALENDAR_MEMORY_DB") or os.path.expanduser("~/.assistant_tools/nlu_memory.db")

FEEDBACK_NONE = "none"
FEEDBACK_APPROVED = "approved"
FEEDBACK_CORRECTED = "corrected"
FEEDBACK_REJECTED = "rejected"
FEEDBACK_SKIPPED = "skipped"     # dismissed from the review list without a verdict

# How long after a voice command an edit/delete of the created record still
# counts as feedback on that command.
FEEDBACK_WINDOW_SEC = 24 * 3600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS examples (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL    NOT NULL,
    source        TEXT    NOT NULL DEFAULT 'mac',
    raw_transcript TEXT   NOT NULL DEFAULT '',
    transcript    TEXT    NOT NULL,
    parse_path    TEXT    NOT NULL DEFAULT '',
    actions_json  TEXT    NOT NULL DEFAULT '[]',
    result        TEXT    NOT NULL DEFAULT '',
    success       INTEGER NOT NULL DEFAULT 1,
    feedback      TEXT    NOT NULL DEFAULT 'none',
    correction_json TEXT,
    notes         TEXT    NOT NULL DEFAULT '',
    llm_ms        INTEGER NOT NULL DEFAULT 0,
    total_ms      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS example_records (
    example_id  INTEGER NOT NULL,
    record_type TEXT    NOT NULL,      -- 'event' | 'todo'
    record_id   INTEGER NOT NULL,
    action      TEXT    NOT NULL,
    PRIMARY KEY (example_id, record_type, record_id)
);
CREATE TABLE IF NOT EXISTS pending (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL    NOT NULL,
    source     TEXT    NOT NULL DEFAULT 'ios',
    transcript TEXT    NOT NULL,
    reason     TEXT    NOT NULL DEFAULT '',
    status     TEXT    NOT NULL DEFAULT 'pending',   -- pending | done | failed | dismissed
    attempts   INTEGER NOT NULL DEFAULT 0,
    result     TEXT    NOT NULL DEFAULT '',
    done_ts    REAL
);
CREATE INDEX IF NOT EXISTS idx_examples_ts ON examples(ts);
CREATE INDEX IF NOT EXISTS idx_records ON example_records(record_type, record_id);
"""

_STOP = {
    "a", "an", "the", "to", "for", "at", "on", "in", "of", "and", "then", "me",
    "my", "i", "please", "set", "add", "make", "create", "new", "up", "with",
    "it", "that", "this", "is", "be", "from", "by", "as", "so", "also", "next",
}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9֐-׿']+", text.lower()) if t not in _STOP and len(t) > 1}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9֐-׿' ]+", " ", text.lower())).strip()


def _mask_dates(params: Any) -> Any:
    """Drop absolute dates from example params so stale dates can't leak.

    Titles, times, lists, tags etc. are what personalise the parse; the
    date must always be resolved fresh relative to *today*. The date keys
    are REMOVED (not replaced with a placeholder) — a small model will
    happily copy a placeholder string into the real output.
    """
    if isinstance(params, dict):
        return {k: _mask_dates(v) for k, v in params.items()
                if not (isinstance(v, str) and _DATE_RE.match(v))}
    if isinstance(params, list):
        return [_mask_dates(v) for v in params]
    return params


class CommandMemory:
    def __init__(self, path: str = MEMORY_PATH) -> None:
        self._path = path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._path, timeout=5)
        c.row_factory = sqlite3.Row
        return c

    # ------------------------------------------------------------ writes

    def record(self, *, transcript: str, raw_transcript: str = "", source: str = "mac",
               parse_path: str = "", actions: Iterable[tuple[str, Any]] = (),
               result: str = "", success: bool = True, llm_ms: int = 0,
               total_ms: int = 0, records: Iterable[tuple[str, int, str]] = ()) -> int:
        """Store one command. ``actions`` = (action_name, intent|dict) pairs.

        ``records`` = (record_type, record_id, action) for rows the command
        created/changed — used to link later edits back as feedback.
        """
        acts = []
        for name, intent in actions:
            if hasattr(intent, "model_dump"):
                params = intent.model_dump(exclude_none=True, exclude_defaults=True)
            elif isinstance(intent, dict):
                params = intent
            else:
                params = {}
            acts.append({"action": name, "parameters": params})
        with self._lock, self._conn() as c:
            cur = c.execute(
                "INSERT INTO examples (ts, source, raw_transcript, transcript, parse_path, "
                "actions_json, result, success, llm_ms, total_ms) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (time.time(), source, raw_transcript or transcript, transcript, parse_path,
                 json.dumps(acts, ensure_ascii=False), result, int(success), llm_ms, total_ms),
            )
            ex_id = int(cur.lastrowid)
            for rtype, rid, action in records:
                c.execute("INSERT OR IGNORE INTO example_records VALUES (?,?,?,?)",
                          (ex_id, rtype, int(rid), action))
        return ex_id

    def set_feedback(self, example_id: int, feedback: str,
                     correction: dict | list | None = None, notes: str = "") -> bool:
        if feedback not in (FEEDBACK_NONE, FEEDBACK_APPROVED, FEEDBACK_CORRECTED, FEEDBACK_REJECTED):
            raise ValueError(f"bad feedback value {feedback!r}")
        with self._lock, self._conn() as c:
            cur = c.execute(
                "UPDATE examples SET feedback=?, correction_json=COALESCE(?, correction_json), "
                "notes=CASE WHEN ?='' THEN notes ELSE ? END WHERE id=?",
                (feedback, json.dumps(correction, ensure_ascii=False) if correction is not None else None,
                 notes, notes, example_id),
            )
            return cur.rowcount > 0

    def feedback_for_record(self, record_type: str, record_id: int, feedback: str,
                            changed_fields: dict | None = None) -> int | None:
        """Implicit feedback: the user edited/deleted a record a voice command made.

        Only applies when the command ran within FEEDBACK_WINDOW_SEC. For a
        'corrected' edit, the correction is the original action with the
        changed fields merged in — i.e. what the parse *should* have produced.
        Returns the example id that was updated, or None.
        """
        with self._lock, self._conn() as c:
            row = c.execute(
                "SELECT e.id, e.ts, e.actions_json, e.correction_json, r.action FROM example_records r "
                "JOIN examples e ON e.id = r.example_id "
                "WHERE r.record_type=? AND r.record_id=? ORDER BY e.ts DESC LIMIT 1",
                (record_type, int(record_id)),
            ).fetchone()
            if row is None or time.time() - row["ts"] > FEEDBACK_WINDOW_SEC:
                return None
            correction = None
            if feedback == FEEDBACK_CORRECTED:
                base = json.loads(row["correction_json"] or row["actions_json"])
                clean = {k: v for k, v in (changed_fields or {}).items()
                         if k not in ("color", "updated_at", "sync_dirty") and v is not None}
                if not clean:
                    return None
                for act in base:
                    if act.get("action") == row["action"]:
                        act.setdefault("parameters", {}).update(clean)
                correction = base
            c.execute(
                "UPDATE examples SET feedback=?, correction_json=COALESCE(?, correction_json) WHERE id=?",
                (feedback, json.dumps(correction, ensure_ascii=False) if correction else None, row["id"]),
            )
            logger.info("Memory feedback %s on example %s (%s #%s)", feedback, row["id"], record_type, record_id)
            return int(row["id"])

    def records_for(self, example_id: int) -> list[dict[str, Any]]:
        """(record_type, record_id, action) rows this command created/changed."""
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT record_type, record_id, action FROM example_records WHERE example_id = ?", (example_id,))]

    def skip_unreviewed(self) -> int:
        """Dismiss every command that still has no feedback (stale backlog)."""
        with self._lock, self._conn() as c:
            return c.execute("UPDATE examples SET feedback = ? WHERE feedback = ?",
                             (FEEDBACK_SKIPPED, FEEDBACK_NONE)).rowcount

    def delete(self, example_id: int) -> bool:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM example_records WHERE example_id=?", (example_id,))
            return c.execute("DELETE FROM examples WHERE id=?", (example_id,)).rowcount > 0

    # ------------------------------------------------------------- reads

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM examples ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get(self, example_id: int) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM examples WHERE id=?", (example_id,)).fetchone()
        return self._row_to_dict(r) if r else None

    def stats(self) -> dict[str, Any]:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM examples").fetchone()[0]
            by_fb = dict(c.execute("SELECT feedback, COUNT(*) FROM examples GROUP BY feedback").fetchall())
            by_path = dict(c.execute("SELECT parse_path, COUNT(*) FROM examples GROUP BY parse_path").fetchall())
            avg = c.execute("SELECT AVG(llm_ms), AVG(total_ms) FROM examples WHERE success=1").fetchone()
        return {"total": total, "feedback": by_fb, "parse_paths": by_path,
                "avg_llm_ms": int(avg[0] or 0), "avg_total_ms": int(avg[1] or 0)}

    @staticmethod
    def _row_to_dict(r: sqlite3.Row) -> dict[str, Any]:
        d = dict(r)
        d["actions"] = json.loads(d.pop("actions_json") or "[]")
        cj = d.pop("correction_json", None)
        d["correction"] = json.loads(cj) if cj else None
        d["success"] = bool(d["success"])
        d["time"] = _dt.datetime.fromtimestamp(d["ts"]).isoformat(timespec="seconds")
        return d

    # --------------------------------------------------------- retrieval

    def retrieve(self, transcript: str, k: int = 4, min_score: float = 0.25) -> list[dict[str, Any]]:
        """Most similar useful past examples for ``transcript``.

        Uses only successful, non-rejected examples. Corrected examples use
        the user's correction as the target and get a relevance bonus —
        that's the highest-value signal we have.
        """
        q_tokens = _tokens(transcript)
        q_norm = _norm(transcript)
        if not q_tokens:
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, ts, transcript, actions_json, correction_json, feedback FROM examples "
                "WHERE success=1 AND feedback != ? AND actions_json != '[]' "
                "ORDER BY ts DESC LIMIT 2000", (FEEDBACK_REJECTED,)).fetchall()
        scored: list[tuple[float, sqlite3.Row]] = []
        seen: set[str] = set()
        for r in rows:
            t_norm = _norm(r["transcript"])
            if t_norm == q_norm or t_norm in seen:
                # identical text → skip (it's *this* command, or a dup)
                continue
            t_tokens = _tokens(r["transcript"])
            if not t_tokens:
                continue
            jacc = len(q_tokens & t_tokens) / len(q_tokens | t_tokens)
            seq = difflib.SequenceMatcher(None, q_norm, t_norm).ratio()
            score = 0.6 * jacc + 0.4 * seq
            if r["feedback"] == FEEDBACK_CORRECTED:
                score += 0.15
            elif r["feedback"] == FEEDBACK_APPROVED:
                score += 0.05
            if score >= min_score:
                seen.add(t_norm)
                scored.append((score, r))
        scored.sort(key=lambda x: -x[0])
        out = []
        for score, r in scored[:k]:
            target = json.loads(r["correction_json"] or r["actions_json"])
            out.append({"id": r["id"], "score": round(score, 3), "transcript": r["transcript"],
                        "actions": target, "feedback": r["feedback"]})
        return out

    def few_shot_block(self, transcript: str, k: int = 4) -> str:
        """Prompt text with the k best examples, or '' if none are relevant."""
        examples = self.retrieve(transcript, k=k)
        if not examples:
            return ""
        lines = [
            "USER HISTORY — how this user's past commands were (correctly) interpreted.",
            "Match their phrasing, names and habits. Dates were removed from these examples "
            "on purpose — always resolve dates fresh from today's date table above.",
        ]
        for ex in examples:
            tag = " (user-corrected)" if ex["feedback"] == FEEDBACK_CORRECTED else ""
            acts = json.dumps({"actions": _mask_dates(ex["actions"])}, ensure_ascii=False)
            lines.append(f'- "{ex["transcript"]}"{tag} → {acts}')
        return "\n".join(lines)


    # ------------------------------------------------------------ pending

    def add_pending(self, transcript: str, reason: str, source: str = "ios") -> int:
        with self._lock, self._conn() as c:
            dup = c.execute("SELECT id FROM pending WHERE status='pending' AND transcript=?",
                            (transcript,)).fetchone()
            if dup:
                return int(dup["id"])
            cur = c.execute("INSERT INTO pending (ts, source, transcript, reason) VALUES (?,?,?,?)",
                            (time.time(), source, transcript, reason))
            return int(cur.lastrowid)

    def pending(self, include_done: bool = False) -> list[dict[str, Any]]:
        with self._conn() as c:
            q = "SELECT * FROM pending" + ("" if include_done else " WHERE status='pending'") + " ORDER BY ts"
            return [dict(r) | {"time": _dt.datetime.fromtimestamp(r["ts"]).isoformat(timespec="seconds")}
                    for r in c.execute(q).fetchall()]

    def get_pending(self, pending_id: int) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM pending WHERE id=?", (pending_id,)).fetchone()
            return dict(r) if r else None

    def resolve_pending(self, pending_id: int, status: str, result: str = "") -> None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE pending SET status=?, result=?, done_ts=?, attempts=attempts+1 WHERE id=?",
                      (status, result, time.time(), pending_id))

    def bump_pending(self, pending_id: int) -> None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE pending SET attempts=attempts+1 WHERE id=?", (pending_id,))


_memory: CommandMemory | None = None
_memory_lock = threading.Lock()


def get_memory() -> CommandMemory:
    global _memory
    if _memory is None:
        with _memory_lock:
            if _memory is None:
                _memory = CommandMemory()
    return _memory
