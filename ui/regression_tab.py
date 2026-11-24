"""Aba 3 — regressão linear múltipla, ANOVA e sugestão de equações."""
from __future__ import annotations

import copy
import math
import threading
from typing import Any, Callable, Optional

import numpy as np
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar,
    QScrollArea, QSizePolicy, QSplitter, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core import charting
from core.data_manager import DataManager
from core.diagnostics import DiagnosticsResult
from core.evaluation import EvaluationResult
from core.formatting import format_coefficient, format_number, format_pvalue
from core.model_search import ModelSearch, SearchCancelled, SearchOutcome, SearchResult
from core.regression_engine import FitResult
from .clipboard import copy_text, table_to_tsv
from .plots import PlotCard
from .tooltips import tip
from .widgets import (
    Banner, Card, KpiCard, button, make_table, readonly_item, show_error,
    show_info, show_warning, toast,
)


class SearchWorker(QThread):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, manager: DataManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.manager = copy.deepcopy(manager)
        self._cancel_flag = threading.Event()

    def cancel(self) -> None:
        self._cancel_flag.set()

    def _cancel(self) -> bool:
        return self._cancel_flag.is_set()

    def run(self) -> None:
        try:
            search = ModelSearch(
                self.manager,
                progress=lambda done, total, message: self.progress.emit(done, total, message),
                cancel=self._cancel,
            )
            outcome = search.run()
            if outcome.cancelled:
                self.cancelled.emit()
            else:
                self.completed.emit(outcome)
        except SearchCancelled:
            self.cancelled.emit()
        except Exception as exc:
            from core.app_paths import log_exception
            log_exception("busca de equações")
            self.failed.emit(
                "A busca de equações não pôde ser concluída. Confira os dados, "
                "reduza o número de variáveis e tente de novo."
            )


class RegressionTab(QWidget):
    search_finished = Signal()

    def __init__(self, manager: DataManager, *,
                 get_evaluation: Optional[Callable[[], Optional[EvaluationResult]]] = None,
                 apply_spec: Optional[Callable[[dict[str, Any]], None]] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.get_evaluation = get_evaluation
        self.apply_spec = apply_spec
        self.fit: Optional[FitResult] = None
        self.diagnostics: Optional[DiagnosticsResult] = None
        self.search_results: list[SearchResult] = []
        self.worker: Optional[SearchWorker] = None
        self._search_revision = -1
        self._search_stale = False
        self._loading = False
        self._build_ui()
        self.set_model(None, None)
        self._load_saved_equations()

    # ------------------------------------------------------------------ visual
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)
        title = QLabel("3. Regressão & ANOVA")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        subtitle = QLabel(
            "O programa ajusta por mínimos quadrados ordinários (OLS). Escolha as variáveis na aba 1 e "
            "calcule, ou peça sugestões com base nas variáveis marcadas."
        )
        subtitle.setObjectName("Hint")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)
        actions_card = Card()
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.calc_button = button("Calcular este modelo", "calculator", primary=True,
                                  tooltip="Ajusta a equação com as variáveis e transformações da aba 1.")
        self.suggest_button = button("Sugerir equações", "search", primary=False,
                                     tooltip="Testa combinações de variáveis e transformações x, ln(x) e 1/x.")
        self.use_button = button("Usar este modelo", "ok",
                                 tooltip="Copia a equação escolhida na lista para a aba 1 e recalcula.")
        self.cancel_button = button("Cancelar busca", "stop", danger=True)
        self.cancel_button.setVisible(False)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setMinimumWidth(240)
        actions.addWidget(self.calc_button)
        actions.addWidget(self.suggest_button)
        actions.addWidget(self.use_button)
        actions.addWidget(self.progress, 1)
        actions.addWidget(self.cancel_button)
        actions_card.add_layout(actions)
        self.search_status = QLabel("A sugestão não substitui o seu julgamento.")
        self.search_status.setObjectName("Hint")
        self.search_status.setWordWrap(True)
        actions_card.add(self.search_status)
        root.addWidget(actions_card)
        self.calc_button.clicked.connect(self.calculate_clicked)
        self.suggest_button.clicked.connect(self.suggest_clicked)
        self.use_button.clicked.connect(self.use_selected_equation)
        self.cancel_button.clicked.connect(self.cancel_search)
        self.model_card = Card(title="Equação ajustada")
        eq_row = QHBoxLayout()
        self.equation_edit = QPlainTextEdit()
        self.equation_edit.setReadOnly(True)
        self.equation_edit.setMaximumHeight(86)
        self.equation_edit.setPlaceholderText("A equação aparece aqui depois do cálculo.")
        self.equation_edit.setAccessibleName("Equação ajustada")
        self.copy_equation_button = button("Copiar equação", "copy")
        self.copy_equation_button.clicked.connect(self.copy_equation)
        eq_row.addWidget(self.equation_edit, 1)
        eq_row.addWidget(self.copy_equation_button, 0, Qt.AlignmentFlag.AlignTop)
        self.model_card.add_layout(eq_row)
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self.kpi_r2 = KpiCard("R²", "—", tip("r2"))
        self.kpi_adj = KpiCard("R² ajustado", "—", tip("r2_ajustado"))
        self.kpi_se = KpiCard("Erro padrão", "—", "É o tamanho médio do erro da equação, na escala usada em Y.")
        self.kpi_n = KpiCard("Imóveis usados", "—", "Imóveis ligados com Y e todos os X preenchidos.")
        for card in (self.kpi_r2, self.kpi_adj, self.kpi_se, self.kpi_n):
            kpi_row.addWidget(card)
        self.model_card.add_layout(kpi_row)
        self.model_warning = Banner("", "warning")
        self.model_warning.setVisible(False)
        self.model_card.add(self.model_warning)
        root.addWidget(self.model_card)
        tables_split = QSplitter(Qt.Orientation.Horizontal)
        anova_card = Card(title="ANOVA", subtitle=tip("anova"))
        self.copy_anova_button = button("Copiar tabela", "copy")
        self.copy_anova_button.clicked.connect(lambda: self.copy_table(self.anova_table, "ANOVA"))
        anova_top = QHBoxLayout()
        anova_top.addStretch(1)
        anova_top.addWidget(self.copy_anova_button)
        anova_card.add_layout(anova_top)
        self.anova_table = make_table(["Fonte", "SQ", "GL", "QM", "F", "p-valor"])
        self.anova_table.setMinimumHeight(190)
        anova_card.add(self.anova_table)
        tables_split.addWidget(anova_card)
        coef_card = Card(title="Coeficientes", subtitle="Estimativa, erro padrão, t e p-valor.")
        self.copy_coef_button = button("Copiar tabela", "copy")
        self.copy_coef_button.clicked.connect(lambda: self.copy_table(self.coef_table, "coeficientes"))
        coef_top = QHBoxLayout()
        coef_top.addStretch(1)
        coef_top.addWidget(self.copy_coef_button)
        coef_card.add_layout(coef_top)
        self.coef_table = make_table(["Variável", "Estimativa", "Erro padrão", "t", "p-valor"])
        self.coef_table.horizontalHeaderItem(4).setToolTip(tip("p_valor"))
        self.coef_table.horizontalHeaderItem(3).setToolTip("Mede quantos erros padrão o coeficiente está longe de zero.")
        self.coef_table.setMinimumHeight(230)
        coef_card.add(self.coef_table)
        tables_split.addWidget(coef_card)
        tables_split.setSizes([600, 700])
        root.addWidget(tables_split)
        self.corr_card = Card(title="Matriz de correlação",
                              subtitle="Pares de X com |r| acima de 0,80 ficam em destaque: eles podem repetir informação.")
        corr_top = QHBoxLayout()
        corr_top.addStretch(1)
        self.copy_corr_button = button("Copiar tabela", "copy")
        self.copy_corr_button.clicked.connect(lambda: self.copy_table(self.corr_table, "correlação"))
        corr_top.addWidget(self.copy_corr_button)
        self.corr_card.add_layout(corr_top)
        self.corr_table = make_table([])
        self.corr_table.setMinimumHeight(180)
        self.corr_card.add(self.corr_table)
        root.addWidget(self.corr_card)
        search_card = Card(title="Equações sugeridas",
                           subtitle="Ficam guardadas as 30 melhores pelo R² ajustado. Clique numa linha e depois em Usar este modelo.")
        self.copy_suggestions_button = button("Copiar tabela", "copy")
        self.copy_suggestions_button.clicked.connect(self.copy_suggestions)
        search_top = QHBoxLayout()
        search_top.addWidget(QLabel("A sugestão não substitui o seu julgamento."))
        search_top.addStretch(1)
        search_top.addWidget(self.copy_suggestions_button)
        search_card.add_layout(search_top)
        self.search_table = make_table([
            "Equação curta", "R²", "R² ajustado", "p do F", "Pior p", "Sinais", "n", "Grau estimado",
        ])
        self.search_table.horizontalHeaderItem(1).setToolTip(tip("r2"))
        self.search_table.horizontalHeaderItem(2).setToolTip(tip("r2_ajustado"))
        self.search_table.horizontalHeaderItem(3).setToolTip(tip("p_f"))
        self.search_table.horizontalHeaderItem(4).setToolTip(tip("p_valor"))
        self.search_table.horizontalHeaderItem(7).setToolTip(tip("grau_estimado"))
        self.search_table.setMinimumHeight(270)
        self.search_table.setAccessibleName("Tabela de equações sugeridas")
        search_card.add(self.search_table)
        self.search_table.itemSelectionChanged.connect(self._search_selection_changed)
        self.search_table.doubleClicked.connect(lambda _idx: self.use_selected_equation())
        root.addWidget(search_card)
        curve_card = Card(title="Curva e elasticidade")
        curve_card.setToolTip(tip("elasticidade"))
        curve_controls = QHBoxLayout()
        curve_controls.setSpacing(8)
        curve_controls.addWidget(QLabel("Variável da curva:"))
        self.curve_combo = QComboBox()
        self.curve_combo.setMinimumWidth(220)
        self.curve_combo.currentIndexChanged.connect(self.update_curve)
        curve_controls.addWidget(self.curve_combo)
        self.curve_base_label = QLabel("As outras variáveis ficam na média dos imóveis ligados.")
        self.curve_base_label.setObjectName("Hint")
        self.curve_base_label.setWordWrap(True)
        curve_controls.addWidget(self.curve_base_label, 1)
        curve_card.add_layout(curve_controls)
        self.curve_warning = Banner("", "error")
        self.curve_warning.setVisible(False)
        curve_card.add(self.curve_warning)
        self.elasticity_label = QLabel("As elasticidades aparecem depois do cálculo.")
        self.elasticity_label.setWordWrap(True)
        self.elasticity_label.setObjectName("Hint")
        curve_card.add(self.elasticity_label)
        root.addWidget(curve_card)
        plots_split = QSplitter(Qt.Orientation.Horizontal)
        self.fit_plot = PlotCard("Aderência: observado × estimado")
        self.curve_plot = PlotCard("Curva da função")
        plots_split.addWidget(self.fit_plot)
        plots_split.addWidget(self.curve_plot)
        plots_split.setSizes([650, 650])
        plots_split.setMinimumHeight(560)
        root.addWidget(plots_split, 1)
        root.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self.fit_plot.setMinimumHeight(560)
        self.curve_plot.setMinimumHeight(560)
        self.search_table.horizontalHeader().setStretchLastSection(False)

    # ------------------------------------------------------------------ modelo
    def set_manager(self, manager: DataManager) -> None:
        self.shutdown()
        self.manager = manager
        self._search_stale = False
        self.set_model(None, None)
        self.search_results = []
        self.search_table.setRowCount(0)
        self.use_button.setEnabled(False)
        self._load_saved_equations()

    def set_model(self, fit: Optional[FitResult], diagnostics: Optional[DiagnosticsResult]) -> None:
        self.fit = fit
        self.diagnostics = diagnostics
        enabled = fit is not None
        for widget in (self.copy_equation_button, self.copy_anova_button, self.copy_coef_button,
                       self.copy_corr_button):
            widget.setEnabled(enabled)
        if fit is None:
            self.equation_edit.setPlainText("")
            self.kpi_r2.set_value("—")
            self.kpi_adj.set_value("—")
            self.kpi_se.set_value("—")
            self.kpi_n.set_value("—")
            self.model_warning.setVisible(False)
            self.anova_table.setRowCount(0)
            self.coef_table.setRowCount(0)
            self.corr_table.setRowCount(0)
            self.corr_table.setColumnCount(0)
            self.fit_plot.clear_plot("Calcule o modelo para ver a aderência.")
            self.curve_plot.clear_plot("Calcule o modelo para ver a curva.")
            self.curve_combo.blockSignals(True)
            self.curve_combo.clear()
            self.curve_combo.blockSignals(False)
            self.curve_warning.setVisible(False)
            self.elasticity_label.setText("As elasticidades aparecem depois do cálculo.")
            return
        self.equation_edit.setPlainText(fit.equation)
        self.kpi_r2.set_value(format_number(fit.rsquared, 4))
        self.kpi_adj.set_value(format_number(fit.rsquared_adj, 4))
        self.kpi_se.set_value(format_number(fit.scale, 4))
        self.kpi_n.set_value(f"{fit.n_obs}" + (f" (de {fit.n_active})" if fit.n_active != fit.n_obs else ""))
        warnings = list(fit.warnings)
        if fit.dropped_positions:
            warnings.append(
                f"{len(fit.dropped_positions)} imóvel(is) ligado(s) saíram deste cálculo por vazio em Y ou X."
            )
        if warnings:
            self.model_warning.setText("\n".join("• " + w for w in warnings))
            self.model_warning.set_role("warning")
            self.model_warning.setVisible(True)
        else:
            self.model_warning.setVisible(False)
        self._fill_anova(fit)
        self._fill_coefficients(fit)
        self._fill_correlation(fit)
        self._fill_fit_plot(fit)
        self._fill_curve_combo(fit)
        self.update_curve()
        self.copy_equation_button.setEnabled(True)

    def _fill_anova(self, fit: FitResult) -> None:
        self.anova_table.setRowCount(len(fit.anova_rows))
        for r, row in enumerate(fit.anova_rows):
            cells = [
                row["Fonte"], format_number(row["SQ"], 4), str(row["GL"]),
                format_number(row["QM"], 4), format_number(row["F"], 3),
                format_pvalue(row["p-valor"]),
            ]
            for c, value in enumerate(cells):
                item = readonly_item(str(value), align_right=c in (1, 2, 3, 4, 5))
                self.anova_table.setItem(r, c, item)
        self.anova_table.resizeColumnsToContents()

    def _fill_coefficients(self, fit: FitResult) -> None:
        self.coef_table.setRowCount(len(fit.design_names) + 1)
        names = ["Intercepto"] + list(fit.design_names)
        for r, (name, key) in enumerate(zip(names, ["const"] + list(fit.design_names))):
            values = [
                name,
                format_coefficient(fit.params[key]),
                format_number(fit.bse[key], 4),
                format_number(fit.tvalues[key], 3),
                format_pvalue(fit.pvalues[key]),
            ]
            for c, value in enumerate(values):
                item = readonly_item(str(value), align_right=c > 0)
                if key != "const" and fit.pvalues[key] <= 0.05:
                    item.setForeground(QColor("#166534"))
                self.coef_table.setItem(r, c, item)
        self.coef_table.resizeColumnsToContents()

    def _fill_correlation(self, fit: FitResult) -> None:
        corr = fit.correlation
        names = list(corr.columns)
        self.corr_table.clear()
        self.corr_table.setRowCount(len(names))
        self.corr_table.setColumnCount(len(names) + 1)
        self.corr_table.setHorizontalHeaderLabels(["Variável"] + names)
        self.corr_table.setVerticalHeaderLabels(names)
        self.corr_table.verticalHeader().setVisible(True)
        for r, row_name in enumerate(names):
            self.corr_table.setItem(r, 0, readonly_item(row_name, bold=True))
            for c, col_name in enumerate(names, start=1):
                try:
                    value = float(corr.iloc[r, c - 1])
                except Exception:
                    value = float("nan")
                item = readonly_item(format_number(value, 3), align_right=True)
                if r != c - 1 and math.isfinite(value) and abs(value) > 0.80:
                    item.setBackground(QColor("#FEF3C7"))
                    item.setForeground(QColor("#92400E"))
                    item.setToolTip("Correlação alta entre X. Veja se uma variável está repetindo a outra.")
                self.corr_table.setItem(r, c, item)
        self.corr_table.resizeColumnsToContents()
        self.corr_table.setMinimumHeight(min(420, 70 + 30 * len(names)))

    def _fill_fit_plot(self, fit: FitResult) -> None:
        fig, _ = charting.fit_scatter(fit.observed_original, fit.fitted_original, fit.labels)
        self.fit_plot.set_figure(fig, x_values=fit.fitted_original, y_values=fit.observed_original,
                                 labels=fit.labels)

    def _fill_curve_combo(self, fit: FitResult) -> None:
        self.curve_combo.blockSignals(True)
        current = self.curve_combo.currentData()
        self.curve_combo.clear()
        for name, transform in zip(fit.x_names, fit.x_transforms):
            self.curve_combo.addItem(f"{name} ({transform})", name)
        if current:
            idx = self.curve_combo.findData(current)
            if idx >= 0:
                self.curve_combo.setCurrentIndex(idx)
        self.curve_combo.blockSignals(False)

    def update_curve(self) -> None:
        if self.fit is None:
            return
        variable = self.curve_combo.currentData()
        if not variable:
            return
        result = self.get_evaluation() if self.get_evaluation else None
        base: dict[str, float] = {}
        source = "média dos imóveis ligados"
        if result is not None and all(name in result.values for name in self.fit.x_names):
            base = dict(result.values)
            source = f"avaliando “{result.name}”"
        else:
            for name in self.fit.x_names:
                values = []
                for pos in self.fit.used_positions:
                    raw = self.manager.df.iloc[pos][name]
                    try:
                        values.append(float(raw))
                    except (TypeError, ValueError):
                        continue
                base[name] = float(np.mean(values)) if values else 0.0
        self.curve_base_label.setText(f"As outras variáveis ficam no ponto: {source}.")
        try:
            curve = self.fit.curve(variable, base)
        except Exception:
            self.curve_plot.clear_plot("Não foi possível desenhar a curva desta variável.")
            self.curve_warning.setVisible(False)
            return
        if curve.empty:
            self.curve_plot.clear_plot("Não há faixa suficiente para desenhar a curva.")
            self.curve_warning.setVisible(False)
            return
        idx = self.fit.x_names.index(variable)
        inverted = self.fit._inverted(variable)
        warning = ""
        if inverted:
            warning = "Sinal invertido em relação ao esperado"
            self.curve_warning.setText(
                "A equação vai no sentido contrário ao sinal que você esperava para esta variável. "
                "O coeficiente não foi forçado."
            )
            self.curve_warning.setVisible(True)
        else:
            self.curve_warning.setVisible(False)
        point = None
        if result is not None and variable in result.values:
            point = (float(result.values[variable]), float(result.prediction.point))
        fig, _ = charting.curve_plot(curve["x"].to_numpy(), curve["y"].to_numpy(),
                                     variable=variable, point=point, warning=warning)
        self.curve_plot.set_figure(fig)
        try:
            rows = self.fit.elasticity_rows(base)
            header = "Elasticidades no ponto do avaliando:" if result is not None else "Elasticidades no ponto médio:"
            lines = [header] + ["• " + row["text"] for row in rows]
            self.elasticity_label.setText("\n".join(lines))
        except Exception:
            self.elasticity_label.setText("Não foi possível calcular as elasticidades neste ponto.")

    # ---------------------------------------------------------------- sugestões
    def calculate_clicked(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            show_info(self, "Espere a busca de equações terminar ou cancele.")
            return
        if hasattr(self, "calculate_callback") and self.calculate_callback:
            self.calculate_callback()
        elif hasattr(self.window(), "recalculate_model"):
            self.window().recalculate_model(show_errors=True)

    def suggest_clicked(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        errors, _warnings = self.manager.validate()
        if errors:
            show_error(self, "\n".join(errors[:4]))
            return
        if not self.manager.x_specs(True):
            show_warning(self, "Marque na aba 1 as variáveis que podem entrar na equação.")
            return
        self._search_revision = self.manager.revision
        self._search_stale = False
        self.suggest_button.setEnabled(False)
        self.calc_button.setEnabled(False)
        self.use_button.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.search_status.setText("Preparando a busca de equações...")
        worker = SearchWorker(self.manager, self)
        self.worker = worker
        worker.progress.connect(self._search_progress)
        worker.completed.connect(self._search_completed)
        worker.cancelled.connect(self._search_cancelled)
        worker.failed.connect(self._search_failed)
        worker.finished.connect(self._search_thread_finished)
        worker.start()

    def _search_progress(self, done: int, total: int, message: str) -> None:
        total = max(total, 1)
        self.progress.setMaximum(total)
        self.progress.setValue(min(done, total))
        self.search_status.setText(f"{message} {done} de cerca de {total} ajustes testados.")

    def _search_completed(self, outcome: SearchOutcome) -> None:
        self.search_results = outcome.results
        self._search_stale = self.manager.revision != self._search_revision
        if not self._search_stale:
            self.manager.saved_equations = [r.as_dict() for r in outcome.results]
        self._fill_search_table()
        if self._search_stale:
            self.search_status.setText(
                "Os dados ou a configuração mudaram durante a busca. As sugestões são da versão anterior "
                "e foram bloqueadas. Rode a busca de novo com os dados atuais."
            )
            show_warning(
                self,
                "Os dados mudaram durante a busca. As sugestões foram mantidas apenas para consulta, "
                "mas não podem ser aplicadas. Rode a busca novamente.",
            )
        else:
            self.search_status.setText(
                f"Busca {outcome.mode} concluída: {outcome.tested} ajuste(s) testado(s). "
                "As 30 melhores estão na tabela. A sugestão não substitui o seu julgamento."
            )
        self.progress.setValue(self.progress.maximum())
        if not self._search_stale:
            self.search_finished.emit()
        if not outcome.results:
            show_warning(self, "Nenhuma equação válida foi encontrada com estas variáveis. "
                               "Confira vazios, sinais e transformações.")

    def _search_cancelled(self) -> None:
        self.search_status.setText("Busca cancelada. Nenhuma sugestão nova foi guardada.")
        self.progress.setVisible(False)
        self.cancel_button.setVisible(False)
        self.suggest_button.setEnabled(True)
        self.calc_button.setEnabled(True)

    def _search_failed(self, message: str) -> None:
        self.search_status.setText("A busca não foi concluída.")
        self.progress.setVisible(False)
        self.cancel_button.setVisible(False)
        self.suggest_button.setEnabled(True)
        self.calc_button.setEnabled(True)
        show_error(self, message or "A busca de equações não pôde ser concluída. Tente com menos variáveis.")

    def _search_thread_finished(self) -> None:
        if self.progress.value() >= self.progress.maximum() or not self.cancel_button.isVisible():
            self.progress.setVisible(False)
        self.cancel_button.setVisible(False)
        self.suggest_button.setEnabled(True)
        self.calc_button.setEnabled(True)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
        self._search_selection_changed()

    def cancel_search(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.search_status.setText("Cancelando a busca no próximo passo...")
            self.cancel_button.setEnabled(False)

    def _fill_search_table(self) -> None:
        self.search_table.setRowCount(len(self.search_results))
        self.search_table.blockSignals(True)
        for r, result in enumerate(self.search_results):
            sigla = result.degree
            values = [
                result.equation,
                format_number(result.r2, 4),
                format_number(result.r2_adj, 4),
                format_pvalue(result.f_p),
                format_pvalue(result.worst_p),
                result.signs,
                str(result.n),
                sigla,
            ]
            for c, value in enumerate(values):
                item = readonly_item(str(value), align_right=c in (1, 2, 3, 4, 6, 7))
                item.setToolTip("A sugestão não substitui o seu julgamento.")
                if c == 7:
                    color = {"III": "#166534", "II": "#92400E", "I": "#991B1B"}.get(sigla, "#475569")
                    item.setForeground(QColor(color))
                self.search_table.setItem(r, c, item)
        self.search_table.blockSignals(False)
        self.search_table.resizeColumnsToContents()
        self.search_table.setColumnWidth(0, max(320, self.search_table.columnWidth(0)))
        self.search_table.setColumnWidth(5, max(120, self.search_table.columnWidth(5)))
        self.copy_suggestions_button.setEnabled(bool(self.search_results))
        self._search_selection_changed()

    def _load_saved_equations(self) -> None:
        try:
            self.search_results = [SearchResult.from_dict(x) for x in self.manager.saved_equations]
        except Exception:
            self.search_results = []
        self._fill_search_table()
        if self.search_results:
            self.search_status.setText(
                "Estas sugestões foram guardadas no projeto. A sugestão não substitui o seu julgamento."
            )

    def _search_selection_changed(self) -> None:
        has_selection = bool(self.search_table.selectionModel().selectedRows()) if hasattr(self, "search_table") else False
        running = self.worker is not None and self.worker.isRunning()
        self.use_button.setEnabled(has_selection and not running and not self._search_stale)

    def use_selected_equation(self) -> None:
        rows = self.search_table.selectionModel().selectedRows()
        if self._search_stale:
            show_warning(self, "A amostra mudou depois da busca. Rode a busca de novo antes de usar uma equação.")
            return
        if not rows:
            show_info(self, "Clique primeiro numa equação da lista.")
            return
        index = rows[0].row()
        if not (0 <= index < len(self.search_results)):
            return
        result = self.search_results[index]
        if self.apply_spec is None:
            show_error(self, "A janela principal não está pronta para aplicar a equação.")
            return
        self.apply_spec(result.spec)
        self.search_status.setText(
            f"Equação aplicada na aba 1. R² ajustado = {format_number(result.r2_adj, 4)}. "
            "A sugestão não substitui o seu julgamento."
        )
        toast(self, "Equação aplicada na aba 1 e recalculada.")

    def copy_suggestions(self) -> None:
        if self.search_table.rowCount() == 0:
            show_info(self, "Ainda não há sugestões para copiar.")
            return
        copy_text(table_to_tsv(self.search_table))
        toast(self, "Tabela de sugestões copiada.")

    # ------------------------------------------------------------------- cópia
    def copy_equation(self) -> None:
        text = self.equation_edit.toPlainText().strip()
        if not text:
            show_info(self, "Ainda não há equação para copiar.")
            return
        copy_text(text)
        toast(self, "Equação copiada.")

    def copy_table(self, table: Any, name: str) -> None:
        if table.rowCount() == 0:
            show_info(self, f"Ainda não há tabela de {name} para copiar.")
            return
        copy_text(table_to_tsv(table))
        toast(self, f"Tabela de {name} copiada.")

    # -------------------------------------------------------------- integração
    def set_evaluation(self, result: Optional[EvaluationResult]) -> None:
        self.update_curve()

    def mark_stale(self) -> None:
        if self.search_results:
            self._search_stale = True
        if self.fit is not None:
            self.search_status.setText(
                "Os dados mudaram. Clique em Calcular este modelo para atualizar a equação."
            )
        if self.search_results:
            self.search_status.setText(
                "Os dados mudaram depois destas sugestões. Rode a busca de novo antes de usar uma equação."
            )
        self._search_selection_changed()

    def shutdown(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)

    def refresh_theme(self) -> None:
        if self.fit is not None:
            self.set_model(self.fit, self.diagnostics)
        self._fill_search_table()
        for table in (self.anova_table, self.coef_table, self.corr_table, self.search_table):
            table.resizeRowsToContents()
