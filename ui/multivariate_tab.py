"""Aba 6 — K-médias e PCA."""
from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QScrollArea, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from core import charting
from core.data_manager import DataManager
from core.formatting import format_number
from core.multivariate import (
    KMeansResult, MultivariateError, PCAResult, run_kmeans, run_pca,
)
from .clipboard import copy_text, table_to_tsv
from .plots import PlotCard
from .widgets import (
    Banner, Card, Hint, button, make_table, readonly_item, show_error, show_info, toast,
)


class MultivariateTab(QWidget):
    cluster_saved = Signal()

    def __init__(self, manager: DataManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.kmeans_result: Optional[KMeansResult] = None
        self.pca_result: Optional[PCAResult] = None
        self._build_ui()
        self.set_manager(manager)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)
        title = QLabel("5. K-Médias & PCA")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        subtitle = QLabel(
            "K-médias separa os imóveis em grupos parecidos. PCA mostra quais variáveis andam juntas e "
            "resume a amostra em componentes. Use os grupos com julgamento: eles não provam nada sozinhos."
        )
        subtitle.setObjectName("Hint")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)
        self.alert = Banner("", "info")
        self.alert.setVisible(False)
        root.addWidget(self.alert)
        vars_card = Card(title="Variáveis para as duas análises",
                         subtitle="Marque pelo menos duas variáveis numéricas. Só imóveis ligados e completos entram.")
        self.var_list = QListWidget()
        self.var_list.setMaximumHeight(190)
        self.var_list.setAccessibleName("Variáveis para K-médias e PCA")
        vars_card.add(self.var_list)
        var_actions = QHBoxLayout()
        self.mark_all_button = button("Marcar todas", "add")
        self.clear_button = button("Limpar seleção", "delete")
        self.mark_all_button.clicked.connect(self._mark_all)
        self.clear_button.clicked.connect(self._clear_vars)
        var_actions.addWidget(self.mark_all_button)
        var_actions.addWidget(self.clear_button)
        var_actions.addStretch(1)
        vars_card.add_layout(var_actions)
        root.addWidget(vars_card)
        kmeans_card = Card(title="K-médias",
                           subtitle="Agrupa imóveis por semelhança. O cotovelo ajuda a escolher quantos grupos usar.")
        kmeans_controls = QHBoxLayout()
        self.standardize = QCheckBox("Padronizar as variáveis antes de agrupar (recomendado)")
        self.standardize.setChecked(True)
        self.standardize.setToolTip("Coloca todas as variáveis na mesma escala para nenhuma dominar só por ter números maiores.")
        self.k_spin = QSpinBox()
        self.k_spin.setRange(2, 10)
        self.k_spin.setValue(3)
        self.k_spin.setPrefix("K = ")
        self.k_run_button = button("Rodar K-médias", "play", primary=True)
        self.k_save_button = button("Gravar coluna Cluster", "save")
        self.k_run_button.clicked.connect(self.run_kmeans_clicked)
        self.k_save_button.clicked.connect(self.save_cluster)
        kmeans_controls.addWidget(self.standardize)
        kmeans_controls.addWidget(QLabel("Número de grupos:"))
        kmeans_controls.addWidget(self.k_spin)
        kmeans_controls.addWidget(self.k_run_button)
        kmeans_controls.addWidget(self.k_save_button)
        kmeans_controls.addStretch(1)
        kmeans_card.add_layout(kmeans_controls)
        self.kmeans_status = QLabel("Ainda não rodou.")
        self.kmeans_status.setObjectName("Hint")
        self.kmeans_status.setWordWrap(True)
        kmeans_card.add(self.kmeans_status)
        plots = QSplitter(Qt.Orientation.Horizontal)
        self.kmeans_plot = PlotCard("Grupos encontrados")
        self.elbow_plot = PlotCard("Cotovelo")
        plots.addWidget(self.kmeans_plot)
        plots.addWidget(self.elbow_plot)
        plots.setMinimumHeight(560)
        kmeans_card.add(plots)
        root.addWidget(kmeans_card)
        pca_card = Card(title="PCA — análise de componentes principais",
                        subtitle="A PCA sempre padroniza as variáveis. O gráfico de cargas mostra o peso de cada variável.")
        pca_controls = QHBoxLayout()
        self.pca_run_button = button("Rodar PCA", "play", primary=True)
        self.pca_run_button.clicked.connect(self.run_pca_clicked)
        pca_controls.addWidget(self.pca_run_button)
        pca_controls.addStretch(1)
        self.pca_status = QLabel("Ainda não rodou.")
        self.pca_status.setObjectName("Hint")
        self.pca_status.setWordWrap(True)
        pca_controls.addWidget(self.pca_status, 1)
        pca_card.add_layout(pca_controls)
        pca_split = QSplitter(Qt.Orientation.Horizontal)
        self.scree_plot = PlotCard("Scree plot — variação explicada")
        self.biplot = PlotCard("Biplot — PC1 × PC2")
        pca_split.addWidget(self.scree_plot)
        pca_split.addWidget(self.biplot)
        pca_split.setMinimumHeight(560)
        pca_card.add(pca_split)
        self.loadings_card = Card(title="Cargas das componentes",
                                  subtitle="Carga alta (para mais ou para menos) indica variável importante naquela componente.")
        self.copy_loadings_button = button("Copiar tabela", "copy")
        self.copy_loadings_button.clicked.connect(self.copy_loadings)
        load_top = QHBoxLayout()
        load_top.addStretch(1)
        load_top.addWidget(self.copy_loadings_button)
        self.loadings_card.add_layout(load_top)
        self.loadings_table = make_table(["Variável"])
        self.loadings_table.setMinimumHeight(170)
        self.loadings_card.add(self.loadings_table)
        pca_card.add(self.loadings_card)
        root.addWidget(pca_card)
        root.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        for card in (self.kmeans_plot, self.elbow_plot, self.scree_plot, self.biplot):
            card.setMinimumHeight(560)
        self.k_save_button.setEnabled(False)
        self.copy_loadings_button.setEnabled(False)

    # ------------------------------------------------------------------ dados
    def set_manager(self, manager: DataManager) -> None:
        self.manager = manager
        self.kmeans_result = None
        self.pca_result = None
        self.k_save_button.setEnabled(False)
        self.copy_loadings_button.setEnabled(False)
        self._fill_variables()
        self.kmeans_status.setText("Ainda não rodou.")
        self.pca_status.setText("Ainda não rodou.")
        self.kmeans_plot.clear_plot("Escolha as variáveis e rode K-médias.")
        self.elbow_plot.clear_plot("O cotovelo aparece depois do K-médias.")
        self.scree_plot.clear_plot("Rode a PCA para ver o scree plot.")
        self.biplot.clear_plot("Rode a PCA para ver o biplot.")
        self.loadings_table.clear()
        self.loadings_table.setRowCount(0)
        self.loadings_table.setColumnCount(0)
        self._update_alert()

    def _fill_variables(self) -> None:
        current = self._selected_variables()
        self.var_list.clear()
        numeric = self.manager.numeric_columns()
        for name in numeric:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name in current else Qt.CheckState.Unchecked)
            self.var_list.addItem(item)
        if not current:
            preferred = [s["name"] for s in self.manager.x_specs(True) if s["name"] in numeric]
            if not preferred:
                preferred = [n for n in numeric if n.lower() != "id" and not n.lower().endswith("_id")][:3]
            defaults = set(preferred[:3])
            for i in range(self.var_list.count()):
                item = self.var_list.item(i)
                item.setCheckState(Qt.CheckState.Checked if item.text() in defaults else Qt.CheckState.Unchecked)

    def _selected_variables(self) -> list[str]:
        result = []
        for i in range(self.var_list.count()):
            item = self.var_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.text())
        return result

    def _mark_all(self) -> None:
        for i in range(self.var_list.count()):
            self.var_list.item(i).setCheckState(Qt.CheckState.Checked)

    def _clear_vars(self) -> None:
        for i in range(self.var_list.count()):
            self.var_list.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _update_alert(self) -> None:
        if not self.manager.has_data():
            self.alert.setText("Importe uma planilha ou abra o exemplo para usar estas análises.")
            self.alert.set_role("warning")
            self.alert.setVisible(True)
        elif len(self.manager.numeric_columns()) < 2:
            self.alert.setText("São necessárias pelo menos duas variáveis numéricas.")
            self.alert.set_role("warning")
            self.alert.setVisible(True)
        else:
            self.alert.setVisible(False)

    # ---------------------------------------------------------------- K-médias
    def run_kmeans_clicked(self) -> None:
        variables = self._selected_variables()
        try:
            result = run_kmeans(self.manager, variables, int(self.k_spin.value()),
                                standardize=self.standardize.isChecked())
        except MultivariateError as exc:
            show_error(self, str(exc))
            return
        self.kmeans_result = result
        sizes = result.cluster_sizes()
        size_text = "; ".join(f"Grupo {k + 1}: {v} imóvel(is)" for k, v in sizes.items())
        self.kmeans_status.setText(
            f"K = {result.k} com {len(result.used_positions)} imóvel(is). {size_text}. "
            + ("Variáveis padronizadas." if result.scaled else "Variáveis na escala original.")
        )
        labels = [self.manager.label_for_row(pos) for pos in result.used_positions]
        fig, _ = charting.kmeans_scatter(result.scores_2d, result.labels,
                                         axis_labels=result.axis_labels)
        self.kmeans_plot.set_figure(fig, x_values=result.scores_2d[:, 0],
                                    y_values=result.scores_2d[:, 1], labels=labels)
        fig, _ = charting.elbow_plot(result.elbow_k, result.elbow_inertia)
        self.elbow_plot.set_figure(fig)
        self.k_save_button.setEnabled(True)
        self.alert.setVisible(False)

    def save_cluster(self) -> None:
        if self.kmeans_result is None:
            show_error(self, "Rode o K-médias antes de gravar a coluna Cluster.")
            return
        values: list[Optional[int]] = [None] * len(self.manager.df)
        for pos, label in zip(self.kmeans_result.used_positions, self.kmeans_result.labels):
            values[pos] = int(label) + 1
        try:
            column = self.manager.set_cluster_column(values)
        except ValueError as exc:
            show_error(self, str(exc))
            return
        self.cluster_saved.emit()
        show_info(
            self,
            f"A coluna “{column}” foi gravada na tabela. Imóveis que não entraram no K-médias ficaram sem grupo. "
            "Ela não entra no modelo automaticamente.",
            title="Cluster gravado",
        )

    # --------------------------------------------------------------------- PCA
    def run_pca_clicked(self) -> None:
        variables = self._selected_variables()
        try:
            result = run_pca(self.manager, variables)
        except MultivariateError as exc:
            show_error(self, str(exc))
            return
        self.pca_result = result
        explained = result.explained[:2]
        self.pca_status.setText(
            f"PCA com padronização e {result.n_obs} imóvel(is). "
            f"CP1 explica {format_number(explained[0] * 100, 1)}% e CP2 explica "
            f"{format_number((explained[1] if len(explained) > 1 else 0) * 100, 1)}% da variação."
        )
        fig, _ = charting.pca_scree(result.explained, result.cumulative)
        self.scree_plot.set_figure(fig)
        loadings = result.loadings.iloc[:, :2].to_numpy()
        fig, _ = charting.pca_biplot(result.scores, loadings, result.explained, result.variables)
        self.biplot.set_figure(fig)
        self._fill_loadings(result)

    def _fill_loadings(self, result: PCAResult) -> None:
        columns = [f"CP{i + 1}" for i in range(result.loadings.shape[1])]
        self.loadings_table.clear()
        self.loadings_table.setColumnCount(1 + len(columns))
        self.loadings_table.setHorizontalHeaderLabels(["Variável"] + columns)
        self.loadings_table.setRowCount(len(result.variables))
        for r, variable in enumerate(result.variables):
            self.loadings_table.setItem(r, 0, readonly_item(variable, bold=True))
            for c, column in enumerate(columns, start=1):
                value = float(result.loadings.loc[variable, column])
                item = readonly_item(format_number(value, 3), align_right=True)
                if abs(value) >= 0.5:
                    item.setToolTip("Carga alta nesta componente.")
                self.loadings_table.setItem(r, c, item)
        self.loadings_table.resizeColumnsToContents()
        self.copy_loadings_button.setEnabled(True)

    def copy_loadings(self) -> None:
        if self.loadings_table.rowCount() == 0:
            show_info(self, "Rode a PCA antes de copiar as cargas.")
            return
        copy_text(table_to_tsv(self.loadings_table))
        toast(self, "Cargas da PCA copiadas.")

    # ------------------------------------------------------------------ tema
    def refresh_theme(self) -> None:
        if self.kmeans_result is not None:
            result = self.kmeans_result
            labels = [self.manager.label_for_row(pos) for pos in result.used_positions]
            fig, _ = charting.kmeans_scatter(result.scores_2d, result.labels,
                                             axis_labels=result.axis_labels)
            self.kmeans_plot.set_figure(fig, x_values=result.scores_2d[:, 0],
                                        y_values=result.scores_2d[:, 1], labels=labels)
            fig, _ = charting.elbow_plot(result.elbow_k, result.elbow_inertia)
            self.elbow_plot.set_figure(fig)
        if self.pca_result is not None:
            result = self.pca_result
            fig, _ = charting.pca_scree(result.explained, result.cumulative)
            self.scree_plot.set_figure(fig)
            fig, _ = charting.pca_biplot(result.scores, result.loadings.iloc[:, :2].to_numpy(),
                                         result.explained, result.variables)
            self.biplot.set_figure(fig)
            self._fill_loadings(result)
