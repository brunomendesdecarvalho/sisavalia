"""Plugin de cálculos específicos: liquidação, desapropriação e aluguel."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtWidgets import (
    QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QPlainTextEdit,
    QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from core.formatting import format_number
from core.plugin_base import BasePlugin
from ui.clipboard import copy_text
from ui.file_dialogs import save_file_name
from ui.widgets import button, show_info, show_warning

try:
    from ._engenharia import expropriation_value, liquidation_vpl, rent_by_capital
except ImportError:  # plugin carregado por caminho pelo PluginManager
    from _engenharia import expropriation_value, liquidation_vpl, rent_by_capital


class ProcedimentosEspecificos(BasePlugin):
    name = "Procedimentos específicos"
    description = (
        "Calculadoras de liquidação forçada por VPL, desapropriação parcial "
        "antes/depois e aluguel por remuneração do capital."
    )

    def run(self, dataframe: pd.DataFrame, parent_widget: Any) -> Any:
        dialog = SpecificDialog(parent_widget)
        dialog.exec()
        return dialog.result_data


class SpecificDialog(QDialog):
    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.result_data: dict[str, Any] = {}
        self.setWindowTitle("Procedimentos específicos — NBR 14653")
        self.resize(900, 700)
        outer = QVBoxLayout(self)
        title = QLabel("Procedimentos específicos")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        hint = QLabel(
            "Escolha o procedimento. Os cálculos são independentes da amostra e "
            "devem ser conferidos pelo responsável técnico."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        outer.addWidget(hint)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._liquidation(), "Liquidação forçada")
        self.tabs.addTab(self._expropriation(), "Desapropriação parcial")
        self.tabs.addTab(self._rent(), "Aluguel por capital")
        outer.addWidget(self.tabs, 1)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setMinimumHeight(160)
        self.result.setAccessibleName("Resultado do procedimento específico")
        outer.addWidget(self.result)
        actions = QHBoxLayout()
        self.calc = button("Calcular aba atual", "calculator", primary=True)
        self.copy = button("Copiar resultado", "copy")
        self.save = button("Salvar resultado", "save")
        self.calc.clicked.connect(self.calculate)
        self.copy.clicked.connect(self.copy_result)
        self.save.clicked.connect(self.save_result)
        actions.addWidget(self.calc)
        actions.addWidget(self.copy)
        actions.addWidget(self.save)
        actions.addStretch(1)
        outer.addLayout(actions)
        close = button("Fechar", "close")
        close.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close)
        outer.addLayout(bottom)

    @staticmethod
    def _spin(minimum: float, maximum: float, value: float, decimals: int = 2,
              suffix: str = "") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setValue(value)
        spin.setSingleStep(1.0 if maximum > 1000 else 0.01)
        spin.setSuffix(suffix)
        return spin

    def _liquidation(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.liq_value = self._spin(0, 1000000000, 500000, 2, " R$")
        self.liq_months = self._spin(0, 120, 12, 0, " meses")
        self.liq_monthly = self._spin(0, 10000000, 1500, 2, " R$")
        self.liq_sale = self._spin(0, 100, 6, 2, " %")
        self.liq_rate = self._spin(0, 100, 12, 2, " % a.a.")
        for label, widget in (
            ("Valor de mercado:", self.liq_value),
            ("Prazo de venda:", self.liq_months),
            ("Despesas mensais:", self.liq_monthly),
            ("Despesas de venda:", self.liq_sale),
            ("Taxa de atratividade:", self.liq_rate),
        ):
            form.addRow(label, widget)
        note = QLabel(
            "VPL = (valor de mercado × (1 − despesas de venda) − despesas mensais × prazo) "
            "descontado pela taxa mensal equivalente."
        )
        note.setWordWrap(True)
        note.setObjectName("Hint")
        form.addRow(note)
        return page

    def _expropriation(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.exp_original = self._spin(0, 1000000000, 500000, 2, " R$")
        self.exp_remaining = self._spin(0, 1000000000, 350000, 2, " R$")
        self.exp_adapt = self._spin(0, 1000000000, 20000, 2, " R$")
        self.exp_loss = self._spin(0, 1000000000, 0, 2, " R$")
        for label, widget in (
            ("Valor original (antes):", self.exp_original),
            ("Valor do remanescente (depois):", self.exp_remaining),
            ("Custos de adaptação:", self.exp_adapt),
            ("Desvalia adicional:", self.exp_loss),
        ):
            form.addRow(label, widget)
        note = QLabel("Indenização = valor original − remanescente + adaptação + desvalia.")
        note.setWordWrap(True)
        note.setObjectName("Hint")
        form.addRow(note)
        return page

    def _rent(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.rent_value = self._spin(0, 1000000000, 500000, 2, " R$")
        self.rent_rate = self._spin(0, 100, 6, 2, " % a.a.")
        self.rent_vacancy = self._spin(0, 100, 5, 2, " %")
        self.rent_admin = self._spin(0, 100, 8, 2, " %")
        for label, widget in (
            ("Valor do imóvel:", self.rent_value),
            ("Taxa de remuneração anual:", self.rent_rate),
            ("Vacância:", self.rent_vacancy),
            ("Administração:", self.rent_admin),
        ):
            form.addRow(label, widget)
        note = QLabel(
            "Aluguel mensal = valor × taxa anual ÷ 12, ajustado por vacância e administração."
        )
        note.setWordWrap(True)
        note.setObjectName("Hint")
        form.addRow(note)
        return page

    def calculate(self) -> None:
        index = self.tabs.currentIndex()
        try:
            if index == 0:
                data = liquidation_vpl(
                    self.liq_value.value(), self.liq_months.value(),
                    self.liq_monthly.value(), self.liq_sale.value(), self.liq_rate.value(),
                )
                text = (
                    "Liquidação forçada — VPL\n"
                    f"Valor de mercado: R$ {format_number(self.liq_value.value(), 2)}\n"
                    f"Prazo de venda: {format_number(self.liq_months.value(), 0)} meses\n"
                    f"Taxa mensal equivalente: {format_number(data['monthly_rate_pct'], 4)}%\n"
                    f"Receita líquida de venda: R$ {format_number(data['net_sale'], 2)}\n"
                    f"VPL da liquidação: R$ {format_number(data['vpl'], 2)}"
                )
                self.result_data["liquidation"] = data
            elif index == 1:
                value = expropriation_value(
                    self.exp_original.value(), self.exp_remaining.value(),
                    self.exp_adapt.value(), self.exp_loss.value(),
                )
                text = (
                    "Desapropriação parcial — antes e depois\n"
                    f"Valor original: R$ {format_number(self.exp_original.value(), 2)}\n"
                    f"Remanescente: R$ {format_number(self.exp_remaining.value(), 2)}\n"
                    f"Adaptação: R$ {format_number(self.exp_adapt.value(), 2)}\n"
                    f"Desvalia: R$ {format_number(self.exp_loss.value(), 2)}\n"
                    f"Indenização: R$ {format_number(value, 2)}"
                )
                self.result_data["expropriation"] = value
            else:
                data = rent_by_capital(
                    self.rent_value.value(), self.rent_rate.value(),
                    self.rent_vacancy.value(), self.rent_admin.value(),
                )
                text = (
                    "Aluguel por remuneração do capital\n"
                    f"Valor do imóvel: R$ {format_number(self.rent_value.value(), 2)}\n"
                    f"Aluguel bruto mensal: R$ {format_number(data['gross'], 2)}\n"
                    f"Aluguel líquido mensal: R$ {format_number(data['monthly'], 2)}\n"
                    f"Aluguel líquido anual: R$ {format_number(data['annual'], 2)}"
                )
                self.result_data["rent"] = data
        except Exception as exc:
            show_warning(self, f"Não foi possível calcular: {exc}")
            return
        text += "\n\nConfira os critérios e a responsabilidade técnica no laudo."
        self.result_text = text
        self.result.setPlainText(text)

    def copy_result(self) -> None:
        text = getattr(self, "result_text", "").strip()
        if not text:
            show_info(self, "Calcule antes de copiar.")
            return
        copy_text(text)
        show_info(self, "Resultado copiado.")

    def save_result(self) -> None:
        if not getattr(self, "result_text", "").strip():
            show_info(self, "Calcule antes de salvar.")
            return
        filename = save_file_name(
            self, "Salvar procedimento específico", "procedimento_especifico.txt",
            "Texto (*.txt)", "txt",
        )
        if not filename:
            return
        target = Path(filename)
        if target.suffix.lower() != ".txt":
            target = target.with_suffix(".txt")
        target.write_text(self.result_text, encoding="utf-8")
        show_info(self, f"Resultado salvo em:\n{target}", title="Resultado salvo")
