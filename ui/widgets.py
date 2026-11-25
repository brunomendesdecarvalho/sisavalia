"""Widgets, ícones, mensagens e utilidades visuais reutilizáveis."""
from __future__ import annotations

import logging
import math
import traceback
from typing import Any, Iterable, Optional

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import (
    QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSizePolicy, QStyle, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.app_paths import log_exception
from core.formatting import format_number, is_missing

LOGGER = logging.getLogger(__name__)

ICON_NAMES: dict[str, QStyle.StandardPixmap] = {
    "new": QStyle.StandardPixmap.SP_FileIcon,
    "open": QStyle.StandardPixmap.SP_DirOpenIcon,
    "save": QStyle.StandardPixmap.SP_DialogSaveButton,
    "recent": QStyle.StandardPixmap.SP_FileDialogDetailedView,
    "report": QStyle.StandardPixmap.SP_FileDialogDetailedView,
    "spreadsheet": QStyle.StandardPixmap.SP_FileDialogListView,
    "help": QStyle.StandardPixmap.SP_DialogHelpButton,
    "font": QStyle.StandardPixmap.SP_FileDialogInfoView,
    "add": QStyle.StandardPixmap.SP_FileDialogNewFolder,
    "delete": QStyle.StandardPixmap.SP_TrashIcon,
    "edit": QStyle.StandardPixmap.SP_FileDialogContentsView,
    "copy": QStyle.StandardPixmap.SP_FileIcon,
    "refresh": QStyle.StandardPixmap.SP_BrowserReload,
    "undo": QStyle.StandardPixmap.SP_ArrowBack,
    "search": QStyle.StandardPixmap.SP_FileDialogListView,
    "play": QStyle.StandardPixmap.SP_MediaPlay,
    "stop": QStyle.StandardPixmap.SP_MediaStop,
    "save_image": QStyle.StandardPixmap.SP_DialogSaveButton,
    "calculator": QStyle.StandardPixmap.SP_ComputerIcon,
    "metadata": QStyle.StandardPixmap.SP_FileDialogInfoView,
    "close": QStyle.StandardPixmap.SP_DialogCloseButton,
    "ok": QStyle.StandardPixmap.SP_DialogApplyButton,
    "cancel": QStyle.StandardPixmap.SP_DialogCancelButton,
    "warning": QStyle.StandardPixmap.SP_MessageBoxWarning,
    "info": QStyle.StandardPixmap.SP_MessageBoxInformation,
    "error": QStyle.StandardPixmap.SP_MessageBoxCritical,
    "plugin": QStyle.StandardPixmap.SP_DirIcon,
    "up": QStyle.StandardPixmap.SP_ArrowUp,
    "down": QStyle.StandardPixmap.SP_ArrowDown,
    "chart": QStyle.StandardPixmap.SP_ComputerIcon,
    "cluster": QStyle.StandardPixmap.SP_DirIcon,
    "simulation": QStyle.StandardPixmap.SP_MediaPlay,
}


ICON_COLORS = {
    "warning": "#B45309",
    "error": "#B91C1C",
    "delete": "#B91C1C",
    "ok": "#15803D",
    "info": "#1D4ED8",
}


def _tinted_pixmap(pixmap: QPixmap, color: str) -> QPixmap:
    if pixmap.isNull():
        return pixmap
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    target = QColor(color)
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() > 0:
                pixel.setRed(target.red())
                pixel.setGreen(target.green())
                pixel.setBlue(target.blue())
                image.setPixelColor(x, y, pixel)
    return QPixmap.fromImage(image)


def _draw_custom_icon(name: str, color: str, size: int = 48) -> Optional[QPixmap]:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color), 3.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    c = size / 48.0
    painter.scale(c, c)

    def line(x1: float, y1: float, x2: float, y2: float) -> None:
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def rect(x: float, y: float, w: float, h: float, radius: float = 2.0) -> None:
        painter.drawRoundedRect(QRectF(x, y, w, h), radius, radius)

    def circle(cx: float, cy: float, r: float) -> None:
        painter.drawEllipse(QPointF(cx, cy), r, r)

    def poly(points: list[tuple[float, float]], close: bool = False) -> None:
        path = QPainterPath(QPointF(points[0][0], points[0][1]))
        for x, y in points[1:]:
            path.lineTo(QPointF(x, y))
        if close:
            path.closeSubpath()
        painter.drawPath(path)

    if name == "new":
        rect(13, 7, 23, 34, 2)
        line(18, 20, 31, 20); line(18, 26, 31, 26); line(18, 32, 27, 32)
        line(34, 29, 42, 29); line(38, 25, 38, 33)
    elif name == "open":
        poly([(7, 18), (20, 18), (24, 13), (41, 13), (41, 37), (7, 37)], True)
        line(7, 21, 41, 21)
    elif name == "save":
        poly([(11, 8), (35, 8), (40, 13), (40, 39), (11, 39)], True)
        rect(18, 8, 16, 10, 1)
        rect(17, 26, 18, 13, 1)
    elif name == "recent":
        circle(24, 24, 16)
        line(24, 13, 24, 25); line(24, 25, 32, 29)
    elif name == "report":
        poly([(12, 7), (30, 7), (37, 14), (37, 41), (12, 41)], True)
        poly([(30, 7), (30, 15), (37, 15)])
        line(18, 23, 31, 23); line(18, 29, 31, 29); line(18, 35, 27, 35)
    elif name == "spreadsheet":
        rect(8, 10, 32, 29, 2)
        line(8, 19, 40, 19); line(8, 29, 40, 29)
        line(19, 10, 19, 39); line(30, 10, 30, 39)
    elif name == "help":
        circle(24, 24, 17)
        painter.setFont(QFont("DejaVu Sans", 22, QFont.Weight.Bold))
        painter.drawText(QRectF(10, 10, 28, 28), Qt.AlignmentFlag.AlignCenter, "?")
    elif name in ("add", "ok"):
        if name == "ok":
            poly([(10, 25), (20, 35), (38, 15)])
        else:
            line(24, 11, 24, 37); line(11, 24, 37, 24)
    elif name == "delete":
        line(10, 14, 38, 14)
        poly([(16, 14), (18, 41), (30, 41), (32, 14)])
        poly([(19, 14), (21, 9), (27, 9), (29, 14)])
        line(22, 21, 22, 34); line(27, 21, 27, 34)
    elif name == "edit":
        poly([(11, 37), (14, 27), (32, 9), (39, 16), (21, 34)], True)
        line(29, 12, 36, 19)
    elif name == "copy":
        rect(9, 9, 21, 26, 2); rect(18, 15, 21, 26, 2)
    elif name == "refresh":
        painter.drawArc(QRectF(11, 11, 26, 26), 35 * 16, 285 * 16)
        poly([(35, 9), (39, 17), (31, 17)], True)
    elif name == "undo":
        poly([(11, 25), (22, 14)])
        line(11, 25, 22, 36)
        painter.drawArc(QRectF(17, 15, 25, 24), -80 * 16, 170 * 16)
    elif name == "search":
        circle(21, 21, 12); line(30, 30, 40, 40)
    elif name == "play":
        poly([(16, 10), (38, 24), (16, 38)], True)
    elif name == "stop":
        rect(14, 14, 20, 20, 2)
    elif name == "save_image":
        rect(8, 11, 32, 27, 2)
        circle(17, 20, 3)
        poly([(11, 35), (21, 25), (27, 31), (32, 26), (38, 33)])
    elif name == "calculator":
        rect(12, 7, 24, 35, 3)
        rect(17, 12, 14, 7, 1)
        for yy in (25, 31, 37):
            line(17, yy, 20, yy); line(24, yy, 27, yy); line(31, yy, 34, yy)
    elif name == "metadata":
        circle(24, 24, 17)
        circle(24, 14, 2.6); line(24, 21, 24, 34)
    elif name in ("close", "cancel", "error"):
        if name == "error":
            circle(24, 24, 17)
        line(16, 16, 32, 32); line(32, 16, 16, 32)
    elif name == "plugin":
        circle(24, 24, 7)
        for angle in range(0, 360, 90):
            import math
            a = math.radians(angle)
            circle(24 + 13 * math.cos(a), 24 + 13 * math.sin(a), 4.5)
    elif name == "up":
        poly([(12, 29), (24, 17), (36, 29)])
    elif name == "down":
        poly([(12, 19), (24, 31), (36, 19)])
    elif name == "chart":
        line(9, 8, 9, 39); line(9, 39, 41, 39)
        poly([(13, 33), (20, 24), (27, 29), (37, 14)])
        circle(13, 33, 2.4); circle(20, 24, 2.4); circle(27, 29, 2.4); circle(37, 14, 2.4)
    elif name == "cluster":
        circle(16, 17, 6); circle(32, 17, 6); circle(24, 33, 6)
        line(21, 20, 27, 20); line(19, 22, 22, 28); line(29, 22, 26, 28)
    elif name == "simulation":
        rect(10, 10, 28, 28, 4)
        for x, y in ((17, 17), (31, 17), (24, 24), (17, 31), (31, 31)):
            circle(x, y, 2.2)
    elif name == "warning":
        poly([(24, 7), (42, 39), (6, 39)], True)
        line(24, 17, 24, 28); circle(24, 34, 1.8)
    elif name == "info":
        circle(24, 24, 17)
        circle(24, 14, 2.6); line(24, 21, 24, 34)
    else:
        painter.end()
        return None
    painter.end()
    return pixmap


def tint_icon(icon: QIcon, color: str = "#1E3A8A") -> QIcon:
    if icon.isNull():
        return icon
    result = QIcon()
    for size in (16, 20, 24, 28, 32):
        pix = icon.pixmap(QSize(size, size))
        if not pix.isNull():
            result.addPixmap(_tinted_pixmap(pix, color))
    return result if not result.isNull() else icon


def standard_icon(name: str, color: Optional[str] = None) -> QIcon:
    """Ícone desenhado por nós, com cor fixa e contraste nos temas claro e escuro."""
    tint = color or ICON_COLORS.get(name, "#1E3A8A")
    icon = QIcon()
    for size in (20, 24, 32, 48):
        pix = _draw_custom_icon(name, tint, size)
        if pix is not None and not pix.isNull():
            icon.addPixmap(pix)
    if not icon.isNull():
        return icon
    style = QApplication.style()
    pixmap_enum = ICON_NAMES.get(name, QStyle.StandardPixmap.SP_FileIcon)
    return tint_icon(style.standardIcon(pixmap_enum), tint)


def button(text: str, icon: str = "ok", *, parent: Optional[QWidget] = None,
           primary: bool = False, danger: bool = False, tooltip: str = "",
           minimum_width: int = 0) -> QPushButton:
    btn = QPushButton(text, parent)
    from .theme import icon_size
    tint = "#FFFFFF" if primary else ("#991B1B" if danger else None)
    btn.setIcon(standard_icon(icon, tint))
    btn.setIconSize(QSize(icon_size(), icon_size()))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setProperty("primary", bool(primary))
    btn.setProperty("danger", bool(danger))
    btn.setAccessibleName(text)
    if tooltip:
        btn.setToolTip(tooltip)
    if minimum_width:
        btn.setMinimumWidth(minimum_width)
    btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    return btn


def refresh_style(widget: QWidget) -> None:
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


class Card(QFrame):
    def __init__(self, parent: Optional[QWidget] = None, *, title: str = "",
                 subtitle: str = "", accessible: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 12)
        self.body.setSpacing(9)
        if title:
            title_label = QLabel(title)
            title_label.setObjectName("SectionTitle")
            title_label.setWordWrap(True)
            self.body.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("Hint")
            subtitle_label.setWordWrap(True)
            self.body.addWidget(subtitle_label)
        if accessible:
            self.setAccessibleName(accessible)

    def add(self, widget: QWidget) -> None:
        self.body.addWidget(widget)

    def add_layout(self, layout: Any) -> None:
        self.body.addLayout(layout)


class SectionTitle(QLabel):
    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("SectionTitle")
        self.setWordWrap(True)


class Hint(QLabel):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Hint")
        self.setWordWrap(True)


class Banner(QLabel):
    def __init__(self, text: str = "", role: str = "info", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.set_role(role)

    def set_role(self, role: str) -> None:
        self.setProperty("role", role)
        refresh_style(self)

    def set_message(self, text: str, role: str = "info") -> None:
        self.setText(text)
        self.set_role(role)
        self.setVisible(bool(text))


class StatusPill(QLabel):
    def __init__(self, text: str = "", status: str = "cinza", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_status(status)

    def set_status(self, status: str, text: Optional[str] = None) -> None:
        if text is not None:
            self.setText(text)
        self.setProperty("status", status)
        refresh_style(self)


class KpiCard(QFrame):
    def __init__(self, label: str, value: str = "—", tooltip: str = "",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SubCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)
        self.label = QLabel(label)
        self.label.setObjectName("KpiLabel")
        self.label.setWordWrap(True)
        self.value = QLabel(value)
        self.value.setObjectName("KpiValue")
        self.value.setWordWrap(True)
        layout.addWidget(self.label)
        layout.addWidget(self.value)
        if tooltip:
            self.setToolTip(tooltip)
            self.label.setToolTip(tooltip)
            self.value.setToolTip(tooltip)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_value(self, text: str, tone: str = "") -> None:
        self.value.setText(text)
        color = {"green": "#166534", "yellow": "#92400E", "red": "#991B1B", "blue": "#1E3A8A"}.get(tone, "#1E3A8A")
        self.value.setStyleSheet(f"color: {color}; background: transparent;")


def make_label(text: str, *, bold: bool = False, tooltip: str = "",
               wrap: bool = False, object_name: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(wrap)
    if bold:
        font = label.font()
        font.setBold(True)
        label.setFont(font)
    if tooltip:
        label.setToolTip(tooltip)
        label.setAccessibleDescription(tooltip)
    if object_name:
        label.setObjectName(object_name)
    return label


def make_table(headers: Iterable[str], *, rows: int = 0, parent: Optional[QWidget] = None,
               editable: bool = False, stretch_last: bool = False,
               word_wrap: bool = False) -> QTableWidget:
    headers = list(headers)
    table = QTableWidget(rows, len(headers), parent)
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers if not editable else
                          (QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed |
                           QTableWidget.EditTrigger.AnyKeyPressed))
    table.setSortingEnabled(False)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setHighlightSections(False)
    table.setWordWrap(word_wrap)
    if stretch_last:
        table.horizontalHeader().setStretchLastSection(True)
    return table


def readonly_item(text: str, *, align_right: bool = False, tooltip: str = "",
                  color: Optional[str] = None, background: Optional[str] = None,
                  bold: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
    item.setFlags(flags)
    if align_right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if tooltip:
        item.setToolTip(tooltip)
    if color:
        item.setForeground(QColor(color))
    if background:
        item.setBackground(QColor(background))
    if bold:
        font = item.font()
        font.setBold(True)
        item.setFont(font)
    return item


def format_data_number(value: Any) -> str:
    if is_missing(value):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return ""
    if abs(number - round(number)) < 1e-9:
        return format_number(number, 0)
    text = format_number(number, 4)
    text = text.rstrip("0").rstrip(",")
    return text or "0"


def rows_to_table(table: QTableWidget, rows: Iterable[Iterable[Any]], *,
                  numeric_columns: Optional[Iterable[int]] = None,
                  wrap: bool = False) -> None:
    rows = [list(r) for r in rows]
    numeric_columns = set(numeric_columns or [])
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            if isinstance(value, QTableWidgetItem):
                item = value
            else:
                item = readonly_item(str(value) if value is not None else "",
                                     align_right=c in numeric_columns)
            table.setItem(r, c, item)
    table.resizeColumnsToContents()
    table.setWordWrap(wrap)


# ------------------------------------------------------------------ mensagens
def _prepare_buttons(box: QMessageBox) -> None:
    mapping = {
        QMessageBox.StandardButton.Yes: standard_icon("ok"),
        QMessageBox.StandardButton.No: standard_icon("cancel"),
        QMessageBox.StandardButton.Ok: standard_icon("ok"),
        QMessageBox.StandardButton.Cancel: standard_icon("cancel"),
        QMessageBox.StandardButton.Save: standard_icon("save"),
        QMessageBox.StandardButton.Discard: standard_icon("delete"),
        QMessageBox.StandardButton.Close: standard_icon("close"),
        QMessageBox.StandardButton.Open: standard_icon("open"),
    }
    for button_obj in box.buttons():
        standard = box.standardButton(button_obj)
        if standard in mapping:
            button_obj.setIcon(mapping[standard])
        button_obj.setMinimumHeight(44)
        button_obj.setCursor(Qt.CursorShape.PointingHandCursor)


def show_message(parent: Optional[QWidget], title: str, text: str, *,
                 kind: str = "info", button_text: str = "Entendi") -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    icons = {
        "info": QMessageBox.Icon.Information,
        "warning": QMessageBox.Icon.Warning,
        "error": QMessageBox.Icon.Critical,
        "success": QMessageBox.Icon.Information,
    }
    box.setIcon(icons.get(kind, QMessageBox.Icon.Information))
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.button(QMessageBox.StandardButton.Ok).setText(button_text)
    _prepare_buttons(box)
    box.exec()


def show_error(parent: Optional[QWidget], text: str, title: str = "Não foi possível concluir") -> None:
    show_message(parent, title, text, kind="error", button_text="Fechar")


def show_info(parent: Optional[QWidget], text: str, title: str = "SisAvalia") -> None:
    show_message(parent, title, text, kind="info")


def show_warning(parent: Optional[QWidget], text: str, title: str = "Atenção") -> None:
    show_message(parent, title, text, kind="warning")


def ask_yes_no(parent: Optional[QWidget], title: str, text: str, *,
               yes_text: str = "Sim", no_text: str = "Não", default_yes: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    yes_button = box.button(QMessageBox.StandardButton.Yes)
    no_button = box.button(QMessageBox.StandardButton.No)
    yes_button.setText(yes_text)
    no_button.setText(no_text)
    box.setDefaultButton(yes_button if default_yes else no_button)
    _prepare_buttons(box)
    return box.exec() == QMessageBox.StandardButton.Yes


def ask_save_changes(parent: Optional[QWidget], work_name: str = "") -> str:
    """Devolve 'save', 'discard' ou 'cancel'."""
    box = QMessageBox(parent)
    box.setWindowTitle("Salvar alterações?")
    box.setIcon(QMessageBox.Icon.Question)
    name = f" do trabalho “{work_name}”" if work_name else ""
    box.setText(f"Há alterações não salvas{name}. O que você quer fazer?")
    box.setInformativeText("Salvar agora evita perder o que foi feito.")
    box.setStandardButtons(
        QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
        QMessageBox.StandardButton.Cancel
    )
    box.button(QMessageBox.StandardButton.Save).setText("Salvar")
    box.button(QMessageBox.StandardButton.Discard).setText("Sair sem salvar")
    box.button(QMessageBox.StandardButton.Cancel).setText("Continuar aqui")
    box.setDefaultButton(QMessageBox.StandardButton.Save)
    _prepare_buttons(box)
    result = box.exec()
    if result == QMessageBox.StandardButton.Save:
        return "save"
    if result == QMessageBox.StandardButton.Discard:
        return "discard"
    return "cancel"


def report_unexpected_error(parent: Optional[QWidget], exc: BaseException, context: str = "") -> None:
    log_exception(context or "erro na interface", (type(exc), exc, exc.__traceback__))
    from core.app_paths import error_log_path
    show_error(
        parent,
        "O programa encontrou um problema inesperado e não conseguiu concluir esta ação. "
        "O trabalho que já estava aberto continua na tela. Se o problema repetir, salve o projeto, "
        "feche e abra o SisAvalia novamente.\n\nDetalhe técnico guardado em:\n" + str(error_log_path()),
        title="Ocorreu um problema",
    )


def safe_call(parent: Optional[QWidget], func: Any, *args: Any, context: str = "", **kwargs: Any) -> Any:
    """Executa uma ação e transforma qualquer erro em mensagem simples."""
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        report_unexpected_error(parent, exc, context)
        return None


def install_exception_hook(app: QApplication) -> None:
    _dialog_open = {"value": False}

    def _hook(exc_type: Any, exc: Any, tb: Any) -> None:
        log_exception("exceção não tratada", (exc_type, exc, tb))
        # Duas exceções seguidas (por exemplo, dois gráficos) não devem abrir
        # duas janelas idênticas sobrepostas.
        if _dialog_open["value"]:
            return
        _dialog_open["value"] = True
        try:
            box = QMessageBox()
            box.setWindowTitle("Ocorreu um problema")
            box.setIcon(QMessageBox.Icon.Critical)
            from core.app_paths import error_log_path
            box.setText(
                "O programa encontrou um problema inesperado. O trabalho atual continua aberto. "
                "Se o problema repetir, salve o projeto e abra o programa novamente.\n\n"
                "Detalhe técnico: " + str(error_log_path())
            )
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.button(QMessageBox.StandardButton.Ok).setText("Fechar")
            _prepare_buttons(box)
            box.exec()
        except Exception:
            traceback.print_exception(exc_type, exc, tb)
        finally:
            _dialog_open["value"] = False
    app.setProperty("sisavalia_exception_hook", True)
    import sys
    sys.excepthook = _hook


def set_row_height(table: QTableWidget, height: int) -> None:
    table.verticalHeader().setDefaultSectionSize(height)


def toast(widget: QWidget, text: str, ms: int = 2400) -> None:
    """Aviso curto no rodapé da janela principal, sem janela modal."""
    window = widget.window()
    status = getattr(window, "statusBar", None)
    if callable(status):
        try:
            window.statusBar().showMessage(text, ms)
            return
        except Exception as exc:
            LOGGER.debug("Mensagem de status não exibida: %s", exc)
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QToolTip
    QToolTip.showText(QCursor.pos(), text, widget)
