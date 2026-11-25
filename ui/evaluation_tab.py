"""Aba 4 — projeção dos avaliandos e enquadramento na NBR 14653-2."""
from __future__ import annotations

import math
from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QScrollArea, QStackedWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from core.data_manager import DataManager
from core.evaluation import EvaluationResult, evaluate_item, round_to_one_percent
from core.formatting import format_number, format_pvalue, parse_number
from core.nbr14653 import item_phrase, grade_phrase
from core.regression_engine import FitResult, ModelError
from .clipboard import copy_text, table_to_tsv
from .dialogs import EvaluatedDialog
from .tooltips import tip
from .widgets import (
    Banner, Card, Hint, KpiCard, SectionTitle, StatusPill, button, make_table,
    readonly_item, refresh_style, show_error, show_info, show_warning, toast, ask_yes_no,
)


class EvaluationTab(QWidget):
    selection_changed = Signal()
    evaluation_changed = Signal()

    def __init__(self, manager: DataManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.fit: Optional[FitResult] = None
        self.evaluations: list[EvaluationResult] = []
        self.selected_id: Optional[str] = None
        self._loading = False
        self._build_ui()
        self.set_manager(manager)

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
        title = QLabel("4. Avaliando & NBR 14653")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        subtitle = QLabel(
            "Inclua os imóveis que serão avaliados. O programa projeta o valor, mostra o intervalo de confiança "
            "de 80% e faz uma conta simplificada dos graus. A decisão final é sempre do avaliador."
        )
        subtitle.setObjectName("Hint")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)
        self.top_banner = Banner("", "info")
        self.top_banner.setVisible(False)
        root.addWidget(self.top_banner)
        self.category_banner = Banner("", "warning")
        self.category_banner.setVisible(False)
        root.addWidget(self.category_banner)
        list_card = Card(title="Imóveis avaliandos",
                         subtitle="Cada linha mostra os valores informados e o resultado da projeção.")
        list_actions = QHBoxLayout()
        self.add_button = button("Incluir avaliando", "add", primary=True)
        self.edit_button = button("Editar selecionado", "edit")
        self.delete_button = button("Excluir selecionado", "delete", danger=True)
        self.copy_list_button = button("Copiar tabela", "copy")
        self.add_button.clicked.connect(self.add_evaluated)
        self.edit_button.clicked.connect(self.edit_evaluated)
        self.delete_button.clicked.connect(self.delete_evaluated)
        self.copy_list_button.clicked.connect(self.copy_list)
        list_actions.addWidget(self.add_button)
        list_actions.addWidget(self.edit_button)
        list_actions.addWidget(self.delete_button)
        list_actions.addStretch(1)
        list_actions.addWidget(self.copy_list_button)
        list_card.add_layout(list_actions)
        self.list_table = make_table(["Avaliando"])
        self.list_table.setMinimumHeight(180)
        self.list_table.setMaximumHeight(300)
        self.list_table.itemSelectionChanged.connect(self._table_selection_changed)
        self.list_table.doubleClicked.connect(lambda _idx: self.edit_evaluated())
        list_card.add(self.list_table)
        self.list_hint = QLabel("Nenhum avaliando incluído ainda. Clique em Incluir avaliando.")
        self.list_hint.setObjectName("Hint")
        self.list_hint.setWordWrap(True)
        list_card.add(self.list_hint)
        root.addWidget(list_card)
        self.detail_stack = QStackedWidget()
        placeholder = Card(title="Selecione um avaliando")
        placeholder.add(Hint("Os resultados, o valor adotado, a extrapolação e os graus aparecem aqui."))
        self.detail_stack.addWidget(placeholder)
        self.detail_widget = QWidget()
        detail_root = QVBoxLayout(self.detail_widget)
        detail_root.setContentsMargins(0, 0, 0, 0)
        detail_root.setSpacing(10)
        self.detail_title = QLabel("")
        self.detail_title.setObjectName("SectionTitle")
        detail_root.addWidget(self.detail_title)
        kpi_card = Card(title="Resultado da projeção")
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(8)
        self.kpi_estimate = KpiCard("Estimativa pontual", "—")
        self.kpi_ic = KpiCard("IC 80% da média", "—", tip("ic80"))
        self.kpi_amp = KpiCard("Amplitude do IC", "—", "A largura do intervalo em relação à estimativa define o grau de precisão.")
        self.kpi_precision = KpiCard("Grau de precisão", "—", tip("precisao"))
        self.kpi_prediction = KpiCard("Predição 80% (não entra no grau)", "—", tip("predicao"))
        self.kpi_arbitrio = KpiCard("Campo de arbítrio (±15%)", "—", tip("campo_arbitrio"))
        self.kpi_admissible = KpiCard(
            "Intervalo admissível",
            "—",
            "Interseção entre o IC/IP 80% escolhido e o campo de arbítrio de ±15%.",
        )
        kpi_grid.addWidget(self.kpi_estimate, 0, 0)
        kpi_grid.addWidget(self.kpi_ic, 0, 1)
        kpi_grid.addWidget(self.kpi_amp, 0, 2)
        kpi_grid.addWidget(self.kpi_precision, 0, 3)
        kpi_grid.addWidget(self.kpi_prediction, 1, 0, 1, 2)
        kpi_grid.addWidget(self.kpi_arbitrio, 1, 2, 1, 2)
        kpi_grid.addWidget(self.kpi_admissible, 2, 0, 1, 4)
        kpi_card.add_layout(kpi_grid)
        detail_root.addWidget(kpi_card)
        adopted_card = Card(title="Valor adotado e justificativa")
        adopted_form = QFormLayout()
        adopted_form.setSpacing(8)
        self.interval_combo = QComboBox()
        self.interval_combo.addItem("IC 80% (valor de mercado)", "IC")
        self.interval_combo.addItem("IP 80% (preço)", "IP")
        self.interval_combo.setToolTip(
            "Escolha qual intervalo de 80% limita o valor adotado. "
            "O IC é o intervalo da média; o IP é o intervalo de predição do preço."
        )
        self.interval_combo.currentIndexChanged.connect(self._interval_changed)
        self.round_limits = QCheckBox("Arredondar também os limites em até 1%")
        self.round_limits.setToolTip(
            "Arredonda os limites exibidos do intervalo para um múltiplo de 1% da estimativa."
        )
        self.round_limits.toggled.connect(self._round_limits_changed)
        self.adopted_edit = QLineEdit()
        self.adopted_edit.setToolTip(tip("adotado"))
        self.adopted_edit.setAccessibleName("Valor adotado ou arbitrado")
        self.adopted_edit.editingFinished.connect(self._adopted_changed)
        self.round_button = button("Arredondar 1%", "calculator",
                                   tooltip="Arredonda o valor adotado para o múltiplo de 1% da estimativa.")
        self.round_button.clicked.connect(self.round_adopted)
        adopted_row = QWidget()
        adopted_layout = QHBoxLayout(adopted_row)
        adopted_layout.setContentsMargins(0, 0, 0, 0)
        adopted_layout.addWidget(self.adopted_edit, 1)
        adopted_layout.addWidget(self.round_button)
        self.use_arbitrio = QCheckBox("Usar campo de arbítrio (±15%)")
        self.use_arbitrio.setToolTip(tip("campo_arbitrio"))
        self.use_arbitrio.toggled.connect(self._use_arbitrio_changed)
        self.justification = QPlainTextEdit()
        self.justification.setPlaceholderText(
            "Explique por que o valor adotado é diferente da estimativa. Obrigatório para exportar o relatório nesse caso."
        )
        self.justification.setMaximumHeight(95)
        self.justification.setAccessibleName("Justificativa do valor adotado")
        self.justification.textChanged.connect(self._justification_changed)
        adopted_form.addRow("Intervalo usado:", self.interval_combo)
        adopted_form.addRow("Valor adotado / arbitrado (R$):", adopted_row)
        adopted_form.addRow("", self.use_arbitrio)
        adopted_form.addRow("", self.round_limits)
        adopted_form.addRow("Justificativa:", self.justification)
        holder = QWidget()
        holder.setLayout(adopted_form)
        adopted_card.add(holder)
        self.adopted_banner = Banner("", "info")
        self.adopted_banner.setVisible(False)
        adopted_card.add(self.adopted_banner)
        detail_root.addWidget(adopted_card)
        nbr_card = Card(title="Graus de fundamentação e de precisão",
                        subtitle="A fundamentação soma seis itens. A precisão é separada e depende só da amplitude do IC 80%.")
        nbr_top = QHBoxLayout()
        self.fund_card = KpiCard("Grau de fundamentação", "—", tip("fundamentacao"))
        self.fund_points = KpiCard("Pontuação de fundamentação", "—", "Soma dos seis itens: III = 3, II = 2, I = 1.")
        self.prec_card = KpiCard("Grau de precisão", "—", tip("precisao"))
        self.final_pill = StatusPill("Aguardando cálculo", "cinza")
        nbr_top.addWidget(self.fund_card)
        nbr_top.addWidget(self.fund_points)
        nbr_top.addWidget(self.prec_card)
        nbr_top.addWidget(self.final_pill)
        nbr_card.add_layout(nbr_top)
        self.cap_banner = Banner("", "warning")
        self.cap_banner.setVisible(False)
        nbr_card.add(self.cap_banner)
        manual_form = QFormLayout()
        manual_form.setSpacing(6)
        self.item1_combo = QComboBox()
        self.item1_combo.addItems(["I", "II", "III"])
        self.item3_combo = QComboBox()
        self.item3_combo.addItems(["I", "II", "III"])
        self.item1_combo.setToolTip("Escolha o grau que descreve a caracterização do avaliando.")
        self.item3_combo.setToolTip("Escolha o grau que descreve a identificação dos dados de mercado.")
        self.item1_combo.currentTextChanged.connect(lambda _v: self._manual_changed())
        self.item3_combo.currentTextChanged.connect(lambda _v: self._manual_changed())
        manual_form.addRow("Item 1 — Caracterização do avaliando:", self.item1_combo)
        manual_form.addRow("Item 3 — Identificação dos dados de mercado:", self.item3_combo)
        manual_holder = QWidget()
        manual_holder.setLayout(manual_form)
        nbr_card.add(manual_holder)
        manual_hint = QLabel(
            "Itens 1 e 3 são escolhidos por você. Item 1: III = descrição completa e conferida; "
            "II = descrição razoável; I = descrição mínima. Item 3: III = dados bem identificados e verificados; "
            "II = dados identificados; I = dados mínimos."
        )
        manual_hint.setObjectName("Hint")
        manual_hint.setWordWrap(True)
        nbr_card.add(manual_hint)
        self.items_table = make_table(["Item", "O que verifica", "Grau", "Pontos", "Semáforo", "Explicação"])
        self.items_table.setMinimumHeight(280)
        nbr_card.add(self.items_table)
        self.precision_hint = QLabel(
            "Grau de precisão: III quando a amplitude do IC 80% é até 30%; II até 40%; "
            "I até 50%; acima disso, Fora de norma."
        )
        self.precision_hint.setObjectName("Hint")
        self.precision_hint.setWordWrap(True)
        self.precision_hint.setToolTip(tip("precisao"))
        nbr_card.add(self.precision_hint)
        self.limits_label = QLabel("")
        self.limits_label.setObjectName("Hint")
        self.limits_label.setWordWrap(True)
        nbr_card.add(self.limits_label)
        detail_root.addWidget(nbr_card)
        extra_card = Card(title="Extrapolação por variável",
                          subtitle="Mostra se o avaliando está fora da faixa da amostra e quanto o valor muda ao voltar para a fronteira.")
        self.extra_table = make_table(
            ["Variável", "Avaliando", "Mínimo", "Máximo", "Situação", "Aceitável", "Regra", "Estimativa na fronteira", "Afastamento"]
        )
        self.extra_table.setToolTip(tip("extrapolacao"))
        self.extra_table.horizontalHeaderItem(4).setToolTip(tip("extrapolacao"))
        self.extra_table.horizontalHeaderItem(8).setToolTip(tip("extrapolacao_regra"))
        self.extra_table.setMinimumHeight(180)
        extra_card.add(self.extra_table)
        self.extra_summary = Banner("", "info")
        extra_card.add(self.extra_summary)
        detail_root.addWidget(extra_card)
        self.detail_widget.setLayout(detail_root)
        self.detail_stack.addWidget(self.detail_widget)
        root.addWidget(self.detail_stack)
        root.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self.detail_stack.setCurrentIndex(0)
        self.item1_combo.blockSignals(True)
        self.item3_combo.blockSignals(True)
        self.item1_combo.setCurrentText(self.manager.manual_grades.get("item1", "II"))
        self.item3_combo.setCurrentText(self.manager.manual_grades.get("item3", "II"))
        self.item1_combo.blockSignals(False)
        self.item3_combo.blockSignals(False)

    # ------------------------------------------------------------------ estado
    def set_manager(self, manager: DataManager) -> None:
        self.manager = manager
        self.fit = None
        self.evaluations = []
        self.selected_id = None
        self._update_category_banner()
        self._rebuild_table()
        self._update_buttons()
        self._show_placeholder()

    def set_model(self, fit: Optional[FitResult]) -> None:
        self.fit = fit
        self._recompute_all(preserve_selection=True)
        self._update_buttons()

    def _update_category_banner(self) -> None:
        issues = self.manager.micronumerosity_issues()
        if issues:
            self.category_banner.setText("\n".join("• " + issue["text"] for issue in issues))
            self.category_banner.set_role("warning")
            self.category_banner.setVisible(True)
        else:
            self.category_banner.setVisible(False)

    def _recompute_all(self, *, preserve_selection: bool = True) -> None:
        self._update_category_banner()
        previous = self.selected_id if preserve_selection else None
        self.evaluations = []
        if self.fit is not None:
            for item in self.manager.evaluated:
                try:
                    self.evaluations.append(evaluate_item(self.manager, self.fit, item))
                except (ModelError, ValueError):
                    continue
        if previous and any(r.item.get("id") == previous for r in self.evaluations):
            self.selected_id = previous
        elif self.evaluations:
            self.selected_id = self.evaluations[0].item.get("id")
        else:
            self.selected_id = None
        self._rebuild_table()
        self._load_selected()

    def _update_buttons(self) -> None:
        has_items = bool(self.manager.evaluated)
        has_selection = self.selected_id is not None
        self.edit_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
        self.copy_list_button.setEnabled(bool(self.manager.evaluated))

    def _rebuild_table(self) -> None:
        self._loading = True
        try:
            x_names = [s["name"] for s in self.manager.x_specs(True)]
            headers = ["Avaliando"] + x_names + ["Estimativa", "IC 80%", "Adotado", "Fund.", "Precisão"]
            self.list_table.clear()
            self.list_table.setColumnCount(len(headers))
            self.list_table.setHorizontalHeaderLabels(headers)
            self.list_table.setRowCount(len(self.manager.evaluated))
            result_by_id = {r.item.get("id"): r for r in self.evaluations}
            for row, item in enumerate(self.manager.evaluated):
                name = str(item.get("name", "Avaliando"))
                values = [name]
                for x_name in x_names:
                    raw = item.get("values", {}).get(x_name)
                    values.append(format_number(raw, 4) if raw is not None else "—")
                result = result_by_id.get(item.get("id"))
                if result:
                    values.extend([
                        format_number(result.prediction.point, 2),
                        f"{format_number(result.prediction.ci_low, 2)} a {format_number(result.prediction.ci_high, 2)}",
                        format_number(result.adopted, 2),
                        result.nbr.final_degree,
                        result.prediction.precision_degree,
                    ])
                else:
                    values.extend(["—", "—", "—", "—", "—"])
                for col, value in enumerate(values):
                    align = col > 0
                    cell = readonly_item(str(value), align_right=align)
                    if col == 0:
                        cell.setToolTip("Clique para ver os detalhes e os gráficos.")
                    self.list_table.setItem(row, col, cell)
                self.list_table.setRowHeight(row, 38)
            self.list_table.resizeColumnsToContents()
            self.list_table.setColumnWidth(0, max(170, self.list_table.columnWidth(0)))
            self.list_hint.setText(
                "Nenhum avaliando incluído ainda. Clique em Incluir avaliando."
                if not self.manager.evaluated
                else "Clique numa linha para ver o valor adotado, a extrapolação e os graus."
            )
            if self.selected_id:
                self._select_row_by_id(self.selected_id)
            elif len(self.manager.evaluated):
                self.list_table.selectRow(0)
        finally:
            self._loading = False

    def _select_row_by_id(self, evaluated_id: str) -> None:
        for row, item in enumerate(self.manager.evaluated):
            if item.get("id") == evaluated_id:
                self.list_table.blockSignals(True)
                self.list_table.selectRow(row)
                self.list_table.blockSignals(False)
                return

    def _table_selection_changed(self) -> None:
        if self._loading:
            return
        rows = self.list_table.selectionModel().selectedRows()
        if not rows:
            self.selected_id = None
        else:
            row = rows[0].row()
            if 0 <= row < len(self.manager.evaluated):
                self.selected_id = self.manager.evaluated[row].get("id")
        self._load_selected()
        self._update_buttons()
        self.selection_changed.emit()

    def _current(self) -> Optional[EvaluationResult]:
        for result in self.evaluations:
            if result.item.get("id") == self.selected_id:
                return result
        return None

    def current_result(self) -> Optional[EvaluationResult]:
        return self._current()

    @property
    def selected_evaluated_id(self) -> Optional[str]:
        return self.selected_id

    # --------------------------------------------------------- seleção atual
    def _show_placeholder(self) -> None:
        self.detail_stack.setCurrentIndex(0)
        self.detail_title.setText("")

    def _load_selected(self) -> None:
        result = self._current()
        if result is None:
            self._show_placeholder()
            return
        self.detail_stack.setCurrentIndex(1)
        self._loading = True
        try:
            self.detail_title.setText(f"Avaliando: {result.name}")
            self.kpi_estimate.set_value("R$ " + format_number(result.prediction.point, 2))
            self.kpi_ic.set_value(
                "R$ " + format_number(result.prediction.ci_low, 2) + " a R$ " +
                format_number(result.prediction.ci_high, 2)
            )
            self.kpi_amp.set_value(format_number(result.prediction.amplitude_pct, 1) + "%")
            self.kpi_precision.set_value(result.prediction.precision_degree,
                                         "green" if result.prediction.precision_degree == "III" else
                                         "yellow" if result.prediction.precision_degree == "II" else
                                         "red" if result.prediction.precision_degree == "I" else "red")
            self.kpi_prediction.set_value(
                "R$ " + format_number(result.prediction.pi_low, 2) + " a R$ " +
                format_number(result.prediction.pi_high, 2)
            )
            self.kpi_arbitrio.set_value(
                "R$ " + format_number(result.arbitrio_low, 2) + " a R$ " +
                format_number(result.arbitrio_high, 2)
            )
            self.kpi_admissible.set_value(
                "R$ " + format_number(result.display_admissible_low, 2) + " a R$ " +
                format_number(result.display_admissible_high, 2)
            )
            if result.adopted_is_estimate:
                self.adopted_edit.setText(format_number(result.prediction.point, 2))
            else:
                self.adopted_edit.setText(format_number(result.adopted, 2))
            self.use_arbitrio.setChecked(result.use_arbitrio)
            self.interval_combo.blockSignals(True)
            interval_index = self.interval_combo.findData(result.interval_mode)
            self.interval_combo.setCurrentIndex(interval_index if interval_index >= 0 else 0)
            self.interval_combo.blockSignals(False)
            self.round_limits.blockSignals(True)
            self.round_limits.setChecked(result.round_limits)
            self.round_limits.blockSignals(False)
            if result.warnings:
                self.top_banner.setText("\n".join("• " + w for w in result.warnings))
                self.top_banner.set_role("warning")
                self.top_banner.setVisible(True)
            else:
                self.top_banner.setVisible(False)
            self.justification.setPlainText(result.justification)
            self.item1_combo.blockSignals(True)
            self.item3_combo.blockSignals(True)
            self.item1_combo.setCurrentText(self.manager.manual_grades.get("item1", "II"))
            self.item3_combo.setCurrentText(self.manager.manual_grades.get("item3", "II"))
            self.item1_combo.blockSignals(False)
            self.item3_combo.blockSignals(False)
            self._fill_nbr(result)
            self._fill_extrapolation(result)
            self._update_adopted_validation(result)
        finally:
            self._loading = False

    def _fill_nbr(self, result: EvaluationResult) -> None:
        nbr = result.nbr
        self.fund_card.set_value(nbr.final_degree,
                                 "green" if nbr.final_degree == "III" else
                                 "yellow" if nbr.final_degree == "II" else
                                 "red" if nbr.final_degree == "I" else "red")
        self.fund_points.set_value(str(nbr.total_points))
        self.prec_card.set_value(result.prediction.precision_degree,
                                 "green" if result.prediction.precision_degree == "III" else
                                 "yellow" if result.prediction.precision_degree == "II" else "red")
        status = "verde" if nbr.final_degree == "III" else "amarelo" if nbr.final_degree == "II" else "vermelho"
        self.final_pill.set_status(status, f"Fundamentação: {nbr.final_degree}  •  Precisão: {result.prediction.precision_degree}")
        if nbr.cap_explanation:
            self.cap_banner.setText(nbr.cap_explanation)
            self.cap_banner.set_role("warning")
            self.cap_banner.setVisible(True)
        else:
            self.cap_banner.setVisible(False)
        self.items_table.clearContents()
        self.items_table.setRowCount(len(nbr.items))
        for row, item in enumerate(nbr.items):
            values = [str(item.number), item.title, item.grade_label if item.grade != "0" else "Não atinge",
                      str(item.points), "", item.detail]
            for col, value in enumerate(values):
                if col == 4:
                    continue
                cell = readonly_item(str(value), align_right=col == 3)
                self.items_table.setItem(row, col, cell)
            pill = StatusPill("Verde" if item.color == "verde" else "Amarelo" if item.color == "amarelo" else "Vermelho",
                              item.color)
            wrap = QWidget()
            wrap_layout = QHBoxLayout(wrap)
            wrap_layout.setContentsMargins(4, 2, 4, 2)
            wrap_layout.addWidget(pill)
            self.items_table.setCellWidget(row, 4, wrap)
            self.items_table.setRowHeight(row, 46)
        self.items_table.resizeColumnsToContents()
        self.items_table.setColumnWidth(1, 230)
        self.items_table.setColumnWidth(5, 420)
        k = self.fit.k if self.fit else 0
        n = self.fit.n_obs if self.fit else 0
        self.limits_label.setText(
            f"Limites usados: item 2 — n efetivo {n}, k = {k}; III se n ≥ {6 * (k + 1)}, II se ≥ {4 * (k + 1)}, "
            f"I se ≥ {3 * (k + 1)}. Item 5 — pior p ≤ 10% (III), ≤ 20% (II), ≤ 30% (I). "
            "Item 6 — p do F ≤ 1% (III), ≤ 2% (II), ≤ 5% (I). Item 4 — fora da amostra, aceitável entre metade do "
            "mínimo e dobro do máximo; afastamento ≤ 15% no II e ≤ 20% no I (cada variável e o simultâneo)."
        )

    def _fill_extrapolation(self, result: EvaluationResult) -> None:
        nbr = result.nbr
        self.extra_table.setRowCount(len(nbr.extrapolation))
        for row, extra in enumerate(nbr.extrapolation):
            values = [
                extra.variable,
                format_number(extra.value, 3),
                format_number(extra.minimum, 3),
                format_number(extra.maximum, 3),
                extra.situation.capitalize(),
                "Sim" if extra.acceptable else "Não",
                extra.limit_text,
                format_number(extra.estimate_pulled, 2) if extra.estimate_pulled is not None else "—",
                format_number(extra.distance_pct, 1) + "%" if extra.distance_pct is not None else "—",
            ]
            for col, value in enumerate(values):
                cell = readonly_item(str(value), align_right=col in (1, 2, 3, 7, 8))
                if col == 4 and extra.situation != "dentro":
                    cell.setBackground(QColor("#FEF3C7"))
                self.extra_table.setItem(row, col, cell)
        self.extra_table.resizeColumnsToContents()
        self.extra_table.setColumnWidth(6, 290)
        summary = f"Item 4: {nbr.item4_grade if nbr.item4_grade != '0' else 'não atinge'} — {nbr.item4_detail}"
        if nbr.simultaneous_distance_pct is not None:
            summary += f" Afastamento simultâneo: {format_number(nbr.simultaneous_distance_pct, 1)}%."
        self.extra_summary.setText(summary)
        self.extra_summary.set_role(
            "success" if nbr.item4_grade == "III" else "warning" if nbr.item4_grade in ("II", "I") else "error"
        )
        self.extra_summary.setVisible(True)

    def _update_adopted_validation(self, result: Optional[EvaluationResult]) -> None:
        if result is None:
            self.adopted_banner.setVisible(False)
            self.adopted_edit.setProperty("invalid", False)
            refresh_style(self.adopted_edit)
            return
        message = ""
        role = "info"
        if result.blocking_messages:
            message = "\n".join("• " + m for m in result.blocking_messages)
            role = "error"
            self.adopted_edit.setProperty("invalid", True)
        else:
            message = (
                f"Valor dentro do {result.interval_label}. "
                f"Intervalo admissível: {format_number(result.display_admissible_low, 2)} a "
                f"{format_number(result.display_admissible_high, 2)}."
                + (" A justificativa está preenchida." if result.justification_required else "")
            )
            role = "success"
            self.adopted_edit.setProperty("invalid", False)
        self.adopted_edit.setToolTip(tip("adotado"))
        refresh_style(self.adopted_edit)
        self.adopted_banner.setText(message)
        self.adopted_banner.set_role(role)
        self.adopted_banner.setVisible(True)

    # -------------------------------------------------------------- interação
    def _adopted_changed(self) -> None:
        if self._loading:
            return
        result = self._current()
        if result is None:
            return
        try:
            value = parse_number(self.adopted_edit.text())
        except ValueError as exc:
            show_error(self, str(exc), title="Valor adotado inválido")
            self._loading = True
            self.adopted_edit.setText(format_number(result.adopted, 2))
            self._loading = False
            return
        if math.isclose(value, result.adopted, rel_tol=0.0, abs_tol=0.005):
            self._update_adopted_validation(result)
            return
        try:
            self.manager.update_evaluated(result.item.get("id"), adopted=value)
        except ValueError as exc:
            show_error(self, str(exc))
            return
        self._refresh_current_after_adoption()
        self.evaluation_changed.emit()

    def _refresh_current_after_adoption(self) -> None:
        item_id = self.selected_id
        if item_id is None or self.fit is None:
            return
        result = self._current()
        if result is None:
            return
        try:
            new_result = evaluate_item(self.manager, self.fit, result.item)
        except (ModelError, ValueError) as exc:
            show_error(self, str(exc))
            return
        self.evaluations = [new_result if r.item.get("id") == item_id else r for r in self.evaluations]
        self._rebuild_table()
        self._load_selected()
        self._update_adopted_validation(new_result)
        self._update_buttons()

    def round_adopted(self) -> None:
        result = self._current()
        if result is None:
            return
        value = round_to_one_percent(result.prediction.point)
        self._loading = True
        self.adopted_edit.setText(format_number(value, 2))
        self._loading = False
        self._adopted_changed()

    def _interval_changed(self) -> None:
        if self._loading:
            return
        result = self._current()
        if result is None:
            return
        mode = str(self.interval_combo.currentData() or "IC")
        self.manager.update_evaluated(result.item.get("id"), interval_mode=mode)
        self._refresh_current_after_adoption()
        self.evaluation_changed.emit()

    def _round_limits_changed(self, checked: bool) -> None:
        if self._loading:
            return
        result = self._current()
        if result is None:
            return
        self.manager.update_evaluated(result.item.get("id"), round_limits=checked)
        self._refresh_current_after_adoption()
        self.evaluation_changed.emit()

    def _use_arbitrio_changed(self, checked: bool) -> None:
        if self._loading:
            return
        result = self._current()
        if result is None:
            return
        try:
            self.manager.update_evaluated(result.item.get("id"), use_arbitrio=checked)
        except ValueError as exc:
            show_error(self, str(exc))
            return
        self._refresh_current_after_adoption()
        self.evaluation_changed.emit()

    def _justification_changed(self) -> None:
        if self._loading:
            return
        result = self._current()
        if result is None:
            return
        self.manager.update_evaluated(result.item.get("id"), justification=self.justification.toPlainText())
        # Atualiza só a validação, sem reposicionar o cursor.
        try:
            new_result = evaluate_item(self.manager, self.fit, result.item) if self.fit else None
        except (ModelError, ValueError):
            new_result = None
        if new_result is not None:
            self.evaluations = [new_result if r.item.get("id") == self.selected_id else r for r in self.evaluations]
            self._update_adopted_validation(new_result)
        self.evaluation_changed.emit()

    def _manual_changed(self) -> None:
        if self._loading:
            return
        self.manager.manual_grades["item1"] = self.item1_combo.currentText()
        self.manager.manual_grades["item3"] = self.item3_combo.currentText()
        if self.fit is not None:
            self._recompute_all(preserve_selection=True)
        self.evaluation_changed.emit()
        self.selection_changed.emit()

    # ---------------------------------------------------------------- CRUD
    def add_evaluated(self) -> None:
        if not self.manager.x_specs(True):
            show_warning(self, "Escolha as variáveis X na aba 1 antes de incluir o avaliando.")
            return
        try:
            dialog = EvaluatedDialog(self.manager, parent=self)
        except ValueError as exc:
            show_error(self, str(exc))
            return
        if dialog.exec() != EvaluatedDialog.DialogCode.Accepted:
            return
        try:
            item = self.manager.add_evaluated(dialog.result["name"], dialog.result["values"])
        except ValueError as exc:
            show_error(self, str(exc))
            return
        self.selected_id = item.get("id")
        self._recompute_all(preserve_selection=True)
        self._update_buttons()
        self.evaluation_changed.emit()
        self.selection_changed.emit()

    def edit_evaluated(self) -> None:
        item = self._selected_item()
        if item is None:
            show_info(self, "Selecione um avaliando para editar.")
            return
        try:
            dialog = EvaluatedDialog(self.manager, item=item, parent=self)
        except ValueError as exc:
            show_error(self, str(exc))
            return
        if dialog.exec() != EvaluatedDialog.DialogCode.Accepted:
            return
        try:
            self.manager.update_evaluated(item.get("id"), name=dialog.result["name"],
                                          values=dialog.result["values"])
        except ValueError as exc:
            show_error(self, str(exc))
            return
        self.selected_id = item.get("id")
        self._recompute_all(preserve_selection=True)
        self._update_buttons()
        self.evaluation_changed.emit()
        self.selection_changed.emit()

    def delete_evaluated(self) -> None:
        item = self._selected_item()
        if item is None:
            show_info(self, "Selecione um avaliando para excluir.")
            return
        if not ask_yes_no(
            self, "Excluir avaliando",
            f"Excluir o avaliando “{item.get('name', '')}”?",
            yes_text="Excluir", no_text="Cancelar",
        ):
            return
        self.manager.delete_evaluated(item.get("id"))
        self.selected_id = None
        self._recompute_all(preserve_selection=False)
        self._update_buttons()
        self.evaluation_changed.emit()
        self.selection_changed.emit()

    def _selected_item(self) -> Optional[dict[str, Any]]:
        for item in self.manager.evaluated:
            if item.get("id") == self.selected_id:
                return item
        return None

    def copy_list(self) -> None:
        if self.list_table.rowCount() == 0:
            show_info(self, "Ainda não há avaliandos para copiar.")
            return
        copy_text(table_to_tsv(self.list_table))
        toast(self, "Tabela de avaliandos copiada.")

    # -------------------------------------------------------------- integração
    def refresh(self) -> None:
        self._recompute_all(preserve_selection=True)
        self._update_buttons()

    def select_evaluated_id(self, evaluated_id: Optional[str]) -> None:
        if not evaluated_id:
            return
        if any(item.get("id") == evaluated_id for item in self.manager.evaluated):
            self.selected_id = evaluated_id
            self._select_row_by_id(evaluated_id)
            self._load_selected()
            self._update_buttons()
            self.selection_changed.emit()

    def commit_edits(self) -> None:
        """Garante que o texto do valor adotado foi gravado antes de exportar."""
        if self._loading:
            return
        if self._current() is not None and self.adopted_edit.text().strip():
            self._adopted_changed()

    def refresh_theme(self) -> None:
        for row in range(self.list_table.rowCount()):
            self.list_table.setRowHeight(row, 42)
        for table in (self.list_table, self.items_table, self.extra_table):
            table.resizeRowsToContents()
