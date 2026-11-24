"""Diálogo de exportação do relatório."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QRadioButton, QVBoxLayout, QWidget,
)

from .dialogs import DialogBase
from .file_dialogs import save_file_name
from .widgets import button


def _safe_name(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9À-ÿ _-]+", "", text).strip()
    return text.replace(" ", "_") or "relatorio"


class ExportDialog(DialogBase):
    def __init__(self, default_title: str, default_dir: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            "Exportar relatório",
            "Escolha o título, o formato e onde guardar. O modo resumo fica em cerca de uma página.",
            parent,
            width=720,
        )
        form = QFormLayout()
        form.setSpacing(10)
        self.title_edit = QLineEdit(default_title)
        self.title_edit.setPlaceholderText("Título que aparece no relatório")
        self.pdf_radio = QRadioButton("PDF (recomendado para enviar e imprimir)")
        self.docx_radio = QRadioButton("DOCX (para editar no LibreOffice Writer)")
        self.pdf_radio.setChecked(True)
        self.summary_check = QCheckBox("Modo resumo (1 página)")
        self.summary_check.setToolTip(
            "Faz um relatório curto com equação, estimativa, intervalo, valor adotado, graus e gráfico de aderência."
        )
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Caminho do arquivo")
        self.browse_button = button("Escolher local", "save_image")
        self.browse_button.clicked.connect(self._browse)
        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.addWidget(self.path_edit, 1)
        path_layout.addWidget(self.browse_button)
        form.addRow("Título:", self.title_edit)
        form.addRow("Formato:", self.pdf_radio)
        form.addRow("", self.docx_radio)
        form.addRow("", self.summary_check)
        form.addRow("Arquivo:", path_row)
        holder = QWidget()
        holder.setLayout(form)
        self.card.add(holder)
        self.note = QLabel(
            "Se o valor adotado for diferente da estimativa, a justificativa é obrigatória. "
            "O programa avisa antes de gerar."
        )
        self.note.setObjectName("Hint")
        self.note.setWordWrap(True)
        self.card.add(self.note)
        self.default_dir = Path(default_dir)
        self._set_default_path()
        self.title_edit.textChanged.connect(self._set_default_path)
        self.pdf_radio.toggled.connect(self._format_changed)
        self.confirm_button.setText("Gerar relatório")
        self.result: Optional[dict[str, Any]] = None

    def _extension(self) -> str:
        return "pdf" if self.pdf_radio.isChecked() else "docx"

    def _set_default_path(self) -> None:
        if not hasattr(self, "path_edit"):
            return
        current = self.path_edit.text().strip()
        if current and Path(current).stem and Path(current).suffix.lower() in (".pdf", ".docx"):
            return
        title = self.title_edit.text().strip() or "relatorio"
        self.path_edit.setText(str(self.default_dir / f"{_safe_name(title)}.{self._extension()}"))

    def _format_changed(self) -> None:
        self.path_edit.setText(str(Path(self.path_edit.text().strip()).with_suffix("." + self._extension())))

    def _browse(self) -> None:
        extension = self._extension()
        filt = "PDF (*.pdf)" if extension == "pdf" else "DOCX (*.docx)"
        start = self.path_edit.text().strip() or str(self.default_dir / f"relatorio.{extension}")
        filename = save_file_name(self, "Onde guardar o relatório", start, filt, extension)
        if filename:
            path = Path(filename)
            if path.suffix.lower() != "." + extension:
                path = path.with_suffix("." + extension)
            self.path_edit.setText(str(path))

    def _confirm(self) -> None:
        title = self.title_edit.text().strip()
        if not title:
            self.show_problem("Digite um título para o relatório.")
            self.title_edit.setFocus()
            return
        path_text = self.path_edit.text().strip()
        if not path_text:
            self.show_problem("Escolha onde guardar o relatório.")
            return
        path = Path(path_text)
        extension = "." + self._extension()
        if path.suffix.lower() != extension:
            path = path.with_suffix(extension)
        self.result = {
            "title": title,
            "format": self._extension(),
            "summary": self.summary_check.isChecked(),
            "path": str(path),
        }
        self.accept()
