"""Tema visual centralizado de la aplicación (paleta profesional y QSS).

Modo claro por defecto. La estructura ya soporta un ``DARK_PALETTE`` para
cuando se active el modo oscuro desde Configuración (Fase 6); por ahora solo
se usa el claro.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    background: str
    surface: str
    border: str
    text_primary: str
    text_secondary: str
    primary: str
    primary_hover: str
    primary_text: str
    success: str
    warning: str
    error: str
    secondary: str


LIGHT_PALETTE = Palette(
    background="#F4F6F9",
    surface="#FFFFFF",
    border="#E2E6EC",
    text_primary="#1F2933",
    text_secondary="#5B6572",
    primary="#1E5FBF",
    primary_hover="#174C99",
    primary_text="#FFFFFF",
    success="#1F9254",
    warning="#B7791F",
    error="#C0392B",
    secondary="#6B7280",
)

DARK_PALETTE = Palette(
    background="#1B1F27",
    surface="#242B36",
    border="#323B49",
    text_primary="#E7EAEE",
    text_secondary="#9AA5B1",
    primary="#4C86E0",
    primary_hover="#6E9CE8",
    primary_text="#0B1220",
    success="#3FB37F",
    warning="#D9A441",
    error="#E0685B",
    secondary="#8A93A0",
)

SIDEBAR_WIDTH = 220
APP_FONT_FAMILY = "Segoe UI"
APP_FONT_SIZE = 10


def get_palette(theme_name: str) -> Palette:
    return DARK_PALETTE if theme_name == "dark" else LIGHT_PALETTE


def build_stylesheet(theme_name: str = "light") -> str:
    p = get_palette(theme_name)
    return f"""
    * {{
        font-family: '{APP_FONT_FAMILY}';
        font-size: {APP_FONT_SIZE}pt;
    }}
    QMainWindow, QWidget#contentArea {{
        background-color: {p.background};
    }}
    QWidget#sidebar {{
        background-color: {p.surface};
        border-right: 1px solid {p.border};
    }}
    QLabel#appTitle {{
        color: {p.text_primary};
        font-weight: 600;
        font-size: 14pt;
    }}
    QLabel#appVersion {{
        color: {p.text_secondary};
        font-size: 8pt;
    }}
    QPushButton#navButton {{
        text-align: left;
        padding: 10px 16px;
        border: none;
        border-radius: 6px;
        color: {p.text_primary};
        background-color: transparent;
    }}
    QPushButton#navButton:hover {{
        background-color: {p.background};
    }}
    QPushButton#navButton[active="true"] {{
        background-color: {p.primary};
        color: {p.primary_text};
        font-weight: 600;
    }}
    QPushButton {{
        padding: 8px 16px;
        border-radius: 6px;
        border: 1px solid {p.border};
        background-color: {p.surface};
        color: {p.text_primary};
    }}
    QPushButton:hover {{
        background-color: {p.background};
    }}
    QPushButton:disabled {{
        color: {p.text_secondary};
    }}
    QPushButton#primaryButton {{
        background-color: {p.primary};
        color: {p.primary_text};
        border: none;
        font-weight: 600;
    }}
    QPushButton#primaryButton:hover {{
        background-color: {p.primary_hover};
    }}
    QPushButton#primaryButton:disabled {{
        background-color: {p.border};
        color: {p.text_secondary};
    }}
    QFrame#card {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: 10px;
    }}
    QLabel#cardValue {{
        font-size: 20pt;
        font-weight: 700;
        color: {p.text_primary};
    }}
    QLabel#cardLabel {{
        color: {p.text_secondary};
        font-size: 9pt;
    }}
    QTableView, QTreeWidget {{
        background-color: {p.surface};
        color: {p.text_primary};
        alternate-background-color: {p.background};
        gridline-color: {p.border};
        border: 1px solid {p.border};
        selection-background-color: {p.primary};
        selection-color: {p.primary_text};
    }}
    QTableWidget::item, QTreeWidget::item {{
        color: {p.text_primary};
        padding: 4px 6px;
    }}
    QTableWidget::item:selected, QTreeWidget::item:selected {{
        background-color: {p.primary};
        color: {p.primary_text};
    }}
    QTableCornerButton::section {{
        background-color: {p.background};
        border: none;
        border-right: 1px solid {p.border};
        border-bottom: 1px solid {p.border};
    }}
    QHeaderView::section {{
        background-color: {p.background};
        color: {p.text_secondary};
        padding: 6px;
        border: none;
        border-bottom: 1px solid {p.border};
        font-weight: 600;
    }}
    QLineEdit, QComboBox, QDateEdit, QSpinBox, QPlainTextEdit {{
        padding: 6px 8px;
        border: 1px solid {p.border};
        border-radius: 6px;
        background-color: {p.surface};
        color: {p.text_primary};
    }}
    QComboBox QAbstractItemView {{
        background-color: {p.surface};
        color: {p.text_primary};
        border: 1px solid {p.border};
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 24px;
        padding: 4px 8px;
        color: {p.text_primary};
    }}
    QComboBox QAbstractItemView::item:selected {{
        background-color: {p.primary};
        color: {p.primary_text};
    }}
    QProgressBar {{
        border: 1px solid {p.border};
        border-radius: 6px;
        text-align: center;
        background-color: {p.background};
    }}
    QProgressBar::chunk {{
        background-color: {p.primary};
        border-radius: 6px;
    }}
    QLabel#statusSuccess {{ color: {p.success}; font-weight: 600; }}
    QLabel#statusWarning {{ color: {p.warning}; font-weight: 600; }}
    QLabel#statusError {{ color: {p.error}; font-weight: 600; }}
    """
