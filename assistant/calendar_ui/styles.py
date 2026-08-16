"""Qt stylesheets and color constants.

Design language: "Moody Dev-tool" — near-black surfaces, sharp/compact
shapes, a single user-configurable accent color, tabular-mono touches on
times/dates. Both a dark theme (default) and a light theme are provided;
everything is generated from the same tokens so they stay in sync.
"""

import os
import re

# ------------------------------------------------------------------
# Color math helpers (no external deps — Qt ships without numpy/PIL)
# ------------------------------------------------------------------

def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(c))) for c in rgb))


def _relative_luminance(hex_color: str) -> float:
    r, g, b = (c / 255 for c in _hex_to_rgb(hex_color))

    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = lin(r), lin(g), lin(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def on_color(hex_color: str) -> str:
    """Legible foreground color to place on top of hex_color."""
    return "#15100a" if _relative_luminance(hex_color) > 0.42 else "#ffffff"


def _darken(hex_color: str, amt: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex((r * (1 - amt), g * (1 - amt), b * (1 - amt)))


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return f"rgba({r},{g},{b},{alpha})"


_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_ACCENT = "#f5a524"  # amber


def _load_configured_accent() -> str:
    """Best-effort read of ui.accent_color from config.yaml at import time.

    Falls back to DEFAULT_ACCENT on any error (missing file, bad YAML,
    key not set) so styles.py never fails to import.
    """
    try:
        import yaml
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(root, "config.yaml")
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        hex_color = (data.get("ui") or {}).get("accent_color")
        if hex_color and _HEX_RE.match(hex_color):
            return hex_color
    except Exception:
        pass
    return DEFAULT_ACCENT


def accent_tokens(accent: str = None) -> dict:
    """Derive the full accent color ramp from a single base hex."""
    base = accent if accent and _HEX_RE.match(accent) else DEFAULT_ACCENT
    return {
        "accent": base,
        "accent_hover": _darken(base, 0.08),
        "accent_pressed": _darken(base, 0.16),
        "on_accent": on_color(base),
        "accent_soft_light": _rgba(base, 0.13),
        "accent_soft_dark": _rgba(base, 0.17),
    }


# ------------------------------------------------------------------
# Accent — single user-configurable brand color (Settings → Accent Color)
# Read once at import time; call set_accent() to update the derived
# constants below at runtime (e.g. right after saving Settings).
# ------------------------------------------------------------------
_ACCENT_BASE = _load_configured_accent()
_ramp = accent_tokens(_ACCENT_BASE)

BLUE        = _ramp["accent"]          # kept name for call-site compatibility ("brand accent")
BLUE_HOVER  = _ramp["accent_hover"]
BLUE_DARK   = _ramp["accent_pressed"]
ON_ACCENT   = _ramp["on_accent"]
BLUE_LIGHT  = _ramp["accent_soft_light"]   # soft tint for active-btn bg (light mode)

# ------------------------------------------------------------------
# Light theme palette — clean, slightly warm neutrals
# ------------------------------------------------------------------
WHITE       = "#fbfbfa"
GRAY_BG     = "#f2f1ee"
GRAY_LIGHT  = "#f7f6f4"
GRAY_BORDER = "#e3e2dd"
GRAY_MID    = "#cdccc5"
GRAY_TEXT   = "#6b6b70"
GRAY_DARK   = "#17171b"

TODAY_BG         = BLUE
TODAY_TEXT       = ON_ACCENT
WEEKEND_BG       = "#f5f4f0"
OTHER_MONTH_TEXT = "#c7c6c0"
SELECTED_BG      = _ramp["accent_soft_light"]

# ------------------------------------------------------------------
# Dark theme palette — near-black, sharp
# ------------------------------------------------------------------
D_WHITE        = "#0a0a0c"
D_GRAY_BG      = "#0f1013"
D_GRAY_LIGHT   = "#141519"
D_GRAY_BORDER  = "#212227"
D_GRAY_MID     = "#3d3d43"
D_GRAY_TEXT    = "#87878f"
D_GRAY_DARK    = "#e9e9ec"
D_BLUE_LIGHT   = _ramp["accent_soft_dark"]
D_OTHER_MONTH_TEXT = "#3d3d43"
D_WEEKEND_BG   = "#0d0e11"

# Semantic (theme- and accent-independent)
DESTRUCTIVE      = "#e5484d"
DESTRUCTIVE_DARK = "#ff6b70"

EVENT_COLORS = [
    BLUE,       # default — follows the configured accent
    "#2fae5c",  # green
    "#c83b01",  # red-orange
    "#7c58b0",  # purple
    "#028385",  # teal
    "#b034a8",  # pink
    "#b84e0e",  # orange
]

# Presets offered in the Settings accent-color swatch picker
ACCENT_PRESETS = [
    ("Amber",  "#f5a524"),
    ("Indigo", "#6f68f0"),
    ("Teal",   "#2dd4bf"),
    ("Coral",  "#e0714f"),
    ("Blue",   "#3b93ff"),
    ("Pink",   "#d6409f"),
    ("Green",  "#2fae5c"),
]

# ------------------------------------------------------------------
# Runtime theme state
# ------------------------------------------------------------------
_dark: bool = True


def set_accent(hex_color: str) -> None:
    """Update the module-level accent ramp (BLUE, BLUE_HOVER, ON_ACCENT, ...).

    Existing `from styles import BLUE`-style imports elsewhere won't see
    this until the app restarts (Python binds the value at import time),
    but the central get_app_style() stylesheet — which drives the
    toolbar, primary buttons, tabs, mic and scrollbars — picks it up
    immediately since it always takes accent as a parameter.
    """
    global BLUE, BLUE_HOVER, BLUE_DARK, ON_ACCENT, BLUE_LIGHT, D_BLUE_LIGHT
    global TODAY_BG, TODAY_TEXT, SELECTED_BG, EVENT_COLORS, _ACCENT_BASE
    _ACCENT_BASE = hex_color
    ramp = accent_tokens(hex_color)
    BLUE = ramp["accent"]
    BLUE_HOVER = ramp["accent_hover"]
    BLUE_DARK = ramp["accent_pressed"]
    ON_ACCENT = ramp["on_accent"]
    BLUE_LIGHT = ramp["accent_soft_light"]
    D_BLUE_LIGHT = ramp["accent_soft_dark"]
    TODAY_BG = BLUE
    TODAY_TEXT = ON_ACCENT
    SELECTED_BG = ramp["accent_soft_light"]
    EVENT_COLORS[0] = BLUE


def get_accent() -> str:
    return _ACCENT_BASE


# Sharp / compact shape scale (chosen design — not user-togglable)
RADIUS_SM = 4
RADIUS_MD = 6
RADIUS_LG = 8

MONO_FONT = 'ui-monospace, "SF Mono", Menlo, Consolas, monospace'
UI_FONT   = '-apple-system, "Segoe UI", Arial, sans-serif'


def get_app_style(dark: bool = True, accent: str = None) -> str:
    """Return the full application stylesheet for light or dark mode."""
    global _dark
    _dark = dark
    ramp = accent_tokens(accent or _ACCENT_BASE)
    acc, acc_hover, acc_pressed, on_acc = (
        ramp["accent"], ramp["accent_hover"], ramp["accent_pressed"], ramp["on_accent"],
    )
    acc_soft = ramp["accent_soft_dark"] if dark else ramp["accent_soft_light"]

    bg      = D_WHITE      if dark else WHITE
    bg2     = D_GRAY_BG    if dark else GRAY_BG
    surface = D_GRAY_LIGHT if dark else GRAY_LIGHT
    border  = D_GRAY_BORDER if dark else GRAY_BORDER
    mid     = D_GRAY_MID   if dark else GRAY_MID
    text    = D_GRAY_DARK  if dark else GRAY_DARK
    text2   = D_GRAY_TEXT  if dark else GRAY_TEXT
    hover   = D_GRAY_LIGHT if dark else GRAY_LIGHT
    pressed = "#1c1d22"    if dark else "#eceae5"
    destructive = DESTRUCTIVE_DARK if dark else DESTRUCTIVE

    return f"""
QMainWindow, QWidget, QScrollArea, QStackedWidget, QListWidget, QListView {{
    background-color: {bg};
    font-family: {UI_FONT};
    font-size: 13px;
    color: {text};
    outline: none;
}}
QListWidget::item:selected {{
    background-color: {acc_soft};
    color: {text};
    border-radius: {RADIUS_SM}px;
}}
QListWidget::item:hover {{
    background-color: {surface};
    border-radius: {RADIUS_SM}px;
}}

/* ── Toolbar ── */
QToolBar {{
    background-color: {bg2};
    border-bottom: 1px solid {border};
    padding: 4px 8px;
    spacing: 4px;
}}

/* ── Standard buttons ── */
QPushButton {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: {RADIUS_MD}px;
    padding: 5px 14px;
    color: {text};
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {hover};
    border-color: {mid};
}}
QPushButton:pressed {{
    background-color: {pressed};
}}

/* ── Primary (New Event, Save) ── */
QPushButton#primary {{
    background-color: {acc};
    border-color: {acc};
    color: {on_acc};
    font-weight: 700;
    border-radius: {RADIUS_MD}px;
}}
QPushButton#primary:hover  {{ background-color: {acc_hover}; border-color: {acc_hover}; }}
QPushButton#primary:pressed {{ background-color: {acc_pressed}; border-color: {acc_pressed}; }}

/* ── Destructive (Delete) ── */
QPushButton#destructive {{
    background-color: transparent;
    border: 1px solid {destructive};
    color: {destructive};
    font-weight: 600;
    border-radius: {RADIUS_MD}px;
}}
QPushButton#destructive:hover {{ background-color: {destructive}; color: #ffffff; }}

/* ── Flat / ghost buttons ── */
QPushButton#flat {{
    background-color: transparent;
    border: none;
    padding: 4px 10px;
    border-radius: {RADIUS_MD}px;
    color: {text};
}}
QPushButton#flat:hover {{
    background-color: {hover};
}}
QPushButton#flat:pressed {{
    background-color: {pressed};
}}

/* ── Icon-only toolbar buttons (settings, theme, mic) ── */
/* No min-width/min-height here: every caller already calls
   setFixedSize(30, 30) in Python, and pairing that with a QSS min-height
   on top of the 4px padding inflated the rendered size to ~39px — pushing
   these buttons off-center in the toolbar row. */
QPushButton#icon_btn {{
    background-color: transparent;
    border: none;
    border-radius: {RADIUS_MD}px;
    font-size: 15px;
    padding: 4px;
    color: {text2};
}}
QPushButton#icon_btn:hover {{
    background-color: {hover};
    color: {text};
}}
QPushButton#icon_btn:pressed {{
    background-color: {pressed};
}}

/* ── Mic state variants ── */
/* No min-width/min-height on any of these three: setFixedSize(30, 30) is
   already called in Python, and pairing that with a QSS min-height on top
   of padding/border inflated the rendered size past 30px, pushing the mic
   button off-center in the toolbar row (same issue as #icon_btn above). */
QPushButton#mic_idle {{
    background-color: {acc};
    border: none;
    border-radius: {RADIUS_MD}px;
    font-size: 15px;
    padding: 4px;
    color: {on_acc};
}}
QPushButton#mic_idle:hover {{
    background-color: {acc_hover};
}}
QPushButton#mic_listening {{
    background-color: {destructive};
    border: none;
    border-radius: {RADIUS_MD}px;
    font-size: 16px;
    padding: 3px;
    color: #ffffff;
}}
QPushButton#mic_processing {{
    background-color: #e8a13a;
    border: none;
    border-radius: {RADIUS_MD}px;
    font-size: 16px;
    padding: 3px;
    color: #1a1206;
}}

/* ── Nav arrows ── */
QPushButton#nav {{
    background-color: transparent;
    border: none;
    border-radius: {RADIUS_SM}px;
    font-size: 17px;
    padding: 2px 6px;
    color: {text2};
}}
QPushButton#nav:hover {{
    background-color: {hover};
    color: {text};
}}

/* ── View toggle tabs (no container, each button standalone) ── */
QPushButton#seg_btn {{
    background-color: transparent;
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: 5px 14px;
    font-size: 12.5px;
    color: {text2};
    font-weight: 500;
}}
QPushButton#seg_btn:hover {{
    color: {text};
    background-color: {hover};
}}
QPushButton#seg_btn[active="true"] {{
    background-color: {acc};
    color: {on_acc};
    font-weight: 700;
}}

/* ── Splitter ── */
QSplitter::handle {{
    background-color: {border};
    width: 1px;
}}

/* ── Sidebar ── */
QWidget#sidebar {{
    background-color: {bg2};
    border-right: 1px solid {border};
}}

/* ── Mini calendar ── */
/* The native navigation bar (month/year QMenu dropdown) is hidden in
   favor of Sidebar's own header — see MiniCalendar in sidebar.py — since
   that QMenu popup isn't reliably themeable via QSS on macOS. */
QCalendarWidget {{
    background-color: {bg2};
}}
QCalendarWidget QAbstractItemView {{
    background-color: {bg2};
    selection-background-color: {acc};
    selection-color: {on_acc};
    color: {text};
    font-size: 12px;
}}

/* ── Labels ── */
QLabel#month_title {{
    font-size: 16px;
    font-weight: 700;
    color: {text};
    padding: 0 6px;
    letter-spacing: -0.01em;
}}
QLabel#day_header {{
    font-size: 10.5px;
    color: {text2};
    font-weight: 700;
    padding: 4px 0;
    text-align: center;
    letter-spacing: 0.03em;
}}

/* ── Dialog ── */
QDialog {{
    background-color: {bg};
}}
QLineEdit, QTextEdit, QDateEdit, QTimeEdit, QComboBox {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: {RADIUS_SM}px;
    padding: 6px 8px;
    font-size: 13px;
    color: {text};
}}
QLineEdit:focus, QTextEdit:focus, QDateEdit:focus, QTimeEdit:focus {{
    border: 1px solid {acc};
}}
QLineEdit#title_input {{
    font-size: 19px;
    font-weight: 600;
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {border};
    border-radius: 0;
    padding: 4px;
}}
QLineEdit#title_input:focus {{
    border-bottom: 2px solid {acc};
}}
QFormLayout QLabel {{
    font-size: 11.5px;
    color: {text2};
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}}
QLineEdit#todo_editor, QLineEdit#new_todo_editor {{
    background-color: transparent;
    border: none;
    border-radius: 0;
    padding: 2px 4px;
    color: {text};
}}
QLineEdit#todo_editor:focus, QLineEdit#new_todo_editor:focus {{
    border-bottom: 2px solid {acc};
}}

/* ── Scrollbar ── */
QScrollBar:vertical {{
    background-color: transparent;
    width: 8px;
    border: none;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {mid};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {text2};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    height: 0;
}}
"""


# Backward-compat alias
APP_STYLE = get_app_style(True)
