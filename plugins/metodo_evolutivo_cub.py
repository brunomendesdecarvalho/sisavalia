"""Plugin do método evolutivo com CUB, área equivalente e depreciação."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget,
)

from core.formatting import format_number
from core.plugin_base import BasePlugin
from ui.clipboard import copy_text
from ui.file_dialogs import save_file_name
from ui.widgets import button, show_info, show_warning

try:
    from ._engenharia import (
        HEIDECKE_C, cub_reproduction, equivalent_area, evolutionary_value,
        precision_grade, ross_heidecke,
    )
except ImportError:  # plugin carregado por caminho pelo PluginManager
    from _engenharia import (
        HEIDECKE_C, cub_reproduction, equivalent_area, evolutionary_value,
        precision_grade, ross_heidecke,
    )


class MetodoEvolutivoCub(BasePlugin):
    name = "Método evolutivo e CUB"
    description = (
        "Calcula área equivalente, custo de reprodução pelo CUB, depreciação "
        "física, custo de reedição e valor pelo método evolutivo."
    )

    def run(self, dataframe: pd.DataFrame, parent_widget: Any) -> Any:
        dialog = EvolutionaryDialog(parent_widget)
        dialog.exec()
        return dialog.result_data


class EvolutionaryDialog(QDialog):
    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.result_data: dict[str, Any] | None = None
        self.setWindowTitle("Método evolutivo e CUB — NBR 14653-2")
        self.resize(900, 760)
        outer = QVBoxLayout(self)
        title = QLabel("Método evolutivo e custo de benfeitorias")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        hint = QLabel(
            "O terreno e a construção são somados e corrigidos pelo fator de comercialização. "
            "A depreciação usa a idade, a vida útil e o estado de conservação."
        )
        hint.setWordWrap(True)
        hint.setObjectName("Hint")
        outer.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        area_box = QFormLayout()
        self.private_area = self._spin(0, 100000, 80, 2)
        self.cub = self._spin(0, 100000, 2500, 2)
        self.cub.setPrefix("R$ ")
        area_box.addRow("Área privativa / equivalente (m²):", self.private_area)
        area_box.addRow("CUB (R$/m²):", self.cub)
        root.addLayout(area_box)
        add_title = QLabel("Áreas equivalentes adicionais (NBR 12721)")
        add_title.setObjectName("SectionTitle")
        root.addWidget(add_title)
        add_form = QFormLayout()
        self.additional: list[tuple[QDoubleSpinBox, QDoubleSpinBox]] = []
        for i in range(3):
            area = self._spin(0, 100000, 0, 2)
            price = self._spin(0, 10, 1.0, 2)
            row = QHBoxLayout()
            row.addWidget(QLabel("Área (m²):"))
            row.addWidget(area)
            row.addWidget(QLabel("Peso relativo:"))
            row.addWidget(price)
            row.addStretch(1)
            holder = QWidget()
            holder.setLayout(row)
            add_form.addRow(f"Adicional {i + 1}:", holder)
            self.additional.append((area, price))
        root.addLayout(add_form)
        cost_box = QFormLayout()
        self.oe = self._spin(0, 100000000, 0, 2)
        self.oi = self._spin(0, 100000000, 0, 2)
        self.ofe = self._spin(0, 100000000, 0, 2)
        self.ofd = self._spin(0, 100000000, 0, 2)
        for spin in (self.oe, self.oi, self.ofe, self.ofd):
            spin.setPrefix("R$ ")
        cost_box.addRow("Outros custos (OE):", self.oe)
        cost_box.addRow("Outros impostos (OI):", self.oi)
        cost_box.addRow("Outras fontes externas (OFe):", self.ofe)
        cost_box.addRow("Outras fontes deduzidas (OFd):", self.ofd)
        self.a = self._spin(0, 100, 0, 2)
        self.f = self._spin(0, 100, 0, 2)
        self.l = self._spin(0, 100, 0, 2)
        for spin, label in ((self.a, "A — administração (%)"), (self.f, "F — financiamento (%)"), (self.l, "L — lucro (%)")):
            spin.setSuffix(" %")
            cost_box.addRow(label, spin)
        root.addLayout(cost_box)
        dep_title = QLabel("Depreciação física")
        dep_title.setObjectName("SectionTitle")
        root.addWidget(dep_title)
        dep_box = QFormLayout()
        self.age = self._spin(0, 200, 10, 2)
        self.life = self._spin(1, 200, 60, 2)
        self.state = QComboBox()
        self.state.addItems(list(HEIDECKE_C))
        self.state.setCurrentText("Regular")
        self.manual_dep = self._spin(-1, 100, -1, 2)
        self.manual_dep.setSpecialValueText("Usar Ross-Heidecke")
        self.manual_dep.setSuffix(" %")
        dep_box.addRow("Idade (anos):", self.age)
        dep_box.addRow("Vida útil (anos):", self.life)
        dep_box.addRow("Estado de conservação:", self.state)
        dep_box.addRow("Depreciação manual:", self.manual_dep)
        root.addLayout(dep_box)
        final_box = QFormLayout()
        self.land_value = self._spin(0, 100000000, 0, 2)
        self.land_value.setPrefix("R$ ")
        self.fc = self._spin(0.1, 3, 1.0, 2)
        final_box.addRow("Valor do terreno (VT):", self.land_value)
        final_box.addRow("Fator de comercialização (FC):", self.fc)
        self.use_current = button("Usar estimativa atual", "calculator",
                                  tooltip="Copia o valor adotado/estimado do avaliando selecionado na aba 4.")
        self.use_current.clicked.connect(self._use_current_estimate)
        final_box.addRow("", self.use_current)
        root.addLayout(final_box)
        actions = QHBoxLayout()
        self.calc = button("Calcular", "calculator", primary=True)
        self.copy = button("Copiar resultado", "copy")
        self.save = button("Salvar resultado", "save")
        self.calc.clicked.connect(self.calculate)
        self.copy.clicked.connect(self.copy_result)
        self.save.clicked.connect(self.save_result)
        actions.addWidget(self.calc)
        actions.addWidget(self.copy)
        actions.addWidget(self.save)
        actions.addStretch(1)
        root.addLayout(actions)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setMinimumHeight(220)
        self.result.setAccessibleName("Resultado do método evolutivo")
        root.addWidget(self.result)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        close = button("Fechar", "close")
        close.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close)
        outer.addLayout(bottom)

    @staticmethod
    def _spin(minimum: float, maximum: float, value: float, decimals: int) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setValue(value)
        spin.setSingleStep(1.0 if maximum > 1000 else 0.01)
        return spin

    def _use_current_estimate(self) -> None:
        try:
            window = self.parent().window() if self.parent() is not None else None
            result = getattr(window, "current_evaluation", None)
            if result is None:
                show_warning(self, "Não há avaliando selecionado na aba 4. Informe o VT manualmente.")
                return
            value = result.adopted or result.prediction.point
            self.land_value.setValue(float(value))
            show_info(self, "Valor do terreno copiado da estimativa atual.")
        except Exception:
            show_warning(self, "Não foi possível copiar a estimativa atual. Informe o VT manualmente.")

    def calculate(self) -> None:
        try:
            equivalent = equivalent_area(
                self.private_area.value(),
                [(a.value(), p.value()) for a, p in self.additional],
            )
            cost = cub_reproduction(
                self.cub.value(), equivalent, self.oe.value(), self.oi.value(),
                self.ofe.value(), self.ofd.value(), self.a.value(), self.f.value(), self.l.value(),
            )
            if self.manual_dep.value() >= 0:
                kd = self.manual_dep.value() / 100.0
                residual = 1.0 - kd
            else:
                kd, residual = ross_heidecke(
                    self.age.value(), self.life.value(), self.state.currentText()
                )
            cb = cost * residual
            vi = evolutionary_value(self.land_value.value(), cb, self.fc.value())
        except Exception as exc:
            show_warning(self, f"Não foi possível calcular: {exc}")
            return
        if equivalent <= 0 or self.cub.value() <= 0:
            show_warning(self, "Informe a área equivalente e o CUB maiores que zero.")
            return
        grade = "III" if self.land_value.value() > 0 and self.cub.value() > 0 else "II"
        if self.land_value.value() <= 0:
            grade = "I"
        lines = [
            "Método evolutivo — memória de cálculo",
            f"Área equivalente (S): {format_number(equivalent, 2)} m²",
            f"CUB: R$ {format_number(self.cub.value(), 2)}/m²",
            f"Custo de reprodução (C): R$ {format_number(cost, 2)}",
            f"Depreciação: {format_number(kd * 100, 2)}% "
            f"({'manual' if self.manual_dep.value() >= 0 else 'Ross-Heidecke simplificado'})",
            f"Custo de reedição (CB): R$ {format_number(cb, 2)}",
            f"Valor do terreno (VT): R$ {format_number(self.land_value.value(), 2)}",
            f"Fator de comercialização (FC): {format_number(self.fc.value(), 2)}",
            f"Valor pelo método evolutivo (VI = (VT + CB) × FC): R$ {format_number(vi, 2)}",
            "",
            f"Enquadramento orientativo (Tabelas 6, 7, 10 e 11): Grau {grade}.",
            "Confirme a fonte do CUB, a vida útil, o estado de conservação e o FC no laudo. "
            "O plugin não substitui a análise do avaliador.",
        ]
        self.result_text = "\n".join(lines)
        self.result.setPlainText(self.result_text)
        self.result_data = {
            "equivalent_area": equivalent, "reproduction_cost": cost,
            "depreciation": kd, "construction_value": cb,
            "land_value": self.land_value.value(), "fc": self.fc.value(),
            "value": vi, "grade": grade,
        }

    def copy_result(self) -> None:
        text = getattr(self, "result_text", "").strip()
        if not text:
            show_info(self, "Calcule antes de copiar.")
            return
        copy_text(text)
        show_info(self, "Resultado copiado.")

    def save_result(self) -> None:
        if not getattr(self, "result_data", None):
            show_info(self, "Calcule antes de salvar.")
            return
        filename = save_file_name(
            self, "Salvar método evolutivo", "metodo_evolutivo.txt",
            "Texto (*.txt);;CSV (*.csv)", "txt",
        )
        if not filename:
            return
        target = Path(filename)
        if target.suffix.lower() not in (".txt", ".csv"):
            target = target.with_suffix(".txt")
        target.write_text(self.result_text, encoding="utf-8")
        show_info(self, f"Resultado salvo em:\n{target}", title="Resultado salvo")
