"""Weekly review of how the assistant is doing, from the command memory.

Reads ~/.assistant_tools/nlu_memory.db (every voice command, what it did,
your 👍/👎/edits) and vocab.json, and prints/writes a short report:
volume, parse-path mix, latency, feedback rates, the commands you marked
wrong, corrections you made, vocab words that fired, and what's still
unreviewed. Run it after a week of real use:

    python -m scripts.weekly_review                 # last 7 days, prints
    python -m scripts.weekly_review --days 14
    python -m scripts.weekly_review --out DOCUMENTATION/WEEKLY_REVIEW.md
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assistant.intent.memory import get_memory  # noqa: E402
from assistant.stt.vocab import get_vocab       # noqa: E402


def pct(v, q):
    if not v:
        return 0
    v = sorted(v); k = (len(v) - 1) * q; f = int(k); c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


# A person cannot read a command, decide, and click in under this. Verdicts
# arriving faster than this in a group are clearing a queue, not judging it.
BULK_WINDOW_S = 3.0
BULK_MIN = 5

# Below this many approvals the accuracy ratio is dominated by whether the
# thumbs-up gets used, so it is not reported.
MIN_APPROVALS = 3


def _drop_bulk_runs(rows):
    """Split rows into (considered, bulk-marked).

    Looks for runs of verdicts whose timestamps are packed tighter than a human
    could produce. Only actual verdicts count — "none" is unreviewed and never
    part of a burst.
    """
    verdicts = sorted((r for r in rows if r["feedback"] in ("approved", "corrected", "rejected")),
                      key=lambda r: r["ts"])
    bulk_ids, run = set(), []

    def _flush():
        if len(run) >= BULK_MIN:
            bulk_ids.update(id(r) for r in run)

    for r in verdicts:
        if run and r["ts"] - run[0]["ts"] <= BULK_WINDOW_S:
            run.append(r)
        else:
            _flush()
            run = [r]
    _flush()

    considered = [r for r in rows if id(r) not in bulk_ids]
    bulk = [r for r in rows if id(r) in bulk_ids]
    return considered, bulk


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out")
    args = ap.parse_args()

    mem = get_memory(); vocab = get_vocab()
    since = time.time() - args.days * 86400
    rows = [r for r in mem.recent(5000) if r["ts"] >= since]
    L = []
    L.append(f"# Assistant weekly review — last {args.days} days (to {dt.date.today()})\n")
    if not rows:
        L.append("No commands recorded in this window. Use the assistant for a few days, then re-run.")
    else:
        n = len(rows)
        by_src = collections.Counter(r["source"] for r in rows)
        by_path = collections.Counter(r["parse_path"] or "?" for r in rows)
        ok = [r for r in rows if r["success"]]
        fb = collections.Counter(r["feedback"] for r in rows)
        reviewed = n - fb.get("none", 0)
        L += [
            f"- **{n} commands** ({', '.join(f'{k} {v}' for k, v in by_src.items())}) · {len(ok)} executed, {n - len(ok)} failed",
            f"- Parse paths: " + ", ".join(f"{k} {v} ({v / n:.0%})" for k, v in by_path.most_common()),
            f"- Latency (executed): first result p50 {pct([r['total_ms'] for r in ok], .5) / 1000:.1f} s · p95 {pct([r['total_ms'] for r in ok], .95) / 1000:.1f} s · "
            f"LLM-path only p50 {pct([r['llm_ms'] for r in ok if r['llm_ms']], .5) / 1000:.1f} s",
            f"- **Feedback:** {reviewed}/{n} reviewed — 👍 {fb.get('approved', 0)} · ✏️ corrected {fb.get('corrected', 0)} · 👎 rejected {fb.get('rejected', 0)} · unreviewed {fb.get('none', 0)}",
        ]
        # Judgements made faster than a person can read the command are not
        # judgements. Clearing a backlog of 24 in two seconds registered as 24
        # considered rejections and dragged the headline to 9%, which is a
        # number about a review session rather than about the assistant.
        judged, bulk = _drop_bulk_runs(rows)
        if bulk:
            L.append(
                f"- Ignoring {len(bulk)} verdict(s) marked in bursts of "
                f"{BULK_MIN} or more within {BULK_WINDOW_S}s — too fast to be "
                f"read, so counted as clearing a backlog rather than judging it."
            )
        jfb = collections.Counter(r["feedback"] for r in judged)
        good = jfb.get("approved", 0)
        bad = jfb.get("corrected", 0) + jfb.get("rejected", 0)
        # Flag rate is always reportable: it counts things you actively marked.
        if judged:
            L.append(f"- **Flagged wrong or corrected: {bad}/{len(judged)} commands** "
                     f"({bad / len(judged):.0%} of everything run this period)")

        # Accuracy is a ratio, and a ratio needs both halves. A thumbs-up is
        # work with no reward — a correct answer is its own confirmation — so
        # approvals go unpressed while mistakes get flagged. With none of them
        # the formula reads 0% no matter how the assistant actually did, which
        # says something about the button rather than the parser. Report the
        # number only when there is enough positive signal to divide by.
        if good >= MIN_APPROVALS:
            L.append(f"- **Accuracy on reviewed commands: {good / (good + bad):.0%}** "
                     f"({good}/{good + bad} — approved ÷ approved+corrected+rejected)")
            by_path_ok = collections.defaultdict(lambda: [0, 0])
            for r in judged:
                if r["feedback"] == "approved": by_path_ok[r["parse_path"]][0] += 1
                elif r["feedback"] in ("corrected", "rejected"): by_path_ok[r["parse_path"]][1] += 1
            L.append("  - by path: " + ", ".join(f"{p} {g}/{g + b} ({g / max(1, g + b):.0%})" for p, (g, b) in by_path_ok.items()))
        elif bad:
            L.append(f"- **Accuracy: not computable.** Only {good} approval(s) this period "
                     f"against {bad} flagged, so the ratio would measure how often 👍 gets "
                     f"pressed, not how often the assistant is right. Use the flag rate "
                     f"above, or `python -m scripts.audit_assistant` for a measured number.")
        else:
            L.append("- **Accuracy: no considered feedback this period.**")

        wrong = [r for r in rows if r["feedback"] in ("rejected", "corrected")]
        if wrong:
            L.append("\n## Marked wrong / corrected\n")
            for r in wrong[:30]:
                L.append(f"- [{r['parse_path']}] “{r['transcript']}” → {[a['action'] for a in r['actions']]}"
                         + (f" — corrected to {[a['action'] for a in r['correction']]} {[a.get('parameters', {}) for a in r['correction']][:1]}" if r.get("correction") else ""))
        failed = [r for r in rows if not r["success"]]
        if failed:
            L.append("\n## Failed outright\n")
            for r in failed[:20]:
                L.append(f"- “{r['transcript']}” — {r['result'][:120]}")
        pend = mem.pending(include_done=True)
        pend = [p for p in pend if p["ts"] >= since]
        if pend:
            L.append(f"\n## Queued because the LLM was offline: {len(pend)} ({sum(1 for p in pend if p['status'] == 'done')} later completed)")

    # vocabulary
    hits = sorted((e for e in vocab.entries if e.hits), key=lambda e: -e.hits)
    L.append(f"\n## Vocabulary ({len(vocab.entries)} words)\n")
    if hits:
        L.append("Words that corrected a transcript this period (all time counts): " + ", ".join(f"{e.word} ×{e.hits}" for e in hits[:25]))
    recent_fix = [r for r in vocab.recent if r.get("corrections")]
    if recent_fix:
        L.append("\nRecent auto-corrections (check these are right — a wrong one means a bad alias to remove):")
        for r in recent_fix[:15]:
            L.append("- " + ", ".join(f"{c['from']} → {c['to']} ({c['reason']})" for c in r["corrections"]) + f"  in “{r['corrected'][:70]}”")

    L.append("\n## What to do with this\n")
    L.append("- Unreviewed commands: open the phone → Settings → *Review commands* and tap 👍/👎 — the memory only helps once it knows what was right.")
    L.append("- Anything under *Marked wrong*: say it again a different way, or add the word it missed to the vocabulary.")
    L.append("- Re-run the audit corpus against your real history: `python -m scripts.audit_assistant --history`.")
    text = "\n".join(L)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"\nWritten to {args.out}")


if __name__ == "__main__":
    main()
