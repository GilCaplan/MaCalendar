"""Qt stylesheets and color constants."""

# ------------------------------------------------------------------
# Light theme palette
# ------------------------------------------------------------------
BLUE        = "#1a6fc4"        # slightly richer blue
BLUE_DARK   = "#155999"
BLUE_LIGHT  = "#e4effa"        # very soft tint for active-btn bg
BLUE_HOVER  = "#1862ad"

WHITE       = "#ffffff"
GRAY_BG     = "#f4f4f5"        # slightly cooler than before
GRAY_LIGHT  = "#f9f9fa"
GRAY_BORDER = "#dddde0"
GRAY_MID    = "#c0bfc4"
GRAY_TEXT   = "#6e6d75"
GRAY_DARK   = "#1c1b1f"

TODAY_BG         = BLUE
TODAY_TEXT       = WHITE
WEEKEND_BG       = "#f0f0f2"   # clearly distinct weekend column shade
OTHER_MONTH_TEXT = "#b0adb8"
SELECTED_BG      = "#eaf3fd"   # very soft blue tint for selected cell (light mode)

# ------------------------------------------------------------------
# Dark theme palette
# ------------------------------------------------------------------
D_WHITE        = "#1c1c1e"
D_GRAY_BG      = "#131315"
D_GRAY_LIGHT   = "#26262a"
D_GRAY_BORDER  = "#38383e"
D_GRAY_MID     = "#58585e"
D_GRAY_TEXT    = "#98989f"
D_GRAY_DARK    = "#e8e8ed"
D_BLUE_LIGHT   = "#1c2f42"   # subtle blue tint for selected cell (dark mode)
D_OTHER_MONTH_TEXT = "#505058"
D_WEEKEND_BG   = "#232328"   # clearly distinct weekend column shade (dark)

EVENT_COLORS = [
    "#1a6fc4",  # blue (default)
    "#108010",  # green
    "#c83b01",  # red-orange
    "#7c58b0",  # purple
    "#028385",  # teal
    "#b034a8",  # pink
    "#b84e0e",  # orange
]

# ------------------------------------------------------------------
# Runtime theme state
# ------------------------------------------------------------------
_dark: bool = False


def get_app_style(dark: bool = False) -> str:
    """Return the full application stylesheet for light or dark mode."""
    global _dark
    _dark = dark

    bg      = D_WHITE      if dark else WHITE
    bg2     = D_GRAY_BG    if dark else GRAY_BG
    border  = D_GRAY_BORDER if dark else GRAY_BORDER
    mid     = D_GRAY_MID   if dark else GRAY_MID
    text    = D_GRAY_DARK  if dark else GRAY_DARK
    text2   = D_GRAY_TEXT  if dark else GRAY_TEXT
    pressed = "#2e2e30"    if dark else "#e8e8ea"

    return f"""
QMainWindow, QWidget {{
    background-color: {bg};
    font-family: -apple-system, "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    color: {text};
}}

/* ── Toolbar ── */
QToolBar {{
    background-color: {bg};
    border-bottom: 1px solid {border};
    padding: 4px 8px;
    spacing: 4px;
}}

/* ── Standard buttons ── */
QPushButton {{
    background-color: {bg};
    border: 1px solid {mid};
    border-radius: 6px;
    padding: 5px 14px;
    color: {text};
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {bg2};
    border-color: {mid};
}}
QPushButton:pressed {{
    background-color: {pressed};
}}

/* ── Primary (New Event, Save) ── */
QPushButton#primary {{
    background-color: {BLUE};
    border-color: {BLUE};
    color: white;
    font-weight: 600;
    border-radius: 6px;
}}
QPushButton#primary:hover  {{ background-color: {BLUE_HOVER}; border-color: {BLUE_HOVER}; }}
QPushButton#primary:pressed {{ background-color: {BLUE_DARK}; }}

/* ── Flat / ghost buttons ── */
QPushButton#flat {{
    background: transparent;
    border: none;
    padding: 4px 10px;
    border-radius: 6px;
    color: {text};
}}
QPushButton#flat:hover {{
    background-color: {bg2};
}}
QPushButton#flat:pressed {{
    background-color: {pressed};
}}

/* ── Icon-only toolbar buttons (settings, theme, mic) ── */
QPushButton#icon_btn {{
    background: transparent;
    border: none;
    border-radius: 6px;
    font-size: 15px;
    padding: 4px;
    color: {text};
    min-width: 30px;
    min-height: 30px;
}}
QPushButton#icon_btn:hover {{
    background-color: {bg2};
}}
QPushButton#icon_btn:pressed {{
    background-color: {pressed};
}}

/* ── Mic state variants ── */
QPushButton#mic_idle {{
    background: transparent;
    border: none;
    border-radius: 6px;
    font-size: 16px;
    padding: 4px;
    color: {text2};
    min-width: 30px;
    min-height: 30px;
}}
QPushButton#mic_idle:hover {{
    background-color: {bg2};
    color: {text};
}}
QPushButton#mic_listening {{
    background-color: #fde7e9;
    border: 1px solid #f0a0a5;
    border-radius: 6px;
    font-size: 16px;
    padding: 4px;
    color: #c0373c;
    min-width: 30px;
    min-height: 30px;
}}
QPushButton#mic_processing {{
    background-color: #fef5d6;
    border: 1px solid #e8cc74;
    border-radius: 6px;
    font-size: 16px;
    padding: 4px;
    color: #9a7700;
    min-width: 30px;
    min-height: 30px;
}}

/* ── Nav arrows ── */
QPushButton#nav {{
    background: transparent;
    border: none;
    border-radius: 5px;
    font-size: 17px;
    padding: 2px 6px;
    color: {text2};
    min-width: 26px;
    min-height: 26px;
}}
QPushButton#nav:hover {{
    background-color: {bg2};
    color: {text};
}}

/* ── View toggle tabs (no container, each button standalone) ── */
QPushButton#seg_btn {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 5px 14px;
    font-size: 13px;
    color: {text2};
    font-weight: 400;
}}
QPushButton#seg_btn:hover {{
    color: {text};
    background-color: {bg2};
}}
QPushButton#seg_btn[active="true"] {{
    background-color: {BLUE};
    color: white;
    font-weight: 600;
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
QCalendarWidget {{
    background-color: {bg2};
}}
QCalendarWidget QToolButton {{
    background: transparent;
    color: {text};
    font-size: 12px;
    border: none;
    padding: 2px;
}}
QCalendarWidget QToolButton:hover {{
    background-color: {border};
    border-radius: 3px;
}}
QCalendarWidget QMenu {{
    background-color: {bg};
    color: {text};
}}
QCalendarWidget QSpinBox {{
    background-color: {bg};
    border: 1px solid {mid};
    border-radius: 2px;
    color: {text};
}}
QCalendarWidget QAbstractItemView {{
    background-color: {bg2};
    selection-background-color: {BLUE};
    selection-color: white;
    color: {text};
    font-size: 12px;
}}

/* ── Labels ── */
QLabel#month_title {{
    font-size: 17px;
    font-weight: 600;
    color: {text};
    padding: 0 6px;
}}
QLabel#day_header {{
    font-size: 11px;
    color: {text2};
    font-weight: 600;
    padding: 4px 0;
    text-align: center;
}}

/* ── Dialog ── */
QDialog {{
    background-color: {bg};
}}
QLineEdit, QTextEdit, QDateEdit, QTimeEdit, QComboBox {{
    background-color: {bg};
    border: none;
    border-bottom: 1px solid {border};
    border-radius: 0;
    padding: 6px 4px;
    font-size: 13px;
    color: {text};
}}
QLineEdit:focus, QTextEdit:focus, QDateEdit:focus, QTimeEdit:focus {{
    border-bottom: 2px solid {BLUE};
}}
QLineEdit#title_input {{
    font-size: 20px;
    font-weight: 400;
    border-bottom: 1px solid {border};
    padding: 4px;
}}
QLineEdit#title_input:focus {{
    border-bottom: 2px solid {BLUE};
}}
QFormLayout QLabel {{
    font-size: 12px;
    color: {text2};
}}

/* ── Scrollbar ── */
QScrollBar:vertical {{
    background: transparent;
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
APP_STYLE = get_app_style(False)
