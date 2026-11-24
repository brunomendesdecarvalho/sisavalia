"""Cartão de gráfico com copiar, salvar, zoom e rótulos ao apontar."""
from __future__ import annotations

import io
import logging
import math
import re
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import QSize, Qt, QTimer
from shiboken6 import isValid
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from .clipboard import copy_figure
from .file_dialogs import save_file_name

LOGGER = logging.getLogger(__name__)
from .widgets import Card, button, show_error, show_info, standard_icon, tint_icon, toast


class ResponsiveCanvas(FigureCanvasQTAgg):
    """Redesenha o layout quando o cartão muda de tamanho, evitando cortes."""

    def __init__(self, figure: Figure) -> None:
        super().__init__(figure)
        self._disposed = False
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(self._fit_layout)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if not self._disposed and isValid(self):
            self._schedule_fit()

    def _schedule_fit(self) -> None:
        if self._disposed or not isValid(self) or self._fit_timer.isActive():
            return
        self._fit_timer.start(0)

    def cancel_pending(self) -> None:
        self._disposed = True
        self._fit_timer.stop()

    def _fit_layout(self) -> None:
        if self._disposed or not isValid(self):
            return
        try:
            engine = self.figure.get_layout_engine()
            if engine is None or engine.__class__.__name__ == "TightLayoutEngine":
                self.figure.tight_layout(pad=1.15)
            self.draw_idle()
        except RuntimeError:
            return
        except Exception as exc:
            LOGGER.debug("Layout do gráfico não ajustado: %s", exc)


class HoverAnnotator:
    """Mostra o rótulo do ponto mais próximo quando o mouse passa por cima."""

    def __init__(self, canvas: FigureCanvasQTAgg, ax: Any,
                 xs: Sequence[float], ys: Sequence[float], labels: Sequence[str],
                 threshold_px: float = 14.0) -> None:
        self.canvas = canvas
        self.ax = ax
        self.xs = np.asarray(xs, dtype=float)
        self.ys = np.asarray(ys, dtype=float)
        self.labels = list(labels)
        self.threshold = threshold_px
        self.annotation = ax.annotate(
            "", xy=(0, 0), xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.45", fc="#FFFFFF", ec="#2563EB", lw=1.2, alpha=0.97),
            arrowprops=dict(arrowstyle="-", color="#2563EB", lw=1.0),
            fontsize=11, color="#0F172A", zorder=20,
        )
        self.annotation.set_visible(False)
        self._cid = canvas.mpl_connect("motion_notify_event", self._on_move)

    def _on_move(self, event: Any) -> None:
        if not isValid(self.canvas):
            return
        if event.inaxes is not self.ax or event.x is None or event.y is None:
            if self.annotation.get_visible():
                self.annotation.set_visible(False)
                self.canvas.draw_idle()
            return
        try:
            display = self.ax.transData.transform(np.column_stack([self.xs, self.ys]))
            distances = np.hypot(display[:, 0] - event.x, display[:, 1] - event.y)
            idx = int(np.argmin(distances))
        except Exception:
            return
        if not math.isfinite(float(distances[idx])) or distances[idx] > self.threshold:
            if self.annotation.get_visible():
                self.annotation.set_visible(False)
                self.canvas.draw_idle()
            return
        label = self.labels[idx] if idx < len(self.labels) else str(idx + 1)
        self.annotation.xy = (float(self.xs[idx]), float(self.ys[idx]))
        self.annotation.set_text(label)
        self.annotation.set_visible(True)
        self.canvas.draw_idle()


class PlotCard(Card):
    def __init__(self, title: str, parent: Optional[QWidget] = None, *,
                 minimum_height: int = 300) -> None:
        super().__init__(parent, title=title)
        self._figure: Optional[Figure] = None
        self._canvas: Optional[FigureCanvasQTAgg] = None
        self._toolbar: Optional[NavigationToolbar2QT] = None
        self._hover: Optional[HoverAnnotator] = None
        self._placeholder = QLabel("O gráfico aparece aqui depois do cálculo.")
        self._placeholder.setObjectName("Hint")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._placeholder.setMinimumHeight(180)
        self.body.addWidget(self._placeholder)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.copy_button = button("Copiar Imagem", "copy", tooltip="Copia o gráfico para colar em outro programa.")
        self.save_button = button("Salvar Imagem", "save_image", tooltip="Salva o gráfico em PNG com alta resolução.")
        self.copy_button.clicked.connect(self.copy_image)
        self.save_button.clicked.connect(self.save_image)
        controls.addWidget(self.copy_button)
        controls.addWidget(self.save_button)
        controls.addStretch(1)
        self.body.addLayout(controls)
        self._canvas_layout = QVBoxLayout()
        self._canvas_layout.setContentsMargins(0, 0, 0, 0)
        self.body.addLayout(self._canvas_layout, 1)
        self._last_title = title
        self.setMinimumHeight(max(minimum_height, 520))
        self.copy_button.setEnabled(False)
        self.save_button.setEnabled(False)

    @property
    def figure(self) -> Optional[Figure]:
        return self._figure

    def set_figure(self, figure: Figure, *, x_values: Optional[Sequence[float]] = None,
                   y_values: Optional[Sequence[float]] = None,
                   labels: Optional[Sequence[str]] = None) -> None:
        self.clear_canvas()
        self._placeholder.setVisible(False)
        self._figure = figure
        try:
            figure.set_layout_engine("constrained")
        except Exception:
            pass
        canvas = ResponsiveCanvas(figure)
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        canvas.setMinimumHeight(310)
        canvas.setAccessibleName(self._last_title)
        self._canvas = canvas
        self._canvas_layout.addWidget(canvas)
        toolbar = NavigationToolbar2QT(canvas, self)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setStyleSheet("QToolBar { border: none; background: #FFFFFF; padding: 2px; } QToolButton { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 5px; padding: 2px; }")
        self._toolbar = toolbar
        self._localize_toolbar(toolbar)
        if hasattr(toolbar, "locLabel"):
            toolbar.locLabel.setVisible(False)
        self._tint_toolbar(toolbar)
        QTimer.singleShot(0, lambda: self._safe_tint_toolbar(toolbar))
        self._canvas_layout.addWidget(toolbar)
        if x_values is not None and y_values is not None and len(x_values) and figure.axes:
            self._hover = HoverAnnotator(canvas, figure.axes[0], x_values, y_values,
                                         labels or [str(i + 1) for i in range(len(x_values))])
        canvas.draw_idle()
        QTimer.singleShot(0, self._safe_fit_canvas)
        self.copy_button.setEnabled(True)
        self.save_button.setEnabled(True)

    def clear_canvas(self) -> None:
        self._hover = None
        if self._canvas is not None:
            self._canvas.cancel_pending()
            self._canvas.setParent(None)
            self._canvas.deleteLater()
            self._canvas = None
        if self._toolbar is not None:
            self._toolbar.setParent(None)
            self._toolbar.deleteLater()
            self._toolbar = None
        if self._figure is not None:
            try:
                import matplotlib.pyplot as plt
                plt.close(self._figure)
            except Exception as exc:
                LOGGER.debug("Figura anterior não foi fechada: %s", exc)
            self._figure = None
        while self._canvas_layout.count():
            item = self._canvas_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def clear_plot(self, message: str = "O gráfico aparece aqui depois do cálculo.") -> None:
        self.clear_canvas()
        self._placeholder.setText(message)
        self._placeholder.setVisible(True)
        self.copy_button.setEnabled(False)
        self.save_button.setEnabled(False)

    def _safe_tint_toolbar(self, toolbar: NavigationToolbar2QT) -> None:
        if toolbar is not self._toolbar:
            return
        self._tint_toolbar(toolbar)

    @staticmethod
    def _tint_toolbar(toolbar: NavigationToolbar2QT) -> None:
        try:
            for tool_button in toolbar.findChildren(QToolButton):
                icon = tool_button.icon()
                if not icon.isNull():
                    tool_button.setIcon(tint_icon(icon, "#1E3A8A"))
        except RuntimeError:
            return

    def _safe_fit_canvas(self) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        try:
            canvas._fit_layout()
        except RuntimeError:
            return

    @staticmethod
    def _localize_toolbar(toolbar: NavigationToolbar2QT) -> None:
        translations = {
            "Home": "Início (mostrar tudo)",
            "Back": "Voltar",
            "Forward": "Avançar",
            "Pan": "Mover o gráfico",
            "Zoom": "Ampliar uma área",
            "Subplots": "Ajustar margens",
            "Customize": "Personalizar",
            "Save": "Salvar imagem",
        }
        for action in toolbar.actions():
            text = action.text() or ""
            for english, portuguese in translations.items():
                if text.startswith(english):
                    action.setText(portuguese)
                    action.setToolTip(portuguese)
                    break
            if action.toolTip() and not any(word in action.toolTip() for word in ("Início", "Voltar", "Avançar", "Mover", "Ampliar", "Ajustar", "Salvar")):
                if "home" in action.toolTip().lower():
                    action.setToolTip("Início (mostrar tudo)")
                elif "back" in action.toolTip().lower():
                    action.setToolTip("Voltar")
                elif "forward" in action.toolTip().lower():
                    action.setToolTip("Avançar")
                elif "pan" in action.toolTip().lower():
                    action.setToolTip("Mover o gráfico")
                elif "zoom" in action.toolTip().lower():
                    action.setToolTip("Ampliar uma área")
                elif "save" in action.toolTip().lower():
                    action.setToolTip("Salvar imagem")

    def _suggested_filename(self) -> str:
        name = re.sub(r"[^A-Za-z0-9À-ÿ_ -]+", "", self._last_title).strip().replace(" ", "_")
        return (name or "grafico") + ".png"

    def copy_image(self) -> None:
        if self._figure is None:
            return
        try:
            copy_figure(self._figure, dpi=240)
        except Exception as exc:
            show_error(self, "Não foi possível copiar o gráfico. Tente salvar a imagem.")
            return
        self.copy_button.setText("Imagem copiada!")
        QTimer.singleShot(1800, self._reset_copy_button)
        toast(self, "Imagem copiada. Cole no Word, no LibreOffice ou em outro programa.")

    def _reset_copy_button(self) -> None:
        try:
            self.copy_button.setText("Copiar Imagem")
        except RuntimeError:
            return

    def save_image(self) -> None:
        if self._figure is None:
            return
        default = str(Path.home() / self._suggested_filename())
        filename = save_file_name(
            self, "Salvar gráfico como imagem", default, "Imagem PNG (*.png)", "png"
        )
        if not filename:
            return
        target = Path(filename)
        if target.suffix.lower() != ".png":
            target = target.with_suffix(".png")
        try:
            self._figure.savefig(target, format="png", dpi=240, bbox_inches="tight", facecolor="white")
            show_info(self, f"Imagem salva em:\n{target}", title="Imagem salva")
        except Exception:
            show_error(self, "Não foi possível salvar a imagem. Confira a pasta escolhida.")
