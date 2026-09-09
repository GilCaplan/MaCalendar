"""Score the resolvers against the dataset.

    python -m assistant.engine.decompose_validate.eval_metrics.run_board [samples]

Feeds each gold item's (text, time) in and scores only the VALUES that come
back, so a segmentation disagreement can never be charged to this stage.
"""
import sys, json, datetime as dt, os
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, _ROOT)
from assistant.engine.decompose_validate import resolve as R
from assistant.engine.decompose_validate.eval_metrics import score as S
rows=[json.loads(l) for l in open(os.path.join(_ROOT, 'assistant/engine/decompose_validate/datasets/generated.jsonl'))]
_by={(r['text'],r['today']):r for r in rows}
def predict(text, today):
    anchor=dt.date.fromisoformat(today)
    out=[]
    for g in _by[(text,today)]['gold']:
        v=R.resolve(g['time'], anchor, text)
        out.append({"kind":g["kind"],"text":g["text"],"time":g["time"],
                    "date":v["date"],"start_time":v["start_time"],
                    "end_time":v["end_time"],"recurrence":v["recurrence"],
                    "quantity":R.resolve_quantity(g["text"]),
                    # lead time is a TIME slot, so it lives in `time`
                    "reminder_minutes":R.resolve_lead_time(g["time"]) or
                                       R.resolve_lead_time(g["text"])})
    return out
res=S.score_rows(rows, predict, samples=int(sys.argv[1]) if len(sys.argv)>1 else 6)
print(S.format_board(res))
