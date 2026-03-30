"""Qt stylesheets and color constants — Outlook-inspired palette."""

# ------------------------------------------------------------------
# Light theme palette
# ------------------------------------------------------------------
BLUE = "#0078d4"
BLUE_DARK = "#005a9e"
BLUE_LIGHT = "#deecf9"
BLUE_HOVER = "#106ebe"

WHITE = "#ffffff"
GRAY_BG = "#f5f5f5"
GRAY_LIGHT = "#fafafa"
GRAY_BORDER = "#e0e0e0"
GRAY_MID = "#c8c8c8"
GRAY_TEXT = "#605e5c"
GRAY_DARK = "#323130"

TODAY_BG = BLUE
TODAY_TEXT = WHITE
WEEKEND_BG = "#fafafa"
OTHER_MONTH_TEXT = "#a19f9d"
SELECTED_BG = "#deecf9"

# ------------------------------------------------------------------
# Dark theme palette
# ------------------------------------------------------------------
D_WHITE = "#1e1e1e"
D_GRAY_BG = "#141414"
D_GRAY_LIGHT = "#252525"
D_GRAY_BORDER = "#383838"
D_GRAY_MID = "#555555"
D_GRAY_TEXT = "#a0a0a0"
D_GRAY_DARK = "#e8e8e8"
D_BLUE_LIGHT = "#003d6b"
D_OTHER_MONTH_TEXT = "#555555"
D_WEEKEND_BG = "#242424"

EVENT_COLORS = [
    "#0078d4",  # blue (default)
    "#107c10",  # green
    "#d83b01",  # red-orange
    "#8764b8",  # purple
    "#038387",  # teal
    "#c239b3",  # pink
    "#ca5010",  # orange
]

# ------------------------------------------------------------------
# Runtime theme state (read by views in paintEvent / rebuild)
# ------------------------------------------------------------------
_dark: bool = False


def get_app_style(dark: bool = False) -> str:
    """Return the full application stylesheet for light or dark mode."""
    global _dark
    _dark = dark

    bg = D_WHITE if dark else WHITE
    bg2 = D_GRAY_BG if dark else GRAY_BG
    border = D_GRAY_BORDER if dark else GRAY_BORDER
    mid = D_GRAY_MID if dark else GRAY_MID
    text = D_GRAY_DARK if dark else GRAY_DARK
    text2 = D_GRAY_TEXT if dark else GRAY_TEXT
    blue_light = D_BLUE_LIGHT if dark else BLUE_LIGHT
    pressed = "#333333" if dark else "#edebe9"

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

/* ── Buttons ── */
QPushButton {{
    background-color: {bg};
    border: 1px solid {mid};
    border-radius: 4px;
    padding: 5px 14px;
    color: {text};
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {bg2};
    border-color: {text};
}}
QPushButton:pressed {{
    background-color: {pressed};
}}
QPushButton#primary {{
    background-color: {BLUE};
    border-color: {BLUE};
    color: {WHITE};
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background-color: {BLUE_HOVER};
    border-color: {BLUE_HOVER};
}}
QPushButton#primary:pressed {{
    background-color: {BLUE_DARK};
}}
QPushButton#flat {{
    background: transparent;
    border: none;
    padding: 4px 8px;
}}
QPushButton#flat:hover {{
    background-color: {bg2};
    border-radius: 4px;
}}
QPushButton#mic_idle {{
    background: transparent;
    border: none;
    font-size: 18px;
    padding: 2px 8px;
}}
QPushButton#mic_listening {{
    background-color: #fde7e9;
    border: none;
    border-radius: 4px;
    font-size: 18px;
    padding: 2px 8px;
}}
QPushButton#mic_processing {{
    background-color: #fff4ce;
    border: none;
    border-radius: 4px;
    font-size: 18px;
    padding: 2px 8px;
}}

/* ── Nav arrow buttons ── */
QPushButton#nav {{
    background: transparent;
    border: none;
    font-size: 16px;
    padding: 2px 6px;
    color: {text};
}}
QPushButton#nav:hover {{
    background-color: {bg2};
    border-radius: 4px;
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
    selection-color: {WHITE};
    color: {text};
    font-size: 12px;
}}

/* ── Labels ── */
QLabel#month_title {{
    font-size: 20px;
    font-weight: 600;
    color: {text};
    padding: 0 8px;
}}
QLabel#day_header {{
    font-size: 11px;
    color: {text2};
    font-weight: 600;
    text-transform: uppercase;
    padding: 4px 0;
    text-align: center;
}}

/* ── View toggle buttons ── */
QPushButton#view_btn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
    color: {text2};
}}
QPushButton#view_btn:hover {{
    background-color: {bg2};
    border-color: {mid};
}}
QPushButton#view_btn[active="true"] {{
    background-color: {blue_light};
    border-color: {BLUE};
    color: {BLUE};
    font-weight: 600;
}}

/* ── Dialog ── */
QDialog {{
    background-color: {bg};
}}
QLineEdit, QTextEdit, QDateEdit, QTimeEdit, QComboBox {{
    background-color: {bg};
    border: none;
    border-bottom: 1px solid {mid};
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
    border-bottom: 1px solid {mid};
    padding: 4px;
}}
QLineEdit#title_input:focus {{
    border-bottom: 2px solid {BLUE};
}}

/* ── Scrollbar ── */
QScrollBar:vertical {{
    background: {bg};
    width: 6px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {mid};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
"""


# Backward-compat alias (static light-mode string, used by older imports)
APP_STYLE = get_app_style(False)
