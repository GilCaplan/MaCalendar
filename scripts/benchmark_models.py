"""Benchmark Ollama models on real voice commands: accuracy AND latency.

Runs each transcript through the *actual* IntentParser (same system prompt,
schema, and pydantic validation the app uses), compares the parsed intents
to the expected ones, and writes a Markdown report.

Usage:
    python -m scripts.benchmark_models                       # all models in MODELS that are pulled
    python -m scripts.benchmark_models --models llama3.1:8b qwen2.5:7b
    python -m scripts.benchmark_models --runs 2 --out DOCUMENTATION/MODEL_BENCHMARK.md
    python -m scripts.benchmark_models --memory              # also inject few-shot from memory

Scoring (per case):
    action match   — the sequence of action names is exactly right
    field match    — for each expected field, the parsed value equals it
                     (dates are compared after resolving relative expectations)
    exact          — action match AND all fields match
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assistant.config import load_config  # noqa: E402

MODELS = ["llama3.1:8b", "llama3.2:3b", "qwen2.5:7b", "qwen2.5:3b", "mistral:7b-instruct"]

TODAY = dt.date.today()


def _d(offset: int = 0) -> str:
    return (TODAY + dt.timedelta(days=offset)).isoformat()


def _next_weekday(wd: int) -> str:
    """Next occurrence of weekday wd (0=Mon) strictly after today."""
    days = (wd - TODAY.weekday()) % 7 or 7
    return _d(days)


# Real phrasings from NLU_TRACKING.md plus the failure from the phone today.
# expected: list of (action, {field: value}) — only fields listed are checked.
CASES = [
    ("walk Kyra the dog at 3:30 pm today and then go to Shaul for Minchat Maariv at 7:30 pm",
     [("create_event", {"date": _d(0), "start_time": "15:30"}),
      ("create_event", {"date": _d(0), "start_time": "19:30"})]),
    ("set a meeting for me tomorrow at 1 p.m. set another one at 4 p.m. and then pizza at 6:30 p.m. tomorrow",
     [("create_event", {"date": _d(1), "start_time": "13:00"}),
      ("create_event", {"date": _d(1), "start_time": "16:00"}),
      ("create_event", {"date": _d(1), "start_time": "18:30"})]),
    ("set a meeting for me next week on wednesday at 2pm with technion regarding project funds for ta costs",
     [("create_event", {"start_time": "14:00", "date": _next_weekday(2)})]),
    ("add on the 19th at 9 a.m. exam for eurovision course online",
     [("create_event", {"start_time": "09:00"})]),
    ("remind me to buy groceries and call the dentist",
     [("create_todo", {})]),
    ("move my 1pm meeting tomorrow to 3pm",
     [("update_event", {"new_start_time": "15:00"})]),
    ("delete the pizza party on friday",
     [("delete_event", {})]),
    ("what do I have on tomorrow",
     [("query_schedule", {})]),
    ("schedule gym every monday at 6 am",
     [("create_event", {"start_time": "06:00", "recurrence": "weekly"})]),
    ("lunch with Amichai at noon on thursday at edo's",
     [("create_event", {"start_time": "12:00", "date": _next_weekday(3)})]),
]


def load_history(path: str = "DOCUMENTATION/NLU_TRACKING.md", source: str | None = None):
    """Turn the NLU tracking log into benchmark cases.

    Ground truth per entry = the action sequence that ran + the start time of
    the first created/updated event (parsed from the result line). Titles and
    dates are NOT checked: titles in the log are often the rule parser's
    placeholder ('event'), and dates were relative to the day it was spoken.
    Only SUCCESS entries are used; note some of those were still wrong in
    practice (the log records what ran, not what the user wanted).
    """
    import re
    text = open(path, encoding="utf-8").read()
    cases = []
    for block in text.split("\n## ")[1:]:
        if "SUCCESS" not in block.split("\n", 1)[0]:
            continue
        if source and (("iOS" in block.split("\n", 1)[0]) != (source == "ios")):
            continue
        m_t = re.search(r"\*\*Transcript:\*\* `(.+?)`", block)
        m_a = re.search(r"\*\*Actions:\*\* ([\w, ]+)", block)
        if not m_t or not m_a:
            continue
        transcript = m_t.group(1).strip()
        actions = [a.strip() for a in m_a.group(1).split(",") if a.strip()]
        times = re.findall(r"from (\d{1,2}(?::\d{2})? ?[AP]M)", block)
        expected = []
        for i, a in enumerate(actions):
            fields = {}
            if a == "create_event" and i < len(times):
                t = dt.datetime.strptime(times[i].replace(" ", ""), "%I:%M%p" if ":" in times[i] else "%I%p")
                fields["start_time"] = t.strftime("%H:%M")
            expected.append((a, fields))
        cases.append((transcript, expected))
    return cases


def _pulled(base_url: str) -> set[str]:
    try:
        return {m["name"] for m in requests.get(f"{base_url}/api/tags", timeout=3).json()["models"]}
    except Exception:
        return set()


def _score(parsed, expected) -> dict:
    names = [n for n, _ in parsed]
    exp_names = [n for n, _ in expected]
    action_ok = names == exp_names
    checked = matched = 0
    for (en, ef), (pn, pi) in zip(expected, parsed if action_ok else [(None, None)] * len(expected)):
        for k, v in ef.items():
            checked += 1
            got = getattr(pi, k, None) if pi is not None else None
            if isinstance(got, dt.date):
                got = got.isoformat()
            if got is not None and str(got) == str(v):
                matched += 1
    return {"action_ok": action_ok, "fields_checked": checked, "fields_ok": matched,
            "exact": action_ok and checked == matched, "got": names}


def bench(model: str, runs: int, use_memory: bool, cfg) -> dict:
    from assistant.actions import ActionRegistry
    import assistant.actions.calendar, assistant.actions.todo, assistant.actions.clarify  # noqa
    from assistant.intent.parser import IntentParser

    cfg = cfg.model_copy(deep=True)
    cfg.ollama.model = model
    cfg.nlu.memory_examples = 4 if use_memory else 0
    # Unload whatever is resident so models don't stack up in RAM and skew latency
    try:
        for m in requests.get(f"{cfg.ollama.base_url}/api/ps", timeout=3).json().get("models", []):
            if m["name"] != model:
                requests.post(f"{cfg.ollama.base_url}/api/generate",
                              json={"model": m["name"], "keep_alive": 0}, timeout=30)
    except Exception:
        pass
    parser = IntentParser(cfg, ActionRegistry())
    parser.warm_up()

    rows = []
    for text, expected in CASES:
        lat, best = [], None
        for _ in range(runs):
            t0 = time.perf_counter()
            try:
                parsed = parser.parse(text)
                err = ""
            except Exception as e:
                parsed, err = [], f"{type(e).__name__}: {str(e)[:80]}"
            lat.append(time.perf_counter() - t0)
            sc = _score(parsed, expected)
            sc["error"] = err
            if best is None or (sc["exact"], sc["fields_ok"]) > (best["exact"], best["fields_ok"]):
                best = sc
        best["latency_s"] = statistics.median(lat)
        best["text"] = text
        rows.append(best)
        print(f"  {'✓' if best['exact'] else '✗'} {best['latency_s']:5.2f}s  {text[:60]}  → {best['got']}"
              + (f"  [{best['error']}]" if best["error"] else ""))

    n = len(rows)
    return {
        "model": model,
        "rows": rows,
        "exact": sum(r["exact"] for r in rows) / n,
        "action": sum(r["action_ok"] for r in rows) / n,
        "fields": (sum(r["fields_ok"] for r in rows) / max(1, sum(r["fields_checked"] for r in rows))),
        "p50": statistics.median(r["latency_s"] for r in rows),
        "max": max(r["latency_s"] for r in rows),
        "errors": sum(1 for r in rows if r["error"]),
    }


def write_report(results: list[dict], path: str, runs: int, use_memory: bool) -> None:
    lines = [
        "# LLM model benchmark — intent parsing",
        "",
        f"_Generated {dt.datetime.now():%Y-%m-%d %H:%M} · {len(CASES)} commands"
        f"{' (from NLU_TRACKING.md history; checks action + start time only)' if len(CASES) > 12 else ''}"
        f" · best of {runs} run(s) per command · "
        f"memory few-shot {'ON' if use_memory else 'OFF'} · machine: {os.uname().machine}_",
        "",
        "Re-run with `python -m scripts.benchmark_models` (see flags in the file header).",
        "",
        "## Summary",
        "",
        "| Model | Exact | Action | Fields | p50 latency | max latency | errors |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(results, key=lambda r: (-r["exact"], r["p50"])):
        lines.append(f"| `{r['model']}` | {r['exact']:.0%} | {r['action']:.0%} | {r['fields']:.0%} | "
                     f"{r['p50']:.2f} s | {r['max']:.2f} s | {r['errors']} |")
    lines += ["", "**Exact** = right actions *and* every checked field. **Action** = right action sequence. "
              "**Fields** = share of checked fields (date/time/recurrence) that were correct. "
              "Latency is the full parse call (prompt → validated intents) with the model kept warm.", ""]
    for r in results:
        lines += [f"## `{r['model']}`", "", "| ✓ | s | command | parsed as | notes |", "|---|---:|---|---|---|"]
        for row in r["rows"]:
            notes = row["error"] or ("" if row["exact"] else f"fields {row['fields_ok']}/{row['fields_checked']}")
            lines.append(f"| {'✓' if row['exact'] else '✗'} | {row['latency_s']:.2f} | {row['text']} | "
                         f"{', '.join(row['got']) or '—'} | {notes} |")
        lines.append("")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nReport written to {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--memory", action="store_true", help="inject few-shot examples from command memory")
    ap.add_argument("--out", default="DOCUMENTATION/MODEL_BENCHMARK.md")
    ap.add_argument("--history", action="store_true",
                    help="use every SUCCESS entry in DOCUMENTATION/NLU_TRACKING.md as the test set")
    args = ap.parse_args()
    if args.history:
        global CASES
        CASES = load_history()
        print(f"Loaded {len(CASES)} historical commands from NLU_TRACKING.md")

    cfg = load_config()
    pulled = _pulled(cfg.ollama.base_url)
    models = args.models or [m for m in MODELS if m in pulled]
    missing = [m for m in models if m not in pulled]
    if missing:
        print(f"Not pulled (skipping): {missing}  →  ollama pull <model>")
        models = [m for m in models if m in pulled]
    if not models:
        sys.exit("No models available. Is Ollama running?")

    results = []
    for m in models:
        print(f"\n=== {m} ===")
        results.append(bench(m, args.runs, args.memory, cfg))
        r = results[-1]
        print(f"  exact {r['exact']:.0%} · action {r['action']:.0%} · fields {r['fields']:.0%} · p50 {r['p50']:.2f}s")
    write_report(results, args.out, args.runs, args.memory)


if __name__ == "__main__":
    main()
