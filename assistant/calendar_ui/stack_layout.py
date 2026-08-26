"""Binder-style layout for overlapping events (shared by day + week views).

Events whose blocks overlap on screen form a *cluster*. Instead of splitting the
column into narrow side-by-side lanes, the cluster is drawn as a stack of cards:
each later card sits on top of the previous one, shifted right by ``step`` px so
the earlier cards' left edges stay visible like the tabs of a binder. Clicking a
card that is not on top "pops" it out (full width, raised); clicking the popped
card opens it for editing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List


@dataclass
class Placed:
    event: dict
    x: int
    w: int
    top: int
    height: int
    depth: int          # 0 = bottom of the stack
    stack_size: int     # 1 = not overlapping anything
    full_x: int         # geometry to use when popped out
    full_w: int


def stacked_layout(events: List[dict], avail_w: int, hour_height: float, min_h: int,
                   left_pad: int, right_pad: int, step: int, to_min: Callable[[str], int]) -> List[Placed]:
    if not events:
        return []

    def ev_s(ev): return to_min(ev.get("start_time", "0:00"))
    def ev_e(ev): return max(to_min(ev.get("end_time", "0:00")), ev_s(ev) + 15)

    boxes = []
    for ev in sorted(events, key=lambda e: (ev_s(e), -ev_e(e))):
        top = int(ev_s(ev) / 60 * hour_height)
        h = max(int((ev_e(ev) - ev_s(ev)) / 60 * hour_height), min_h)
        boxes.append((ev, top, h))

    # Clusters by *pixel* overlap so a 15-minute event stretched to min_h still stacks.
    clusters: List[List[tuple]] = []
    cur: List[tuple] = []
    cur_bottom = -1
    for b in boxes:
        if cur and b[1] >= cur_bottom:
            clusters.append(cur); cur = []; cur_bottom = -1
        cur.append(b)
        cur_bottom = max(cur_bottom, b[1] + b[2])
    if cur:
        clusters.append(cur)

    usable = avail_w - left_pad - right_pad
    out: List[Placed] = []
    for grp in clusters:
        n = len(grp)
        eff_step = step if n * step <= usable * 0.5 else max(4, int(usable * 0.5 / n))
        for depth, (ev, top, h) in enumerate(grp):
            x = left_pad + depth * eff_step if n > 1 else left_pad
            w = max(usable - depth * eff_step, 40) if n > 1 else max(usable, 40)
            out.append(Placed(ev, x, w, top + 1, h - 2, depth, n, left_pad, max(usable, 40)))
    return out
