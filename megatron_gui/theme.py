"""MEGATRON visual language.

A phosphor-green desk with a distinct neon accent per engine and
JetBrains Mono typography throughout. Everything is defined here so the
app has one identity.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

# ----------------------------------------------------------------------
# Palette
# ----------------------------------------------------------------------

BG = "#020705"
PANEL = "#05110A"
RAISED = "#07170E"
HOVER = "#0C2616"
LINE = "#174328"
TEXT = "#D8FFE5"
MUTED = "#7FC795"
DIM = "#477A58"

ORANGE = "#C6FF3D"   # megastocks — acid lime
PURPLE = "#55FFC8"   # megacalls — mint
YELLOW = "#39FF88"   # megacrypto — matrix green
GREEN = "#6BFF9E"
RED = "#FF4D6D"
BLUE = "#4BFFE2"
INK = "#010B05"

ACCENTS = {
    "dashboard": BLUE,
    "stocks": ORANGE,
    "calls": PURPLE,
    "crypto": YELLOW,
}


def rgba(hex_color: str, alpha: float) -> str:
    """Qt stylesheet rgba() string from a hex colour."""
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{int(round(255 * alpha))})"


# ----------------------------------------------------------------------
# Type
# ----------------------------------------------------------------------

@lru_cache(maxsize=1)
def ui_family() -> str:
    """Use the terminal face everywhere; the desk has no prose sans."""
    return mono_family()


@lru_cache(maxsize=1)
def mono_family() -> str:
    families = set(QFontDatabase.families())
    for candidate in (
        "JetBrainsMono Nerd Font",
        "JetBrains Mono",
        "iA Writer Mono S",
        "DejaVu Sans Mono",
        "Liberation Mono",
    ):
        if candidate in families:
            return candidate
    return "monospace"


def font(size: int = 13, weight: QFont.Weight = QFont.Weight.Normal, *, mono: bool = False, spacing: float = 0.0) -> QFont:
    f = QFont(mono_family() if mono else ui_family())
    f.setPixelSize(size)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


# ----------------------------------------------------------------------
# QSS
# ----------------------------------------------------------------------

def build_qss() -> str:
    ui = ui_family()
    mono = mono_family()

    return f"""
    * {{
        font-family: "{mono}", "{ui}", monospace;
    }}
    QWidget {{
        color: {TEXT};
        font-size: 13px;
    }}
    #Root {{
        background: {BG};
    }}
    #Sidebar {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #04120A, stop:1 {PANEL});
        border-right: 1px solid {LINE};
    }}
    #HeaderBar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #081B10, stop:1 {PANEL});
        border-bottom: 1px solid {LINE};
    }}
    QFrame#Card {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {RAISED}, stop:1 #06120B);
        border: 1px solid {LINE};
        border-radius: 14px;
    }}
    QFrame#CardFlat {{
        background: {PANEL};
        border: 1px solid {LINE};
        border-radius: 12px;
    }}
    QSplitter::handle {{
        background: {LINE};
        width: 1px;
        height: 1px;
    }}
    QSplitter::handle:hover {{
        background: {GREEN};
    }}
    QFrame#RailStrip {{
        background: {PANEL};
        border-right: 1px solid {LINE};
    }}
    QPushButton#RailToggle {{
        background: transparent;
        color: {MUTED};
        border: 1px solid {LINE};
        border-radius: 6px;
        padding: 0;
        font-size: 13px;
        font-weight: 700;
    }}
    QPushButton#RailToggle:hover {{
        color: {ORANGE};
        border-color: {ORANGE};
        background: {HOVER};
    }}
    QComboBox {{
        background: {RAISED};
        border: 1px solid {LINE};
        border-radius: 8px;
        padding: 6px 9px;
        color: {TEXT};
        min-height: 20px;
    }}
    QComboBox:hover {{ border-color: {rgba(ORANGE, 0.5)}; }}
    QComboBox:focus {{ border-color: {GREEN}; }}
    QComboBox QAbstractItemView {{
        background: {PANEL};
        color: {TEXT};
        border: 1px solid {LINE};
        selection-background-color: {rgba(ORANGE, 0.22)};
        padding: 4px;
    }}
    QCheckBox {{
        color: {MUTED};
        spacing: 6px;
        font-size: 9px;
        font-weight: 600;
    }}
    QCheckBox:hover {{ color: {TEXT}; }}
    QCheckBox::indicator {{
        width: 13px;
        height: 13px;
        border: 1px solid {LINE};
        border-radius: 3px;
        background: {BG};
    }}
    QCheckBox::indicator:checked {{
        background: {ORANGE};
        border-color: {ORANGE};
    }}
    QTabWidget#ResearchTabs::pane {{
        border: none;
        background: transparent;
        top: -1px;
    }}
    QTabWidget#ResearchTabs QTabBar::tab {{
        background: {BG};
        color: {MUTED};
        border: 1px solid {LINE};
        border-radius: 7px;
        padding: 4px 10px;
        margin-right: 4px;
        min-width: 44px;
        font-family: "{mono}";
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 1px;
    }}
    QTabWidget#ResearchTabs QTabBar::tab:hover {{
        color: {TEXT};
        border-color: {MUTED};
    }}
    QTabWidget#ResearchTabs QTabBar::tab:selected {{
        color: {ORANGE};
        background: {rgba(ORANGE, 0.10)};
        border-color: {rgba(ORANGE, 0.52)};
    }}
    QTabBar#TickerTabs::tab {{
        background: transparent;
        color: {DIM};
        border: 1px solid transparent;
        border-radius: 5px;
        padding: 3px 7px;
        margin-right: 2px;
        font-family: "{mono}";
        font-size: 9px;
        font-weight: 700;
    }}
    QTabBar#TickerTabs::tab:hover {{
        color: {TEXT};
        background: {HOVER};
    }}
    QTabBar#TickerTabs::tab:selected {{
        color: {ORANGE};
        background: {rgba(ORANGE, 0.10)};
        border-color: {rgba(ORANGE, 0.40)};
    }}
    QFrame#Divider {{
        background: {LINE};
        border: none;
        max-height: 1px;
    }}
    QLabel {{
        background: transparent;
    }}
    QLabel#PageTitle {{
        font-family: "{mono}";
        font-size: 23px;
        font-weight: 700;
        color: {GREEN};
    }}
    QLabel#PageSub {{
        color: {DIM};
        font-size: 11px;
    }}
    QLabel#Hint {{
        color: {DIM};
        font-size: 11px;
    }}
    QLabel#Muted {{
        color: {MUTED};
        font-size: 12px;
    }}
    QPushButton {{
        background: {HOVER};
        color: {TEXT};
        border: 1px solid {LINE};
        border-radius: 9px;
        padding: 8px 14px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: #10331E;
        border-color: {GREEN};
    }}
    QPushButton:pressed {{
        background: #071C10;
    }}
    QPushButton:disabled {{
        background: #050E08;
        color: {DIM};
        border-color: #102B1A;
    }}
    QPushButton#Chip {{
        background: {BG};
        color: {MUTED};
        border: 1px solid {LINE};
        border-radius: 6px;
        padding: 3px 9px;
    }}
    QPushButton#Chip:hover {{
        color: {GREEN};
        border-color: {GREEN};
    }}
    QPushButton#Chip:checked {{
        background: {rgba(GREEN, 0.14)};
        color: {GREEN};
        border-color: {rgba(GREEN, 0.62)};
    }}
    QLineEdit {{
        background: #010604;
        border: 1px solid {LINE};
        border-radius: 9px;
        padding: 8px 11px;
        color: {TEXT};
        selection-background-color: {GREEN};
        selection-color: {INK};
    }}
    QLineEdit:focus {{
        border-color: {GREEN};
    }}
    QLineEdit#ConsoleInput {{
        font-family: "{mono}";
        font-size: 12px;
        padding: 7px 10px;
    }}
    QSpinBox, QDoubleSpinBox {{
        background: {BG};
        border: 1px solid {LINE};
        border-radius: 9px;
        padding: 8px 11px;
        color: {TEXT};
        selection-background-color: {ORANGE};
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {BLUE};
    }}
    QPlainTextEdit#Console {{
        background: #010604;
        border: 1px solid {LINE};
        border-radius: 11px;
        padding: 10px;
        color: #B5FFD0;
        selection-background-color: {GREEN};
        selection-color: {INK};
    }}
    QTableWidget {{
        background: #010604;
        alternate-background-color: #04110A;
        border: 1px solid {LINE};
        border-radius: 10px;
        gridline-color: #102B1A;
        selection-background-color: {GREEN};
        selection-color: {INK};
    }}
    QHeaderView::section {{
        background: {PANEL};
        color: {MUTED};
        border: none;
        border-bottom: 1px solid {LINE};
        padding: 8px 6px;
        font-size: 10px;
        font-weight: 700;
    }}
    QTableWidget::item {{
        padding: 4px 6px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: #1E5132;
        min-height: 28px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {GREEN};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: #1E5132;
        min-width: 28px;
        border-radius: 5px;
    }}
    QToolTip {{
        background: {RAISED};
        color: {TEXT};
        border: 1px solid {LINE};
        padding: 6px 8px;
    }}
    QMessageBox {{
        background: {PANEL};
    }}
    QMessageBox QLabel {{
        color: {TEXT};
    }}
    """


def apply_palette(app: QApplication) -> None:
    pal = QPalette()
    role = QPalette.ColorRole
    pal.setColor(role.Window, QColor(BG))
    pal.setColor(role.WindowText, QColor(TEXT))
    pal.setColor(role.Base, QColor(RAISED))
    pal.setColor(role.AlternateBase, QColor(PANEL))
    pal.setColor(role.Text, QColor(TEXT))
    pal.setColor(role.Button, QColor(RAISED))
    pal.setColor(role.ButtonText, QColor(TEXT))
    pal.setColor(role.Highlight, QColor(GREEN))
    pal.setColor(role.HighlightedText, QColor(INK))
    pal.setColor(role.ToolTipBase, QColor(RAISED))
    pal.setColor(role.ToolTipText, QColor(TEXT))
    pal.setColor(role.PlaceholderText, QColor(DIM))
    app.setPalette(pal)
