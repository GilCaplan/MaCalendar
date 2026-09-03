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
        yield y, left, left + w, label


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_two_labels_on_a_baseline_overlap(page):
    text = page.read_text()
    problems = []
    for n, svg in enumerate(re.findall(r"<svg\b.*?</svg>", text, re.S)):
        rows: dict[float, list] = {}
        for y, left, right, label in _boxes(svg):
            rows.setdefault(round(y, 1), []).append((left, right, label))
        for y, items in rows.items():
            items.sort()
            for (l1, r1, a), (l2, r2, b) in zip(items, items[1:]):
                if r1 - l2 > SLACK_PX:
                    problems.append(
                        f"figure {n + 1}, y={y}: {a!r} and {b!r} overlap by "
                        f"{r1 - l2:.0f}px")
    assert not problems, f"{page.name}:\n  " + "\n  ".join(problems)
