"""Binder-style stacking of overlapping events."""

from assistant.calendar_ui.stack_layout import stacked_layout


def _to_min(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _ev(i, s, e):
    return {"id": i, "title": f"e{i}", "start_time": s, "end_time": e}


def test_non_overlapping_events_are_full_width_singletons():
    out = stacked_layout([_ev(1, "09:00", "10:00"), _ev(2, "10:00", "11:00")], 200, 60, 20, 4, 6, 14, _to_min)
    assert [p.stack_size for p in out] == [1, 1]
    assert all(p.x == 4 and p.w == 190 for p in out)


def test_overlapping_events_step_in_like_binder_tabs():
    out = stacked_layout([_ev(1, "09:00", "11:00"), _ev(2, "09:30", "10:30"), _ev(3, "10:00", "12:00")],
                         200, 60, 20, 4, 6, 14, _to_min)
    assert [p.depth for p in out] == [0, 1, 2] and all(p.stack_size == 3 for p in out)
    assert [p.x for p in out] == [4, 18, 32]
    assert [p.w for p in out] == [190, 176, 162]
    assert all(p.full_x == 4 and p.full_w == 190 for p in out)     # popped-out geometry


def test_pixel_overlap_from_min_height_still_stacks():
    # A 5-minute event stretched to min_h overlaps the next one on screen.
    out = stacked_layout([_ev(1, "08:30", "08:35"), _ev(2, "08:40", "09:00")], 200, 60, 40, 4, 6, 14, _to_min)
    assert all(p.stack_size == 2 for p in out)


def test_step_is_capped_for_big_stacks():
    evs = [_ev(i, "09:00", "10:00") for i in range(10)]
    out = stacked_layout(evs, 100, 60, 20, 2, 2, 14, _to_min)
    assert out[-1].w >= 40 and out[-1].x <= 2 + 96 * 0.5
