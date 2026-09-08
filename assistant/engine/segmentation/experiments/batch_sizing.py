"""How many commands can go in ONE LLMSeg call before the answers degrade?

Batching is attractive because the prompt is mostly FIXED: the rules block and
the examples are ~500 tokens and the command itself is ~50, so K commands in
one call cost 500 + K*50 instead of K*550. At 20s/row measured, that is the
difference between a 50-minute board and a 10-minute one.

But batching is only legitimate if it does not change the ANSWER. So the test
is not "is it faster" — it obviously is — it is:

    does the batched answer EQUAL the answer the same command gets alone?

K=1 answers come from the run cache, so the baseline is the real unbatched
output rather than a re-derivation. Anything below 100% agreement means the
model is leaking context between commands, and the largest K that still agrees
is the one worth shipping.

Two separate questions, deliberately measured together:
  - FOR THE TEST HARNESS: any K that agrees is a pure speed win.
  - FOR THE PRODUCT: batching only applies where commands already queue (the
    engine's ingest step coalesces), and a shared call means one malformed
    reply can spoil K commands — so the product wants a smaller, safer K than
    the harness does.

    python -m assistant.engine.segmentation.experiments.batch_sizing            # one llama job, ~10 min
"""
from __future__ import annotations

import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_S = "/tmp/seg_batch_sizing"
os.makedirs(_S, exist_ok=True)
for k, v in dict(MACALENDAR_DB=f"{_S}/c.db", MACALENDAR_MEMORY_DB=f"{_S}/m.db",
                 MACALENDAR_VOCAB=f"{_S}/v.json", MACALENDAR_CATEGORIES=f"{_S}/g.json",
                 MACALENDAR_TRACE_BUS=f"{_S}/t.jsonl",
                 MACALENDAR_NO_WARMUP="1").items():
    os.environ.setdefault(k, v)

from assistant.engine.segmentation.llmseg import llmseg                       # noqa: E402
from assistant.engine.segmentation.fastseg.fastseg import fastseg              # noqa: E402

_CACHE = os.path.join(_HERE, "experiments", "runs", "llmseg_cache.jsonl")


def load_baseline() -> "list[tuple[str, list]]":
    """(text, items) for every command already answered UNBATCHED."""
    out = []
    seen = set()
    try:
        with open(_CACHE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec["text"] in seen:
                    continue
                seen.add(rec["text"])
                out.append((rec["text"], rec["result"]["items"]))
    except OSError:
        pass
    return out


# ---------------------------------------------------------------------------
# The batched prompt — FLAT keys ("2.1" = command 2, item 1)
# ---------------------------------------------------------------------------
#
# Flat rather than nested on purpose. An 8B asked for {"1": {"1": [...]}} tends
# to lose a brace level; "<command>.<item>" is one object deep and each key
# says exactly where it belongs, so a partial answer is still parseable.

def build_batch_prompt(batch: "list[tuple[str, list]]") -> str:
    lines = []
    for n, (text, proposal) in enumerate(batch, 1):
        compact = {str(i + 1): [it["action"], it["time"], it["tag"]]
                   for i, it in enumerate(proposal)}
        lines.append(f'{n}. COMMAND: {text}\n   PROPOSAL: {json.dumps(compact)}')
    commands = "\n".join(lines)
    return f"""You are given {len(batch)} SEPARATE commands. They are unrelated to each
other. Decompose EACH ONE independently — never move words between commands.

{commands}

{llmseg._RULES}

{llmseg._EXAMPLES}

Output ONE JSON object. Each key is "<command number>.<item number>" and each
value is [action, time, tag]. Every one of the {len(batch)} commands must appear
at least once. Output the JSON and nothing else - no explanation, no code fence.

Example shape for 2 commands where the first has two items:
{{"1.1": ["gym", "tomorrow at 7", "event"], "1.2": ["meeting", "tomorrow at 11", "event"], "2.1": ["buy milk", "today", "task"]}}"""


def parse_batch(raw: str, batch) -> "list[list[dict]] | None":
    try:
        blob = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except Exception:
        return None
    out: "list[list[dict]]" = [[] for _ in batch]
    for key, value in blob.items():
        try:
            cmd_i = int(str(key).split(".")[0]) - 1
        except ValueError:
            continue
        if not (0 <= cmd_i < len(batch)):
            continue
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            continue
        fallback = batch[cmd_i][1][0]["tag"] if batch[cmd_i][1] else "event"
        out[cmd_i].append({"action": str(value[0]).strip(),
                           "time": str(value[1]).strip() or "today",
                           "tag": llmseg.normalise_tag(
                               value[2] if len(value) > 2 else "", fallback)})
    return out


def same(a: "list[dict]", b: "list[dict]") -> bool:
    def key(items):
        return [(i["action"].strip().lower(), i["time"].strip().lower(), i["tag"])
                for i in items]
    return key(a) == key(b)


def main() -> None:
    baseline = load_baseline()
    if len(baseline) < 8:
        raise SystemExit(f"need >=8 cached unbatched answers, have {len(baseline)}. "
                         "Run the segment board first to fill the cache.")
    print(f"baseline: {len(baseline)} commands answered UNBATCHED (K=1)\n")

    # K=1's own cost, straight from the cache — not re-measured.
    ks = [k for k in (2, 4, 8, 16) if k <= len(baseline)]
    print(f"{'K':>3}  {'calls':>5}  {'agree':>12}  {'s/row':>7}  {'parse':>6}   notes")
    print("-" * 64)

    for K in ks:
        usable = (len(baseline) // K) * K
        rows = baseline[:usable]
        agree = total = 0
        parse_fail = 0
        elapsed = 0.0
        for start in range(0, usable, K):
            chunk = rows[start:start + K]
            batch = [(t, fastseg(t)) for t, _ in chunk]
            t0 = time.perf_counter()
            try:
                raw = llmseg.call_model(build_batch_prompt(batch), timeout=300)
            except Exception as exc:
                print(f"{K:>3}  model error: {type(exc).__name__}")
                break
            elapsed += time.perf_counter() - t0
            got = parse_batch(raw, batch)
            if got is None:
                parse_fail += 1
                total += len(chunk)
                continue
            for (text, want), mine in zip(chunk, got):
                total += 1
                if not mine:
                    continue
                agree += same(want, mine)
        if total:
            print(f"{K:>3}  {usable // K:>5}  {agree:>4}/{total:<7} "
                  f"{elapsed / total:>7.1f}  {parse_fail:>6}   "
                  f"{'OK' if agree == total else 'DIVERGES'}")
        sys.stdout.flush()

    print("\nK=1 reference: 20.1 s/row (26 cached rows, model resident)")
    print("Read: the largest K whose agreement is 4-of-4 style perfect is the "
          "one that is safe to use. Divergence at any K means the model is "
          "leaking between commands.")


if __name__ == "__main__":
    main()
