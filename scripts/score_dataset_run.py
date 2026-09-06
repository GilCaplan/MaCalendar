"""Score a dummy_<N>.db against what its history's compound prompts imply —
and, given two, diff them: what changed, per prompt and overall.

There is no hand-written ground truth for this dataset (unlike
scripts/audit_assistant.py's corpus, where every case has an `expect`). What
exists instead is free, deterministic ground truth from HOW each "complex"
prompt was built: fetch_hwu64_sample.py's _compose_complex joined two real
utterances of a known kind (event+event, task+task, event+task), so the
number of events/tasks a compound SHOULD produce is known without anyone
labelling it. "simple"/"medium" prompts are single real utterances — the
only deterministic claim there is "at least one thing happened."

That is the only thing scored as pass/fail here. Title/description/location
QUALITY has no ground truth to diff against — see garbage_titles below for
what's checked instead: not "is this a good title" (unanswerable), but "is
this obviously not one" (a stray connective word alone, e.g. "then" leaking
in from a compound's joining phrase — a real defect found in the first row
inspected while building this).

    python -m scripts.score_dataset_run output/dummy_1000.db
    python -m scripts.score_dataset_run output/dummy_1000.db --out report.md
    python -m scripts.score_dataset_run run_a/dummy_1000.db run_b/dummy_1000.db
        # ^ diff mode: what changed between two runs of the *same* history,
        # e.g. before/after a fix, or two different k values.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sqlite3
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXP_DIR = ROOT / "DOCUMENTATION" / "experiments" / "memory_scaling"
FIXTURE = EXP_DIR / "hwu64_sample.json"

#: A title that is ONE of these words and nothing else is not a title — it's
#: a connective from how a compound prompt was joined, leaking through.
_GARBAGE_TITLES = {"then", "and", "also", "and then", "so", "please", "now"}


def load_provenance(fixture_path: pathlib.Path = FIXTURE) -> dict[str, dict]:
    """transcript -> {scenario, intent, complexity} from the raw fetch record.

    Keyed by exact text, same as the dataset/history files use for their own
    verification against the pool — see build_memory_scaling_pool.slice_tiers.
    """
    data = json.loads(fixture_path.read_text())
    return {r["text"]: r for r in data["rows"]}


def _expected(intent: str) -> dict:
    """What a compound of this kind should produce. Absent for non-compounds."""
    return {
        "event+event": {"min_events": 2, "min_tasks": 0},
        "task+task": {"min_events": 0, "min_tasks": 2},
        "event+task": {"min_events": 1, "min_tasks": 1},
    }[intent]


OVERRIDES = ROOT / "dataset" / "inputs" / "convention_overrides.json"


def load_overrides(path: pathlib.Path = OVERRIDES) -> dict[str, dict]:
    """transcript -> {class, treatment} from the convention-overrides layer.

    Produced by scripts/audit_dataset_conventions.py: rows whose HWU-derived
    expectation disagrees with the product's own conventions (no list
    objects, no standing alerts, remind-to may be a task). Raw count_ok is
    never touched by these — they feed count_ok_adj only, so logged runs
    stay comparable."""
    if not path.exists():
        return {}
    return json.loads(path.read_text())["rows"]


def _score_row(transcript: str, actions_json: str, prov: dict | None,
               override: dict | None = None) -> dict:
    try:
        actions = json.loads(actions_json or "[]")
    except json.JSONDecodeError:
        actions = []

    n_events = sum(1 for a in actions if a.get("action", "").startswith("create_event"))
    task_titles: list[str] = []
    for a in actions:
        if a.get("action", "").startswith("create_todo"):
            titles = a.get("parameters", {}).get("titles") or []
            task_titles.extend(t for t in titles if isinstance(t, str))
    n_tasks = len(task_titles)

    garbage = [t for t in task_titles if t.strip().lower() in _GARBAGE_TITLES]
    # event titles are a single string per action, not a list
    event_titles = [a.get("parameters", {}).get("title", "") for a in actions
                    if a.get("action", "").startswith("create_event")]
    garbage += [t for t in event_titles if t.strip().lower() in _GARBAGE_TITLES]

    event_dt = [(a.get("parameters", {}).get("date"), a.get("parameters", {}).get("start_time"))
                for a in actions if a.get("action", "").startswith("create_event")]
    # Only a real signal with 2+ *distinctly requested* events and both dates
    # actually present — an event with no date at all isn't "collapsed", it's
    # missing a date, a different problem this doesn't try to catch.
    dates_collapsed = (len(event_dt) >= 2 and all(d and t for d, t in event_dt)
                        and len(set(event_dt)) == 1)

    row = {
        "transcript": transcript,
        "n_actions": len(actions),
        "n_events": n_events,
        "n_tasks": n_tasks,
        "garbage_titles": garbage,
        "event_dates_collapsed": dates_collapsed,
        "scenario": (prov or {}).get("scenario", "unknown"),
        "complexity": (prov or {}).get("complexity", "unknown"),
        "compound_kind": (prov or {}).get("intent") if (prov or {}).get("scenario") == "compound" else None,
    }
    if row["compound_kind"] == "event+task":
        missing = []
        if n_events == 0:
            missing.append("event")
        if n_tasks == 0:
            missing.append("task")
        row["missing_half"] = "+".join(missing) if missing else "none"

    intent = (prov or {}).get("intent", "")
    if row["compound_kind"] in ("event+event", "task+task", "event+task"):
        exp = _expected(row["compound_kind"])
        row["expected_min_events"] = exp["min_events"]
        row["expected_min_tasks"] = exp["min_tasks"]
        row["count_ok"] = n_events >= exp["min_events"] and n_tasks >= exp["min_tasks"]
    elif intent in ("set", "createoradd"):
        # A creation request: something should have been created. Against a
        # fresh scratch DB every time, so there's no ambiguity about which
        # record — there are none yet.
        row["expected_min_events"] = None
        row["expected_min_tasks"] = None
        row["count_ok"] = (n_events + n_tasks) >= 1
    elif intent in ("query", "remove"):
        # The opposite claim: nothing should have been CREATED in response to
        # "what's on my calendar" or "remove the meeting" — creating something
        # instead of querying/deleting is the real failure mode here. Whether
        # the query/delete itself succeeded isn't checked: against an empty
        # scratch DB a delete has nothing to find, and "I couldn't find that"
        # is the correct answer, not a failure — see actions.py's own
        # "guessing is destructive" rule for delete matching.
        row["expected_min_events"] = None
        row["expected_min_tasks"] = None
        row["count_ok"] = (n_events + n_tasks) == 0
    else:
        row["expected_min_events"] = None
        row["expected_min_tasks"] = None
        row["count_ok"] = None  # unknown provenance — not scored either way

    # --- product-adjusted verdict (count_ok_adj); raw count_ok above is
    # frozen for comparability with every logged run ---------------------
    n_mut = sum(1 for a in actions if a.get("action", "").startswith(
        ("delete_", "update_", "complete_")))
    row["n_mutations"] = n_mut
    adj = row["count_ok"]
    if intent == "query" and adj:
        # a query must not just avoid creating — it must not CHANGE anything
        adj = n_mut == 0
    total, clean = n_events + n_tasks, not garbage
    treatment = (override or {}).get("treatment")
    if treatment == "noop_ok":
        # an honest nothing is as correct as a sensible creation
        adj = (total == 0 and n_mut == 0) or (total >= 1 and clean)
    elif treatment == "half_flexible":
        # one half is something the product legitimately declines
        adj = total >= 1 and clean
    elif treatment == "split_flexible":
        # per-kind split came from source intents our conventions re-file
        adj = total >= 2
    row["count_ok_adj"] = adj
    row["override_class"] = (override or {}).get("class")

    return row


def score_db(db_path: pathlib.Path, provenance: dict[str, dict]) -> dict:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
        # Verbatim input, not the stored transcript: the pipeline may rewrite
        # the transcript before recording it, and provenance is keyed on what
        # the history file actually said.
        cols = {r[1] for r in c.execute("PRAGMA table_info(examples)")}
        if "tier_rank" in cols:
            rows = c.execute(
                "SELECT COALESCE(NULLIF(raw_transcript, ''), transcript), "
                "actions_json, parse_path, tier_rank, ts, llm_ms, total_ms "
                "FROM examples WHERE tier_rank IS NOT NULL ORDER BY tier_rank"
            ).fetchall()
        else:
            # archives from before the harness stamped tier_rank (the Sep 3-4
            # pre-loop runs); scoreable all the same, just unranked
            rows = c.execute(
                "SELECT COALESCE(NULLIF(raw_transcript, ''), transcript), "
                "actions_json, parse_path, NULL, ts, llm_ms, total_ms "
                "FROM examples ORDER BY id"
            ).fetchall()

    overrides = load_overrides()
    per_prompt = []
    for transcript, actions_json, parse_path, tier_rank, ts, llm_ms, total_ms in rows:
        r = _score_row(transcript, actions_json, provenance.get(transcript),
                       overrides.get(transcript))
        r.update({"tier_rank": tier_rank, "ts": ts, "parse_path": parse_path,
                  "llm_ms": llm_ms, "total_ms": total_ms})
        per_prompt.append(r)

    def _agg(rows_: list[dict]) -> dict:
        n = len(rows_)
        if not n:
            return {"n": 0}
        scored = [r for r in rows_ if r["count_ok"] is not None]
        adj = [r for r in rows_ if r.get("count_ok_adj") is not None]
        return {
            "n": n,
            "count_ok_rate": (sum(r["count_ok"] for r in scored) / len(scored)) if scored else None,
            "count_ok_adj_rate": (sum(r["count_ok_adj"] for r in adj) / len(adj)) if adj else None,
            "n_overridden": sum(1 for r in rows_ if r.get("override_class")),
            "query_mutation_violations": sum(
                1 for r in rows_ if r.get("n_mutations") and r["count_ok"] and
                r.get("count_ok_adj") is False and not r.get("override_class")),
            "garbage_title_rate": sum(1 for r in rows_ if r["garbage_titles"]) / n,
            "total_ms_p50": statistics.median(r["total_ms"] for r in rows_),
            "total_ms_p95": (sorted(r["total_ms"] for r in rows_)[int(n * .95)] if n > 1
                              else rows_[0]["total_ms"]),
            "parse_path": {p: sum(1 for r in rows_ if r["parse_path"] == p)
                            for p in sorted({r["parse_path"] for r in rows_})},
            "event_dates_collapsed_rate": (
                sum(r["event_dates_collapsed"] for r in rows_) / n),
            "count_ok_by_parse_path": {
                p: (sum(1 for r in rows_ if r["parse_path"] == p and r["count_ok"])
                    / max(1, sum(1 for r in rows_ if r["parse_path"] == p and r["count_ok"] is not None)))
                for p in sorted({r["parse_path"] for r in rows_})
            },
        }

    aggregate = {
        "overall": _agg(per_prompt),
        "by_complexity": {c: _agg([r for r in per_prompt if r["complexity"] == c])
                           for c in ("simple", "medium", "complex")},
        "by_compound_kind": {k: _agg([r for r in per_prompt if r["compound_kind"] == k])
                              for k in ("event+event", "task+task", "event+task")},
        "event_task_missing_half": {
            m: sum(1 for r in per_prompt if r.get("missing_half") == m)
            for m in ("none", "event", "task", "event+task")
        },
    }
    return {"db": str(db_path), "per_prompt": per_prompt, "aggregate": aggregate}


def compare(a: dict, b: dict) -> dict:
    """Per-prompt and aggregate diff between two score_db() results.

    Matched by transcript — meaningful only when both dbs came from
    overlapping histories (e.g. the same history_N.json run twice, or a
    smaller tier against a larger one it's nested inside).
    """
    by_text_a = {r["transcript"]: r for r in a["per_prompt"]}
    by_text_b = {r["transcript"]: r for r in b["per_prompt"]}
    shared = set(by_text_a) & set(by_text_b)

    flipped_better, flipped_worse, unchanged_fail, unchanged_pass = [], [], [], []
    for t in shared:
        ra, rb = by_text_a[t], by_text_b[t]
        if ra["count_ok"] == rb["count_ok"]:
            (unchanged_pass if ra["count_ok"] else unchanged_fail).append(t)
        elif rb["count_ok"] and not ra["count_ok"]:
            flipped_better.append(t)
        else:
            flipped_worse.append(t)

    return {
        "a_db": a["db"], "b_db": b["db"],
        "n_shared_prompts": len(shared),
        "n_a_only": len(set(by_text_a) - shared), "n_b_only": len(set(by_text_b) - shared),
        "count_ok_rate_a": a["aggregate"]["overall"].get("count_ok_rate"),
        "count_ok_rate_b": b["aggregate"]["overall"].get("count_ok_rate"),
        "flipped_better": flipped_better, "flipped_worse": flipped_worse,
        "n_unchanged_pass": len(unchanged_pass), "n_unchanged_fail": len(unchanged_fail),
    }


def _fmt_pct(x) -> str:
    return f"{x:.0%}" if isinstance(x, (int, float)) else "–"


def write_report(result: dict, comparison: dict | None, out_path: pathlib.Path) -> None:
    lines = [f"# Dataset run score — `{result['db']}`", ""]
    ov = result["aggregate"]["overall"]
    lines += [f"- product-adjusted count-correct **{_fmt_pct(ov.get('count_ok_adj_rate'))}** "
              f"({ov.get('n_overridden', 0)} overridden rows; raw below is the comparable number)"]
    lines += [f"- **{ov['n']} prompts** scored · count-correct **{_fmt_pct(ov.get('count_ok_rate'))}** · "
              f"garbage-title rate **{_fmt_pct(ov.get('garbage_title_rate'))}**",
              f"- total_ms p50 {ov.get('total_ms_p50', 0):.0f} · p95 {ov.get('total_ms_p95', 0):.0f}",
              f"- parse paths: {ov.get('parse_path', {})}", ""]
    lines += ["## By complexity", "", "| Tier | n | count-correct | garbage titles | total_ms p50 |",
              "|---|---:|---:|---:|---:|"]
    for tier, a in result["aggregate"]["by_complexity"].items():
        if a.get("n"):
            lines.append(f"| {tier} | {a['n']} | {_fmt_pct(a['count_ok_rate'])} | "
                         f"{_fmt_pct(a['garbage_title_rate'])} | {a['total_ms_p50']:.0f} |")
    lines += ["", "## By compound kind", "",
              "| Kind | n | count-correct | garbage titles | dates collapsed |", "|---|---:|---:|---:|---:|"]
    for kind, a in result["aggregate"]["by_compound_kind"].items():
        if a.get("n"):
            lines.append(f"| {kind} | {a['n']} | {_fmt_pct(a['count_ok_rate'])} | "
                         f"{_fmt_pct(a['garbage_title_rate'])} | {_fmt_pct(a['event_dates_collapsed_rate'])} |")

    mh = result["aggregate"]["event_task_missing_half"]
    lines += ["", "## event+task: which half goes missing when it fails", "",
              f"- both present: {mh['none']} · event missing: {mh['event']} · "
              f"task missing: {mh['task']} · both missing: {mh['event+task']}"]

    lines += ["", "## Correctness by parse path", "", "| Path | count-correct |", "|---|---:|"]
    for p, rate in ov.get("count_ok_by_parse_path", {}).items():
        lines.append(f"| {p} | {_fmt_pct(rate)} |")

    fails = [r for r in result["per_prompt"] if not r["count_ok"]]
    lines += ["", f"## Count-mismatch failures ({len(fails)})", ""]
    for r in fails[:30]:
        lines.append(f"- **{r['transcript'][:90]}** — {r['compound_kind'] or r['complexity']}: "
                     f"got {r['n_events']} events, {r['n_tasks']} tasks "
                     f"(wanted ≥{r['expected_min_events'] or 0}/≥{r['expected_min_tasks'] or 0})")

    if comparison:
        lines += ["", "## Comparison", "",
                  f"- {comparison['n_shared_prompts']} shared prompts "
                  f"({comparison['n_a_only']} only in A, {comparison['n_b_only']} only in B)",
                  f"- count-correct rate: {_fmt_pct(comparison['count_ok_rate_a'])} → "
                  f"{_fmt_pct(comparison['count_ok_rate_b'])}",
                  f"- **{len(comparison['flipped_worse'])} got worse**, "
                  f"**{len(comparison['flipped_better'])} got better**, "
                  f"{comparison['n_unchanged_pass']} still pass, {comparison['n_unchanged_fail']} still fail"]
        if comparison["flipped_worse"]:
            lines += ["", "### Got worse", ""] + [f"- {t[:100]}" for t in comparison["flipped_worse"][:20]]
        if comparison["flipped_better"]:
            lines += ["", "### Got better", ""] + [f"- {t[:100]}" for t in comparison["flipped_better"][:20]]

    out_path.write_text("\n".join(lines))
    print(f"wrote {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("db_a", type=pathlib.Path)
    ap.add_argument("db_b", type=pathlib.Path, nargs="?")
    ap.add_argument("--out", type=pathlib.Path, default=None)
    args = ap.parse_args()

    prov = load_provenance()
    result_a = score_db(args.db_a, prov)
    comparison = None
    if args.db_b:
        result_b = score_db(args.db_b, prov)
        comparison = compare(result_a, result_b)

    out = args.out or args.db_a.with_suffix(".score.md")
    write_report(result_a, comparison, out)


if __name__ == "__main__":
    main()
