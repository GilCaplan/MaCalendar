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
        if reviewed:
            good = fb.get("approved", 0); bad = fb.get("corrected", 0) + fb.get("rejected", 0)
            L.append(f"- **Accuracy on reviewed commands: {good / max(1, good + bad):.0%}** (approved ÷ approved+corrected+rejected)")
            by_path_ok = collections.defaultdict(lambda: [0, 0])
            for r in rows:
                if r["feedback"] == "approved": by_path_ok[r["parse_path"]][0] += 1
                elif r["feedback"] in ("corrected", "rejected"): by_path_ok[r["parse_path"]][1] += 1
            L.append("  - by path: " + ", ".join(f"{p} {g}/{g + b} ({g / max(1, g + b):.0%})" for p, (g, b) in by_path_ok.items()))

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
