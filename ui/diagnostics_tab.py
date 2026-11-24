"""Aba 5 — resíduos, distância de Cook, Mahalanobis e premissas."""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from core import charting
from core.data_manager import DataManager
from core.diagnostics import DiagnosticsResult
from core.formatting import format_number
from core.regression_engine import FitResult
from .clipboard import copy_text, table_to_tsv
from .plots import PlotCard
from .tooltips import tip
from .widgets import (
    Banner, Card, Hint, StatusPill, button, make_table, readonly_item,
    show_error, show_info, show_warning, toast, ask_yes_no,
)


class DiagnosticsTab(QWidget):
    points_deactivated = Signal()

    def __init__(self, manager: DataManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.fit: Optional[FitResult] = None
        self.diagnostics: Optional[DiagnosticsResult] = None
        self._build_ui()
        self.set_model(None, None)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)
        title = QLabel("5. Resíduos & Cook")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        subtitle = QLabel(
            "Os resíduos medem o quanto cada imóvel ficou longe da equação. Cook mostra quem puxa o resultado "
            "e Mahalanobis mostra quem está distante nas variáveis explicativas. Passe o mouse nos pontos para ver o imóvel."
        )
        subtitle.setObjectName("Hint")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)
        self.top_banner = Banner("Calcule o modelo na aba 3 para ver os diagnósticos.", "info")
        root.addWidget(self.top_banner)
        self.category_banner = Banner("", "warning")
        self.category_banner.setVisible(False)
        root.addWidget(self.category_banner)
        premises_card = Card(title="Semáforo das premissas",
                             subtitle="Verde é tranquilizador, amarelo pede conferência e vermelho pede atenção.")
        self.assumption_rows_layout = QVBoxLayout()
        self.assumption_rows_layout.setSpacing(6)
        premises_card.add_layout(self.assumption_rows_layout)
        self.assumption_rows: dict[str, tuple[QLabel, StatusPill, QLabel]] = {}
        for key, title_text in (
            ("normalidade", "Normalidade dos resíduos"),
            ("homocedasticidade", "Dispersão dos resíduos"),
            ("multicolinearidade", "Variáveis repetidas"),
            ("independencia", "Durbin-Watson (informativo)"),
        ):
            row = QHBoxLayout()
            name = QLabel(title_text)
            name.setMinimumWidth(210)
            name.setWordWrap(True)
            pill = StatusPill("Aguardando", "cinza")
            text = QLabel("—")
            text.setWordWrap(True)
            text.setObjectName("Hint")
            row.addWidget(name, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(pill, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(text, 1)
            holder = QWidget()
            holder.setLayout(row)
            self.assumption_rows_layout.addWidget(holder)
            self.assumption_rows[key] = (name, pill, text)
        bands_title = QLabel("Contagem dos resíduos padronizados (o Shapiro-Wilk é só uma linha extra):")
        bands_title.setWordWrap(True)
        premises_card.add(bands_title)
        self.bands_table = make_table(["Faixa", "Encontrado", "Esperado", "Semáforo", "Quantidade"])
        self.bands_table.setMaximumHeight(190)
        premises_card.add(self.bands_table)
        self.shapiro_label = QLabel("Shapiro-Wilk: —")
        self.shapiro_label.setObjectName("Hint")
        self.shapiro_label.setWordWrap(True)
        premises_card.add(self.shapiro_label)
        self.vif_label = QLabel("VIF: —")
        self.vif_label.setWordWrap(True)
        self.vif_label.setToolTip(tip("vif"))
        self.vif_label.setObjectName("Hint")
        premises_card.add(self.vif_label)
        self.corr_label = QLabel("Pares com |r| > 0,80: —")
        self.corr_label.setWordWrap(True)
        self.corr_label.setToolTip("Correlação alta entre duas variáveis X. Pode indicar informação repetida.")
        self.corr_label.setObjectName("Hint")
        premises_card.add(self.corr_label)
        root.addWidget(premises_card)
        influence_card = Card(title="Desligar pontos de atenção",
                              subtitle="O imóvel não é apagado: ele apenas deixa de entrar nas contas até você reativar na aba 1.")
        influence_actions = QHBoxLayout()
        self.cook_button = button("Desativar pontos influentes (Cook)", "delete", danger=True,
                                  tooltip=tip("cook"))
        self.mahal_button = button("Desativar pontos atípicos (Mahalanobis)", "delete", danger=True,
                                   tooltip=tip("mahalanobis"))
        self.cook_button.clicked.connect(self.deactivate_cook)
        self.mahal_button.clicked.connect(self.deactivate_mahalanobis)
        influence_actions.addWidget(self.cook_button)
        influence_actions.addWidget(self.mahal_button)
        influence_actions.addStretch(1)
        influence_card.add_layout(influence_actions)
        self.influence_hint = QLabel("")
        self.influence_hint.setObjectName("Hint")
        self.influence_hint.setWordWrap(True)
        influence_card.add(self.influence_hint)
        root.addWidget(influence_card)
        table_card = Card(title="Tabela por imóvel",
                          subtitle="Resíduo relativo acima de 40% fica amarelo; acima de 70%, vermelho. |z| > 2 fica em destaque.")
        table_actions = QHBoxLayout()
        table_actions.addStretch(1)
        self.copy_table_button = button("Copiar tabela", "copy")
        self.copy_table_button.clicked.connect(self.copy_table)
        table_actions.addWidget(self.copy_table_button)
        table_card.add_layout(table_actions)
        self.table = make_table([
            "Rótulo", "Observado", "Estimado", "Resíduo", "Resíduo relativo", "Padronizado",
            "Studentizado", "Cook", "Mahalanobis",
        ])
        for index, key in ((3, "residuo"), (4, "residuo_relativo"), (5, "padronizado"),
                           (6, "studentizado"), (7, "cook"), (8, "mahalanobis")):
            self.table.horizontalHeaderItem(index).setToolTip(tip(key))
        self.table.setMinimumHeight(260)
        table_card.add(self.table)
        root.addWidget(table_card)
        plots_grid = QGridLayout()
        plots_grid.setSpacing(10)
        self.resid_plot = PlotCard("Resíduos × valores ajustados")
        self.qq_plot = PlotCard("Q-Q dos resíduos")
        self.hist_plot = PlotCard("Histograma dos resíduos")
        self.cook_plot = PlotCard("Distância de Cook")
        self.mahal_plot = PlotCard("Distância de Mahalanobis")
        plots_grid.addWidget(self.resid_plot, 0, 0)
        plots_grid.addWidget(self.qq_plot, 0, 1)
        plots_grid.addWidget(self.hist_plot, 1, 0)
        plots_grid.addWidget(self.cook_plot, 1, 1)
        plots_grid.addWidget(self.mahal_plot, 2, 0, 1, 2)
        for card in (self.resid_plot, self.qq_plot, self.hist_plot, self.cook_plot, self.mahal_plot):
            card.setMinimumHeight(560)
        root.addLayout(plots_grid)
        root.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------ dados
    def set_manager(self, manager: DataManager) -> None:
        self.manager = manager
        self.set_model(None, None)

    def set_model(self, fit: Optional[FitResult], diagnostics: Optional[DiagnosticsResult]) -> None:
        self.fit = fit
        self.diagnostics = diagnostics
        issues = self.manager.micronumerosity_issues()
        if issues:
            self.category_banner.setText("\n".join("• " + issue["text"] for issue in issues))
            self.category_banner.set_role("warning")
            self.category_banner.setVisible(True)
        else:
            self.category_banner.setVisible(False)
        if fit is None or diagnostics is None:
            self.top_banner.setText("Calcule o modelo na aba 3 para ver os diagnósticos.")
            self.top_banner.set_role("info")
            self.top_banner.setVisible(True)
            for key in self.assumption_rows:
                _, pill, text = self.assumption_rows[key]
                pill.set_status("cinza", "Aguardando")
                text.setText("—")
            self.bands_table.setRowCount(0)
            self.table.setRowCount(0)
            self.shapiro_label.setText("Shapiro-Wilk: —")
            self.vif_label.setText("VIF: —")
            self.corr_label.setText("Pares com |r| > 0,80: —")
            self.influence_hint.setText("")
            self.cook_button.setEnabled(False)
            self.mahal_button.setEnabled(False)
            self.copy_table_button.setEnabled(False)
            for card in (self.resid_plot, self.qq_plot, self.hist_plot, self.cook_plot, self.mahal_plot):
                card.clear_plot("Calcule o modelo para ver este gráfico.")
            return
        self.top_banner.setVisible(False)
        self._fill_assumptions(diagnostics)
        self._fill_table(diagnostics)
        self._fill_plots(fit)
        flagged_cook = len(diagnostics.cooks_flags)
        flagged_mahal = len(diagnostics.mahalanobis_flags)
        self.cook_button.setText(f"Desativar pontos influentes (Cook) — {flagged_cook}")
        self.mahal_button.setText(f"Desativar pontos atípicos (Mahalanobis) — {flagged_mahal}")
        self.cook_button.setEnabled(flagged_cook > 0)
        self.mahal_button.setEnabled(flagged_mahal > 0)
        self.copy_table_button.setEnabled(True)
        self.influence_hint.setText(
            f"Corte de Cook: {format_number(diagnostics.cooks_threshold, 4)} (4 ÷ n, com atenção também para valores acima de 1). "
            f"Corte de Mahalanobis: {format_number(diagnostics.mahalanobis_cutoff, 3)}"
            + (" — corte aproximado pela qui-quadrado porque a amostra é pequena." if diagnostics.mahalanobis_approximate else " — corte exato pela distribuição Beta a 5%.")
            + " Desligar um ponto só muda a amostra depois que você confirma."
        )

    def _fill_assumptions(self, diag: DiagnosticsResult) -> None:
        for key, assumption in (
            ("normalidade", diag.normality),
            ("homocedasticidade", diag.homocedasticity),
            ("multicolinearidade", diag.multicollinearity),
            ("independencia", diag.independence),
        ):
            _, pill, text = self.assumption_rows[key]
            status = assumption.status if assumption.status in ("verde", "amarelo", "vermelho") else "cinza"
            label = {"verde": "Verde", "amarelo": "Amarelo", "vermelho": "Vermelho", "cinza": "Informativo"}[status]
            pill.set_status(status, label)
            text.setText(assumption.text)
        self.bands_table.setRowCount(len(diag.normality_bands))
        for r, band in enumerate(diag.normality_bands):
            values = [
                band.label,
                format_number(band.observed_pct, 1) + "%",
                f"{format_number(band.expected_low, 0)}–{format_number(band.expected_high, 0)}%",
                "",
                f"{band.count} de {band.total}",
            ]
            for c, value in enumerate(values):
                if c == 3:
                    continue
                self.bands_table.setItem(r, c, readonly_item(value, align_right=c in (1, 2, 4)))
            pill = StatusPill("Verde" if band.status == "verde" else "Amarelo" if band.status == "amarelo" else "Vermelho",
                              band.status)
            wrap = QWidget()
            layout = QHBoxLayout(wrap)
            layout.setContentsMargins(2, 2, 2, 2)
            layout.addWidget(pill)
            self.bands_table.setCellWidget(r, 3, wrap)
        self.bands_table.resizeColumnsToContents()
        self.bands_table.setColumnWidth(0, 110)
        self.bands_table.setColumnWidth(3, 150)
        self.bands_table.resizeRowsToContents()
        self.shapiro_label.setText(diag.shapiro_text + " Não muda a cor das faixas.")
        vif_parts = [f"{name} = {format_number(value, 2) if math.isfinite(value) else 'muito alto'}"
                     for name, value in diag.vif.items()]
        self.vif_label.setText(
            "VIF (amarelo acima de 5; vermelho acima de 10): "
            + ("; ".join(vif_parts) if vif_parts else "—")
        )
        if diag.high_correlations:
            pairs = "; ".join(f"{a} × {b} = {format_number(r, 3)}" for a, b, r in diag.high_correlations)
            self.corr_label.setText("Pares de X com |r| > 0,80: " + pairs)
            self.corr_label.setStyleSheet("color: #92400E; background: #FFFBEB; padding: 6px; border-radius: 6px;")
        else:
            self.corr_label.setText("Pares de X com |r| > 0,80: nenhum.")
            self.corr_label.setStyleSheet("")

    def _fill_table(self, diag: DiagnosticsResult) -> None:
        self.table.setRowCount(len(diag.table))
        for r, row in enumerate(diag.table):
            values = [
                row.label,
                format_number(row.observed, 2),
                format_number(row.estimated, 2),
                format_number(row.residual, 2),
                format_number(row.relative_pct, 1) + "%",
                format_number(row.standardized, 3),
                format_number(row.studentized, 3),
                format_number(row.cook, 4),
                format_number(row.mahalanobis, 3),
            ]
            for c, value in enumerate(values):
                item = readonly_item(value, align_right=c > 0)
                if c == 4:
                    if row.relative_pct >= 70:
                        item.setBackground(QColor("#FEE2E2"))
                        item.setForeground(QColor("#991B1B"))
                    elif row.relative_pct >= 40:
                        item.setBackground(QColor("#FEF3C7"))
                        item.setForeground(QColor("#92400E"))
                if row.z_highlight and c in (5, 6):
                    item.setBackground(QColor("#DBEAFE"))
                    item.setForeground(QColor("#1E3A8A"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                if row.influential and c == 7:
                    item.setBackground(QColor("#FEE2E2"))
                    item.setForeground(QColor("#991B1B"))
                if row.atypical and c == 8:
                    item.setBackground(QColor("#FEF3C7"))
                    item.setForeground(QColor("#92400E"))
                if c == 0:
                    item.setToolTip("Passe o mouse nos gráficos para ver o mesmo imóvel.")
                self.table.setItem(r, c, item)
            self.table.setRowHeight(r, 38)
        self.table.resizeColumnsToContents()

    def _fill_plots(self, fit: FitResult) -> None:
        fig, _ = charting.residual_fitted(fit.fitted_original, fit.residuals, fit.labels)
        self.resid_plot.set_figure(fig, x_values=fit.fitted_original, y_values=fit.residuals,
                                   labels=fit.labels)
        fig, _ = charting.qq_plot(fit.residuals)
        from scipy import stats
        resid = np.asarray(fit.residuals, dtype=float)
        try:
            (osm, osr), _ = stats.probplot(resid, dist="norm")
            order = np.argsort(resid)
            qq_labels = [fit.labels[i] for i in order]
            self.qq_plot.set_figure(fig, x_values=osm, y_values=osr, labels=qq_labels)
        except Exception:
            self.qq_plot.set_figure(fig)
        fig, _ = charting.histogram(fit.residuals, title="Histograma dos resíduos",
                                    xlabel="Resíduo", color=charting.PRIMARY)
        self.hist_plot.set_figure(fig)
        threshold_cook = min(4.0 / max(fit.n_obs, 1), 1.0)
        fig, _ = charting.stem_plot(fit.cooks_distance, fit.labels, threshold_cook,
                                    title="Distância de Cook", ylabel="Cook")
        self.cook_plot.set_figure(fig, x_values=np.arange(1, fit.n_obs + 1),
                                  y_values=fit.cooks_distance, labels=fit.labels)
        fig, _ = charting.stem_plot(fit.mahalanobis, fit.labels, fit.mahalanobis_cutoff,
                                    title="Distância de Mahalanobis", ylabel="Mahalanobis")
        self.mahal_plot.set_figure(fig, x_values=np.arange(1, fit.n_obs + 1),
                                   y_values=fit.mahalanobis, labels=fit.labels)

    # ------------------------------------------------------------------ ações
    def copy_table(self) -> None:
        if self.table.rowCount() == 0:
            show_info(self, "Ainda não há tabela de resíduos para copiar.")
            return
        copy_text(table_to_tsv(self.table))
        toast(self, "Tabela de resíduos copiada.")

    def _positions_for(self, positions: list[int], kind: str) -> None:
        if self.diagnostics is None:
            return
        if not positions:
            show_info(self, "Nenhum ponto se enquadra neste critério com os dados atuais.")
            return
        if kind == "cook":
            labels = [r.label for r in self.diagnostics.table if r.position in positions]
            title = "Desativar pontos influentes"
            criteria = "distância de Cook acima do corte"
        else:
            labels = [r.label for r in self.diagnostics.table if r.position in positions]
            title = "Desativar pontos atípicos"
            criteria = "distância de Mahalanobis acima do corte"
        preview = "; ".join(labels[:5]) + ("..." if len(labels) > 5 else "")
        if not ask_yes_no(
            self, title,
            f"{len(positions)} imóvel(is) serão desmarcados na aba 1 por causa de {criteria}. "
            f"Eles não serão apagados.\n\n{preview}\n\nDeseja continuar?",
            yes_text="Desativar", no_text="Cancelar",
        ):
            return
        changed = self.manager.deactivate_many(positions)
        if changed:
            self.points_deactivated.emit()
            show_info(self, f"{changed} imóvel(is) foram desmarcados na aba 1. O modelo será recalculado.")

    def deactivate_cook(self) -> None:
        if self.diagnostics is not None:
            self._positions_for(self.diagnostics.cooks_flags, "cook")

    def deactivate_mahalanobis(self) -> None:
        if self.diagnostics is not None:
            self._positions_for(self.diagnostics.mahalanobis_flags, "mahalanobis")

    def refresh_theme(self) -> None:
        for table in (self.bands_table, self.table):
            table.resizeRowsToContents()
        if self.fit is not None and self.diagnostics is not None:
            self._fill_plots(self.fit)
