"""Tiny SVG icon loader for the shared "moody dev-tool" glyph set.

Icons live as hand-authored SVGs in `calendar_ui/icons/*.svg`, drawn on a
24x24 grid and colored with `currentColor` so a single file can be tinted
to match the active theme/accent. This module swaps `currentColor` for a
concrete hex color, rasterizes with QSvgRenderer, and caches the result
per (name, color, size) so repeated lookups (e.g. rebuilding a list every
refresh) don't re-parse/re-render the SVG.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_ICONS_DIR = os.path.join(os.path.dirname(__file__), "icons")

_pixmap_cache: dict[tuple, QPixmap] = {}
_icon_cache: dict[tuple, QIcon] = {}


def _default_color() -> str:
    """Current UI text color, so an untinted icon matches surrounding text."""
    from assistant.calendar_ui import styles
    return styles.D_GRAY_DARK if styles._dark else styles.GRAY_DARK


def _load_svg(name: str, color: str) -> bytes:
    path = os.path.join(_ICONS_DIR, f"{name}.svg")
    with open(path, "r", encoding="utf-8") as f:
        svg = f.read()
    return svg.replace("currentColor", color).encode("utf-8")


def pixmap(name: str, color: str | None = None, size: int = 16) -> QPixmap:
    """Rasterize an icon to a QPixmap (for QLabel icons, composite rows, …)."""
    color = color or _default_color()
    key = (name, color, size)
    cached = _pixmap_cache.get(key)
    if cached is not None:
        return cached
    renderer = QSvgRenderer(QByteArray(_load_svg(name, color)))
    out = QPixmap(QSize(size, size))
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    renderer.render(painter)
    painter.end()
    _pixmap_cache[key] = out
    return out


def icon(name: str, color: str | None = None, size: int = 16) -> QIcon:
    """Load `icons/<name>.svg`, tinted `color` (default: current text color)."""
    color = color or _default_color()
    key = (name, color, size)
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
    result = QIcon(pixmap(name, color, size))
    _icon_cache[key] = result
    return result
