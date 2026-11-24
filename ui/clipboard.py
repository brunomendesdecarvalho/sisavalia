"""Cópia de textos, tabelas e gráficos para a área de transferência."""
from __future__ import annotations

import io
from typing import Any

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QTableWidget


def copy_text(text: str) -> None:
    QApplication.clipboard().setText(text)


def table_to_tsv(table: QTableWidget, *, include_headers: bool = True) -> str:
    lines: list[str] = []
    if include_headers:
        headers = []
        for col in range(table.columnCount()):
            item = table.horizontalHeaderItem(col)
            headers.append(item.text() if item is not None else "")
        lines.append("\t".join(headers))
    for row in range(table.rowCount()):
        cells = []
        for col in range(table.columnCount()):
            item = table.item(row, col)
            cells.append(item.text() if item is not None else "")
        lines.append("\t".join(cells))
    return "\n".join(lines)


def copy_table(table: QTableWidget) -> str:
    text = table_to_tsv(table)
    copy_text(text)
    return text


def copy_pixmap(pixmap: QPixmap) -> None:
    QApplication.clipboard().setPixmap(pixmap)


def copy_figure(fig: Any, dpi: int = 220) -> None:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    buffer.seek(0)
    image = QImage()
    image.loadFromData(buffer.getvalue(), "PNG")
    QApplication.clipboard().setImage(image)


def figure_to_pixmap(fig: Any, dpi: int = 220) -> QPixmap:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue(), "PNG")
    return pixmap
