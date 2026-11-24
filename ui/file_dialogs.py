"""Diálogos de arquivo não nativos, sempre com o tema claro do SisAvalia.

O diálogo nativo pode usar o tema escuro do sistema e deixar a seleção
ilegível. Usamos o diálogo do Qt com a paleta clara já aplicada.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog, QToolButton, QWidget

from .widgets import tint_icon


class ThemedFileDialog(QFileDialog):
    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        QTimer.singleShot(0, self._tint_icons)

    def _tint_icons(self) -> None:
        try:
            for button in self.findChildren(QToolButton):
                icon = button.icon()
                if not icon.isNull():
                    button.setIcon(tint_icon(icon, "#1E3A8A"))
        except RuntimeError:
            return


def _prepare(dialog: QFileDialog, title: str, start: str, filters: str, mode: str) -> None:
    dialog.setWindowTitle(title)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setViewMode(QFileDialog.ViewMode.Detail)
    dialog.setNameFilters([part.strip() for part in filters.split(";;") if part.strip()])
    start_path = Path(start)
    if start_path.is_dir():
        dialog.setDirectory(str(start_path))
    else:
        dialog.setDirectory(str(start_path.parent if start_path.parent.exists() else Path.home()))
        dialog.selectFile(start_path.name)
    dialog.setLabelText(QFileDialog.DialogLabel.LookIn, "Pasta:")
    dialog.setLabelText(QFileDialog.DialogLabel.FileName, "Nome do arquivo:")
    dialog.setLabelText(QFileDialog.DialogLabel.FileType, "Tipo de arquivo:")
    if mode == "save":
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setLabelText(QFileDialog.DialogLabel.Accept, "Salvar")
        dialog.setOption(QFileDialog.Option.DontConfirmOverwrite, False)
    else:
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setLabelText(QFileDialog.DialogLabel.Accept, "Abrir")
    dialog.setLabelText(QFileDialog.DialogLabel.Reject, "Cancelar")


def open_file_name(parent: Optional[QWidget], title: str, start: str, filters: str) -> str:
    dialog = ThemedFileDialog(parent)
    _prepare(dialog, title, start, filters, "open")
    if dialog.exec() == QFileDialog.DialogCode.Accepted:
        selected = dialog.selectedFiles()
        return selected[0] if selected else ""
    return ""


def save_file_name(parent: Optional[QWidget], title: str, start: str, filters: str,
                   default_suffix: str = "") -> str:
    dialog = ThemedFileDialog(parent)
    if default_suffix:
        dialog.setDefaultSuffix(default_suffix.lstrip("."))
    _prepare(dialog, title, start, filters, "save")
    if dialog.exec() == QFileDialog.DialogCode.Accepted:
        selected = dialog.selectedFiles()
        return selected[0] if selected else ""
    return ""
