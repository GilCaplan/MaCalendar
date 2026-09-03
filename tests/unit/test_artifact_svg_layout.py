"""Text in the hand-authored diagrams must not overlap.

Three labels in the published explainers rendered on top of each other, and
nobody noticed until someone looked at the page. The diagrams are hand-written
SVG with absolute coordinates, so there is no layout engine to catch a label
that outgrew its space — a two-word edit to a caption is enough to do it.

The estimate below is deliberately crude: SVG has no way to measure text
without a renderer, so this approximates a glyph as a fraction of the font
size and only complains when two labels on the same baseline overlap by more
than a few pixels. It catches the failure that actually happened — a long
right-aligned label growing back into a left-aligned one — without failing on
every diagram that packs text tightly.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ARTIFACTS = pathlib.Path(__file__).resolve().parents[2] / "DOCUMENTATION" / "artifacts"
PAGES = sorted(ARTIFACTS.glob("*.html")) if ARTIFACTS.exists() else []

#: Average glyph width as a fraction of font-size. Real proportional text is
#: nearer 0.5; 0.46 keeps the estimate conservative so this reports collisions
#: rather than near-misses.
GLYPH = 0.46
#: Overlap smaller than this is kerning noise in the estimate, not a bug.
SLACK_PX = 4.0

_TEXT = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.S)
_ATTR = re.compile(r'(\w[\w-]*)\s*=\s*"([^"]*)"')


def _width(label: str, size: float) -> float:
    # Emoji render roughly square, and much wider than an average glyph.
    plain = sum(2.0 if ord(c) > 0x2000 else 1.0 for c in label)
    return plain * size * GLYPH


def _boxes(svg: str):
    for match in _TEXT.finditer(svg):
        attrs, inner = match.group(1), match.group(2)
        a = dict(_ATTR.findall(attrs))
        label = re.sub(r"<[^>]+>", "", inner).strip()
        if not label:
            continue
        try:
            x, y = float(a.get("x", 0)), float(a.get("y", 0))
        except ValueError:
            continue
        size = float(a.get("font-size", 12) or 12)
        w = _width(label, size)
        anchor = a.get("text-anchor", "start")
        left = x - w if anchor == "end" else x - w / 2 if anchor == "middle" else x
        yield y, left, left + w, label, size


_LINE = re.compile(r"<line\b([^>]*)>")
_RECT = re.compile(r"<rect\b([^>]*)>")


#: Strokes fainter than this read as background — a spine a label sits on
#: deliberately, not a line drawn across it. Judged by eye against the pages:
#: a 16%-opacity connector behind centred text is a normal, legible device;
#: a solid border under a label is the failure this test exists for.
VISIBLE_OPACITY = 0.35


def _opaque(attrs: dict) -> bool:
    for key in ("stroke-opacity", "opacity"):
        try:
            if float(attrs.get(key, 1)) < VISIBLE_OPACITY:
                return False
        except ValueError:
            pass
    return True


def _segments(svg: str):
    """Every straight stroke solid enough to obscure text."""
    for m in _LINE.finditer(svg):
        a = dict(_ATTR.findall(m.group(1)))
        if not _opaque(a):
            continue
        try:
            yield (float(a.get("x1", 0)), float(a.get("y1", 0)),
                   float(a.get("x2", 0)), float(a.get("y2", 0)))
        except ValueError:
            continue
    for m in _RECT.finditer(svg):
        a = dict(_ATTR.findall(m.group(1)))
        if a.get("stroke", "none") in ("none", "") or not _opaque(a):
            continue                       # a fill-only rect is a background, not an edge
        try:
            x, y = float(a.get("x", 0)), float(a.get("y", 0))
            w, h = float(a.get("width", 0)), float(a.get("height", 0))
        except ValueError:
            continue
        yield (x, y, x + w, y)             # the four borders
        yield (x, y + h, x + w, y + h)
        yield (x, y, x, y + h)
        yield (x + w, y, x + w, y + h)


def _crosses(seg, box) -> bool:
    """Does an axis-aligned stroke pass through the middle of a text box?

    Only horizontal and vertical strokes are judged — a diagonal grazing a
    corner is normal in these drawings and flagging it would bury the real
    hits. The box is inset before testing, so a label that merely sits inside
    a container is not reported; only a stroke running through the glyphs is.
    """
    x1, y1, x2, y2 = seg
    left, top, right, bottom = box
    inset_x, inset_y = 2.5, 2.0
    left, right = left + inset_x, right - inset_x
    top, bottom = top + inset_y, bottom - inset_y
    if right <= left or bottom <= top:
        return False
    if abs(y1 - y2) < 0.6:                                     # horizontal
        return top < y1 < bottom and min(x1, x2) < right and max(x1, x2) > left
    if abs(x1 - x2) < 0.6:                                     # vertical
        return left < x1 < right and min(y1, y2) < bottom and max(y1, y2) > top
    return False


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_label_has_a_stroke_running_through_it(page):
    """A line drawn across a label makes both unreadable.

    Reported from a screenshot, not by a test: two labels sat on top of a box
    border and an arrow, and all three fought for the same pixels. The
    baseline check below could never have seen it — it only compares text
    against other text.
    """
    text = page.read_text()
    problems = []
    for n, svg in enumerate(re.findall(r"<svg\b.*?</svg>", text, re.S)):
        segs = list(_segments(svg))
        for y, left, right, label, size in _boxes(svg):
            # The real font size, not a fixed guess: these drawings run from
            # 6.5px to 12px, and assuming the largest gave every small label a
            # box twice too tall, so any stroke passing nearby read as a hit.
            box = (left, y - size * 0.74, right, y + size * 0.20)
            for seg in segs:
                if _crosses(seg, box):
                    problems.append(f"figure {n + 1}: a stroke runs through {label!r}")
                    break
    assert not problems, f"{page.name}:\n  " + "\n  ".join(sorted(set(problems)))


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_two_labels_on_a_baseline_overlap(page):
    text = page.read_text()
    problems = []
    for n, svg in enumerate(re.findall(r"<svg\b.*?</svg>", text, re.S)):
        rows: dict[float, list] = {}
        for y, left, right, label, _size in _boxes(svg):
            rows.setdefault(round(y, 1), []).append((left, right, label))
        for y, items in rows.items():
            items.sort()
            for (l1, r1, a), (l2, r2, b) in zip(items, items[1:]):
                if r1 - l2 > SLACK_PX:
                    problems.append(
                        f"figure {n + 1}, y={y}: {a!r} and {b!r} overlap by "
                        f"{r1 - l2:.0f}px")
    assert not problems, f"{page.name}:\n  " + "\n  ".join(problems)
