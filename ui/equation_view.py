"""Imagem da equação, com cópia para a área de transferência e PNG."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from core.equation import equation_latex, equation_png_from_fit
from .file_dialogs import save_file_name
from .widgets import button, show_error, toast


class EquationView(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pixmap = QPixmap()
        self._latex = ""
        self._original = QPixmap()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(5)
        title = QLabel("Equação formatada (LaTeX)")
        title.setObjectName("Hint")
        layout.addWidget(title)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumHeight(62)
        self.image.setMaximumHeight(170)
        self.image.setStyleSheet("background: white; border: 1px solid #CBD5E1; border-radius: 4px;")
        self.image.setAccessibleName("Imagem da equação ajustada")
        layout.addWidget(self.image)
        self.latex_edit = QLineEdit()
        self.latex_edit.setReadOnly(True)
        self.latex_edit.setPlaceholderText("A equação em LaTeX aparece aqui.")
        self.latex_edit.setAccessibleName("Equação em LaTeX")
        layout.addWidget(self.latex_edit)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.copy_image_button = button("Copiar imagem", "copy")
        self.save_png_button = button("Salvar PNG", "save_image")
        self.copy_latex_button = button("Copiar LaTeX", "copy")
        self.copy_image_button.clicked.connect(self.copy_image)
        self.save_png_button.clicked.connect(self.save_png)
        self.copy_latex_button.clicked.connect(self.copy_latex)
        for widget in (self.copy_image_button, self.save_png_button, self.copy_latex_button):
            widget.setEnabled(False)
            actions.addWidget(widget)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.setVisible(False)

    def set_fit(self, fit: object) -> None:
        try:
            data = equation_png_from_fit(fit)  # type: ignore[arg-type]
            pixmap = QPixmap()
            if not pixmap.loadFromData(data, "PNG"):
                raise ValueError("A imagem da equação não pôde ser lida.")
        except Exception as exc:
            self.clear()
            show_error(self, f"Não foi possível desenhar a equação formatada: {exc}")
            return
        self._latex = equation_latex(fit)  # type: ignore[arg-type]
        self._original = pixmap
        self.latex_edit.setText(self._latex)
        self.latex_edit.setCursorPosition(0)
        self._scale_image()
        self.setVisible(True)
        for widget in (self.copy_image_button, self.save_png_button, self.copy_latex_button):
            widget.setEnabled(True)

    def clear(self) -> None:
        self._pixmap = QPixmap()
        self._original = QPixmap()
        self._latex = ""
        self.image.clear()
        self.latex_edit.clear()
        self.setVisible(False)
        for widget in (self.copy_image_button, self.save_png_button, self.copy_latex_button):
            widget.setEnabled(False)

    def _scale_image(self) -> None:
        if self._original.isNull():
            return
        available = max(260, self.width() - 8)
        max_height = 170
        if self._original.width() > available or self._original.height() > max_height:
            self._pixmap = self._original.scaled(
                available, max_height, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            self._pixmap = self._original
        self.image.setPixmap(self._pixmap)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._scale_image()

    def copy_image(self) -> None:
        if self._pixmap.isNull():
            return
        QApplication.clipboard().setPixmap(self._pixmap)
        toast(self, "Imagem da equação copiada.")

    def copy_latex(self) -> None:
        if not self._latex:
            return
        QApplication.clipboard().setText(self._latex)
        toast(self, "LaTeX da equação copiado.")

    def save_png(self) -> None:
        if self._original.isNull():
            return
        start = str(Path.home() / "equacao.png")
        parent = self.window()
        project_io = getattr(parent, "project_io", None)
        if project_io is not None:
            try:
                start = str(Path(project_io.get_last_directory()) / "equacao.png")
            except Exception:
                pass
        filename = save_file_name(
            self, "Salvar equação em PNG", start, "Imagem PNG (*.png)", "png"
        )
        if not filename:
            return
        target = Path(filename)
        if target.suffix.lower() != ".png":
            target = target.with_suffix(".png")
        if not self._original.save(str(target), "PNG"):
            show_error(self, "Não foi possível salvar a imagem da equação.")
            return
        toast(self, f"Equação salva em {target}.")
