"""Aba 2 — estatísticas descritivas e gráficos exploratórios."""
from __future__ import annotations

from typing import Any, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QScrollArea, QSplitter,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from core import charting
from core.data_manager import TEXT_TYPE, DataManager
from core.formatting import format_number, is_missing
from core.evaluation import EvaluationResult
from .clipboard import copy_text
from .plots import PlotCard
from .widgets import (
    Banner, Card, button, make_table, readonly_item, show_info, toast,
)


class ExploreTab(QWidget):
    def __init__(self, manager: DataManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self._loading = False
        self.evaluation: Optional[EvaluationResult] = None
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)
        title = QLabel("2. Explorar")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        subtitle = QLabel(
            "Confira a faixa dos dados, os vazios e os pontos muito diferentes antes de montar a equação. "
            "Passe o mouse sobre um ponto para ver o imóvel."
        )
        subtitle.setObjectName("Hint")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)
        self.alert = Banner("", "warning")
        self.alert.setVisible(False)
        root.addWidget(self.alert)
        stats_card = Card(title="Estatísticas descritivas",
                          subtitle="Somente imóveis ligados. Vazios são contados, mas não entram nas contas.")
        stats_actions = QHBoxLayout()
        stats_actions.addStretch(1)
        self.copy_stats_button = button("Copiar tabela", "copy")
        self.copy_stats_button.clicked.connect(self.copy_stats)
        stats_actions.addWidget(self.copy_stats_button)
        stats_card.add_layout(stats_actions)
        self.stats_table = make_table(
            ["Variável", "Mínimo", "Máximo", "Média", "Mediana", "Desvio padrão", "Vazios"],
        )
        self.stats_table.setMinimumHeight(180)
        self.stats_table.setMaximumHeight(300)
        stats_card.add(self.stats_table)
        root.addWidget(stats_card)
        controls_card = Card(title="Gráficos")
        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(QLabel("Dispersão — X:"))
        self.scatter_x = QComboBox()
        self.scatter_x.setMinimumWidth(150)
        controls.addWidget(self.scatter_x)
        controls.addWidget(QLabel("Y:"))
        self.scatter_y = QComboBox()
        self.scatter_y.setMinimumWidth(150)
        controls.addWidget(self.scatter_y)
        controls.addSpacing(18)
        controls.addWidget(QLabel("Histograma de:"))
        self.hist_var = QComboBox()
        self.hist_var.setMinimumWidth(150)
        controls.addWidget(self.hist_var)
        controls.addStretch(1)
        controls_card.add_layout(controls)
        root.addWidget(controls_card)
        plots_split = QSplitter(Qt.Orientation.Horizontal)
        plots_split.setChildrenCollapsible(False)
        self.scatter_plot = PlotCard("Dispersão X × Y")
        self.hist_plot = PlotCard("Histograma")
        plots_split.addWidget(self.scatter_plot)
        plots_split.addWidget(self.hist_plot)
        plots_split.setSizes([650, 650])
        plots_split.setMinimumHeight(560)
        root.addWidget(plots_split, 1)
        root.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self.scatter_x.currentIndexChanged.connect(self.refresh_plots)
        self.scatter_y.currentIndexChanged.connect(self.refresh_plots)
        self.hist_var.currentIndexChanged.connect(self.refresh_plots)
        self.scatter_plot.setMinimumHeight(560)
        self.hist_plot.setMinimumHeight(560)

    # --------------------------------------------------------------- carga
    def set_manager(self, manager: DataManager) -> None:
        self.manager = manager
        self.evaluation = None
        self.refresh()

    def set_evaluation(self, result: Optional[EvaluationResult]) -> None:
        self.evaluation = result
        self.refresh_plots()

    def refresh(self) -> None:
        self._loading = True
        try:
            self._fill_combos()
            self._fill_stats()
            self._update_alert()
        finally:
            self._loading = False
        self.refresh_plots()

    def _fill_combos(self) -> None:
        numeric = self.manager.numeric_columns()
        for combo in (self.scatter_x, self.scatter_y, self.hist_var):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(numeric)
            combo.blockSignals(False)
        preferred_x = None
        for spec in self.manager.x_specs(True):
            if spec["name"] in numeric:
                preferred_x = spec["name"]
                break
        if preferred_x is None:
            for name in numeric:
                low = name.lower()
                if name == self.manager.y_column or low == "id" or low.endswith("_id"):
                    continue
                preferred_x = name
                break
        if preferred_x:
            self.scatter_x.setCurrentText(preferred_x)
            self.hist_var.setCurrentText(preferred_x)
        if self.manager.y_column in numeric:
            self.scatter_y.setCurrentText(self.manager.y_column)
        elif numeric:
            self.scatter_y.setCurrentIndex(len(numeric) - 1)

    def _fill_stats(self) -> None:
        rows = []
        mask = self.manager.active_mask()
        for column in self.manager.numeric_columns():
            values = pd.to_numeric(self.manager.df[column], errors="coerce")
            active_values = values[mask]
            valid = active_values.dropna()
            empty = int(active_values.isna().sum())
            if len(valid) == 0:
                rows.append((column, "—", "—", "—", "—", "—", str(empty)))
                continue
            std = valid.std(ddof=1) if len(valid) > 1 else float("nan")
            rows.append((
                column,
                format_number(valid.min(), 2),
                format_number(valid.max(), 2),
                format_number(valid.mean(), 2),
                format_number(valid.median(), 2),
                format_number(std, 2),
                str(empty),
            ))
        self.stats_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = readonly_item(str(value), align_right=c > 0)
                if c == 6 and value != "0":
                    item.setForeground(QColor("#92400E"))
                    item.setBackground(QColor("#FEF3C7"))
                    item.setToolTip("Há células vazias nos imóveis ligados.")
                self.stats_table.setItem(r, c, item)
        self.stats_table.resizeColumnsToContents()
        self.copy_stats_button.setEnabled(bool(rows))

    def _update_alert(self) -> None:
        messages: list[str] = []
        mask = self.manager.active_mask()
        total_empty = 0
        for column in self.manager.numeric_columns():
            values = pd.to_numeric(self.manager.df[column], errors="coerce")[mask]
            total_empty += int(values.isna().sum())
        text_cols = self.manager.text_columns()
        if total_empty:
            messages.append(
                f"Há {total_empty} célula(s) vazia(s) nas colunas numéricas dos imóveis ligados. "
                "Elas não entram nas contas e podem reduzir a amostra."
            )
        if text_cols:
            messages.append(
                f"Há {len(text_cols)} coluna(s) de texto (não numérica): "
                + ", ".join(text_cols[:5])
                + (". Elas não entram no modelo." if len(text_cols) <= 5 else ", ... Elas não entram no modelo.")
            )
        if self.manager.n_active == 0:
            messages.append("Todos os imóveis estão desligados. Reative na aba 1 para ver os gráficos.")
        if messages:
            self.alert.setText("\n".join("• " + m for m in messages))
            self.alert.set_role("warning")
            self.alert.setVisible(True)
        else:
            self.alert.setText("Nenhum vazio nas colunas numéricas dos imóveis ligados.")
            self.alert.set_role("success")
            self.alert.setVisible(True)

    def copy_stats(self) -> None:
        if self.stats_table.rowCount() == 0:
            show_info(self, "Ainda não há estatísticas para copiar.")
            return
        from .clipboard import table_to_tsv
        copy_text(table_to_tsv(self.stats_table))
        toast(self, "Tabela de estatísticas copiada.")

    # --------------------------------------------------------------- gráficos
    def refresh_plots(self) -> None:
        if self._loading:
            return
        self._plot_scatter()
        self._plot_hist()

    def _plot_scatter(self) -> None:
        x_name = self.scatter_x.currentText()
        y_name = self.scatter_y.currentText()
        mask = self.manager.active_mask()
        if not x_name or not y_name:
            self.scatter_plot.clear_plot("Escolha as variáveis para ver a dispersão.")
            return
        x_all = pd.to_numeric(self.manager.df[x_name], errors="coerce")
        y_all = pd.to_numeric(self.manager.df[y_name], errors="coerce")
        valid = mask & x_all.notna().to_numpy() & y_all.notna().to_numpy()
        positions = [i for i in range(len(self.manager.df)) if valid[i]]
        if len(positions) < 2:
            self.scatter_plot.clear_plot("Poucos imóveis ligados com as duas variáveis preenchidas.")
            return
        xs = x_all.iloc[positions].to_numpy(dtype=float)
        ys = y_all.iloc[positions].to_numpy(dtype=float)
        labels = [self.manager.label_for_row(i) for i in positions]
        fig, ax = charting.new_figure()
        ax.scatter(xs, ys, s=60, color=charting.PRIMARY, alpha=0.85,
                   edgecolor="white", linewidth=0.9, zorder=3, label="Imóveis")
        x_min, x_max = float(np.min(xs)), float(np.max(xs))
        ax.axvline(x_min, color=charting.GRAY, linewidth=1.0, linestyle=":")
        ax.axvline(x_max, color=charting.GRAY, linewidth=1.0, linestyle=":")
        hover_x = list(xs)
        hover_y = list(ys)
        hover_labels = list(labels)
        if self.evaluation is not None and x_name in self.evaluation.values:
            px = float(self.evaluation.values[x_name])
            py = float(self.evaluation.prediction.point)
            ax.scatter([px], [py], marker="*", s=300, color=charting.RED,
                       edgecolor="white", linewidth=1.2, zorder=6,
                       label=f"Avaliando: {self.evaluation.name}")
            ax.annotate(
                "Avaliando", xy=(px, py), xytext=(12, 16), textcoords="offset points",
                color=charting.RED, fontsize=13, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.32", fc="#FFF1F2", ec=charting.RED),
                arrowprops=dict(arrowstyle="-", color=charting.RED),
            )
            hover_x.append(px)
            hover_y.append(py)
            hover_labels.append(f"Avaliando: {self.evaluation.name} (projetado)")
        charting.tidy(ax, title=f"Dispersão: {x_name} × {y_name}",
                      xlabel=x_name, ylabel=y_name, x_values=xs, y_values=ys)
        ax.legend(loc="best")
        fig.tight_layout()
        self.scatter_plot.set_figure(fig, x_values=hover_x, y_values=hover_y, labels=hover_labels)

    def refresh_theme(self) -> None:
        self.refresh_plots()

    def _plot_hist(self) -> None:
        name = self.hist_var.currentText()
        if not name:
            self.hist_plot.clear_plot("Escolha uma variável para o histograma.")
            return
        values = pd.to_numeric(self.manager.df[name], errors="coerce")[self.manager.active_mask()].dropna()
        if len(values) < 1:
            self.hist_plot.clear_plot("Não há valores ligados para esta variável.")
            return
        fig, _ = charting.histogram(values.to_numpy(dtype=float),
                                    title=f"Histograma de {name}", xlabel=name)
        self.hist_plot.set_figure(fig)
