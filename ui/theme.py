"""Tema, tamanhos de fonte e locale brasileiro."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QLocale
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from core.app_paths import resource_path
from core.charting import configure_matplotlib

THEME_MODES = {
    "Pequena": {
        "font_pt": 10, "title_pt": 18, "subtitle_pt": 13, "kpi_pt": 20,
        "btn_min": 38, "input_min": 34, "table_row": 32, "icon": 20,
    },
    "Normal": {
        "font_pt": 12, "title_pt": 22, "subtitle_pt": 15, "kpi_pt": 24,
        "btn_min": 46, "input_min": 42, "table_row": 38, "icon": 24,
    },
    "Grande": {
        "font_pt": 14, "title_pt": 25, "subtitle_pt": 18, "kpi_pt": 28,
        "btn_min": 54, "input_min": 50, "table_row": 44, "icon": 28,
    },
    "Muito Grande": {
        "font_pt": 16, "title_pt": 28, "subtitle_pt": 20, "kpi_pt": 32,
        "btn_min": 62, "input_min": 58, "table_row": 50, "icon": 32,
    },
}

_current_mode = "Pequena"


def current_mode() -> str:
    return _current_mode


def current_font_pt() -> int:
    return int(THEME_MODES.get(_current_mode, THEME_MODES["Pequena"])["font_pt"])


def icon_size() -> int:
    return int(THEME_MODES.get(_current_mode, THEME_MODES["Pequena"])["icon"])


def table_row_height() -> int:
    return int(THEME_MODES.get(_current_mode, THEME_MODES["Pequena"])["table_row"])


def light_palette() -> QPalette:
    """Paleta clara fixa: evita ícones brancos e textos ilegíveis no tema escuro do sistema."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#DC2626"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#2563EB"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#DBEAFE"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#64748B"))
    palette.setColor(QPalette.ColorRole.Light, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Midlight, QColor("#F1F5F9"))
    palette.setColor(QPalette.ColorRole.Mid, QColor("#CBD5E1"))
    palette.setColor(QPalette.ColorRole.Dark, QColor("#94A3B8"))
    palette.setColor(QPalette.ColorRole.Shadow, QColor("#64748B"))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText, QPalette.ColorRole.HighlightedText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#94A3B8"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#E2E8F0"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#F1F5F9"))
    return palette


def load_stylesheet(mode: str) -> tuple[str, dict[str, Any]]:
    config = THEME_MODES.get(mode, THEME_MODES["Normal"])
    path = resource_path("ui/styles.qss")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = "QWidget { background-color: #F8FAFC; color: #0F172A; }"
    assets = resource_path("ui/assets").resolve().as_posix()
    replacements = {
        "@ASSETS@": assets,
        "@FONT_PT@": str(config["font_pt"]),
        "@TITLE_PT@": str(config["title_pt"]),
        "@SUBTITLE_PT@": str(config["subtitle_pt"]),
        "@KPI_PT@": str(config["kpi_pt"]),
        "@BTN_MIN@": str(config["btn_min"]),
        "@INPUT_MIN@": str(config["input_min"]),
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text, config


def apply_theme(app: QApplication, mode: str = "Normal") -> None:
    """Aplica fonte, QSS e estilo dos gráficos em toda a aplicação."""
    global _current_mode
    if mode not in THEME_MODES:
        mode = "Pequena"
    _current_mode = mode
    config = THEME_MODES[mode]
    QLocale.setDefault(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil))
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    font = QFont("DejaVu Sans")
    font.setPointSize(int(config["font_pt"]))
    app.setFont(font)
    stylesheet, _ = load_stylesheet(mode)
    app.setStyleSheet(stylesheet)
    configure_matplotlib(int(config["font_pt"]))
    from .wheel_guard import install_wheel_guard
    install_wheel_guard(app)
    app.setProperty("sisavalia_theme", mode)
    app.setProperty("sisavalia_font_pt", int(config["font_pt"]))
