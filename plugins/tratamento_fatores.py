"""Plugin de tratamento por fatores (NBR 14653-2, Anexo B e Tabelas 3 a 5)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QPlainTextEdit, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from core.formatting import format_number
from core.plugin_base import BasePlugin
from ui.clipboard import copy_text
from ui.file_dialogs import save_file_name
from ui.widgets import button, show_info, show_warning, standard_icon

try:
    from ._engenharia import factor_grades, factor_values, precision_grade
except ImportError:  # plugin carregado por caminho pelo PluginManager
    from _engenharia import factor_grades, factor_values, precision_grade


class TratamentoFatores(BasePlugin):
    name = "Tratamento por fatores"
    description = (
        "Homogeneíza valores por fatores manuais, saneia discrepantes e enquadra "
        "o resultado nas Tabelas 3, 4 e 5 da NBR 14653-2."
    )

    def run(self, dataframe: pd.DataFrame, parent_widget: Any) -> Any:
        dialog = FactorDialog(dataframe, parent_widget)
        dialog.exec()
        return dialog.result_data


class FactorDialog(QDialog):
    def __init__(self, dataframe: pd.DataFrame, parent: Any = None) -> None:
        super().__init__(parent)
        self.dataframe = dataframe.copy()
        self.result_data: dict[str, Any] | None = None
        self.result_text = ""
        self.setWindowTitle("Tratamento por fatores — NBR 14653-2")
        self.resize(980, 760)
        outer = QVBoxLayout(self)
        title = QLabel("Tratamento por fatores")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        hint = QLabel(
            "Escolha o valor, a área (se o valor for total) e informe os fatores de "
            "homogeneização. Cada fator deve ficar entre 0,50 e 2,00; o produto dos "
            "fatores também deve ficar nessa faixa."
        )
        hint.setWordWrap(True)
        hint.setObjectName("Hint")
        outer.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form = QVBoxLayout(inner)
        form.setContentsMargins(10, 10, 10, 10)
        form.setSpacing(10)
        top = QFormLayout()
        self.value_combo = QComboBox()
        for column in self.dataframe.columns:
            numeric = pd.to_numeric(self.dataframe[column], errors="coerce")
            if numeric.notna().sum() >= 2:
                self.value_combo.addItem(str(column))
        self.area_combo = QComboBox()
        self.area_combo.addItem("Não dividir pela área", "")
        for column in self.dataframe.columns:
            numeric = pd.to_numeric(self.dataframe[column], errors="coerce")
            if numeric.notna().sum() >= 2:
                self.area_combo.addItem(str(column), str(column))
        for i in range(self.area_combo.count()):
            text = self.area_combo.itemText(i).lower()
            if "area" in text or "área" in text:
                self.area_combo.setCurrentIndex(i)
                break
        top.addRow("Valor total / unitário:", self.value_combo)
        top.addRow("Área (opcional):", self.area_combo)
        self.criterion = QComboBox()
        self.criterion.addItems(["±30% em torno da média", "Chauvenet"])
        top.addRow("Saneamento:", self.criterion)
        form.addLayout(top)
        factor_title = QLabel("Fatores de homogeneização")
        factor_title.setObjectName("SectionTitle")
        form.addWidget(factor_title)
        self.factor_table = QTableWidget(0, 3)
        self.factor_table.setHorizontalHeaderLabels(["Variável", "Fator", "Critério / observação"])
        self.factor_table.setMinimumHeight(260)
        self.factor_table.setAlternatingRowColors(True)
        self.factor_table.setAccessibleName("Fatores de homogeneização")
        form.addWidget(self.factor_table)
        self._build_factor_rows()
        self.value_combo.currentTextChanged.connect(self._build_factor_rows)
        grade_box = QFormLayout()
        self.item1 = QComboBox()
        self.item1.addItem("III — completa quanto a todos os fatores", "III")
        self.item1.addItem("II — completa quanto aos fatores utilizados", "II")
        self.item1.addItem("I — situação-paradigma", "I")
        self.item3 = QComboBox()
        self.item3.addItem("III — todas as características observadas", "III")
        self.item3.addItem("II — informações dos dados analisadas", "II")
        self.item3.addItem("I — dados mínimos", "I")
        grade_box.addRow("Item 1 — caracterização:", self.item1)
        grade_box.addRow("Item 3 — identificação dos dados:", self.item3)
        form.addLayout(grade_box)
        actions = QHBoxLayout()
        self.calc_button = button("Calcular", "calculator", primary=True)
        self.copy_button = button("Copiar resultado", "copy")
        self.csv_button = button("Salvar CSV", "save")
        self.calc_button.clicked.connect(self.calculate)
        self.copy_button.clicked.connect(self.copy_result)
        self.csv_button.clicked.connect(self.save_csv)
        actions.addWidget(self.calc_button)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.csv_button)
        actions.addStretch(1)
        form.addLayout(actions)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setPlaceholderText("O resultado do tratamento aparece aqui.")
        self.result.setMinimumHeight(210)
        self.result.setAccessibleName("Resultado do tratamento por fatores")
        form.addWidget(self.result)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        close = button("Fechar", "close")
        close.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close)
        outer.addLayout(bottom)
        self._spins: dict[str, QDoubleSpinBox] = {}

    def _build_factor_rows(self) -> None:
        value_column = self.value_combo.currentText()
        numeric = [
            str(c) for c in self.dataframe.columns
            if c != value_column and pd.to_numeric(self.dataframe[c], errors="coerce").notna().sum() >= 2
        ]
        self.factor_table.setRowCount(len(numeric))
        self._spins = {}
        for row, column in enumerate(numeric):
            item = QTableWidgetItem(column)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.factor_table.setItem(row, 0, item)
            spin = QDoubleSpinBox()
            spin.setRange(0.05, 10.0)
            spin.setDecimals(2)
            spin.setSingleStep(0.01)
            spin.setValue(1.0)
            spin.setSuffix(" ×")
            spin.setToolTip("Fator de homogeneização desta variável. A faixa da norma é 0,50 a 2,00.")
            spin.setAccessibleName(f"Fator de {column}")
            self.factor_table.setCellWidget(row, 1, spin)
            self._spins[column] = spin
            note = "Use 1,00 para não alterar."
            if "oferta" in column.lower():
                note = "Ex.: fator de oferta 0,90 para preço anunciado."
            self.factor_table.setItem(row, 2, QTableWidgetItem(note))
        self.factor_table.resizeColumnsToContents()
        self.factor_table.setColumnWidth(0, 220)
        self.factor_table.setColumnWidth(1, 110)
        self.factor_table.setColumnWidth(2, 320)

    def calculate(self) -> None:
        value_column = self.value_combo.currentText()
        if not value_column:
            show_warning(self, "Escolha a coluna de valor.")
            return
        try:
            values = pd.to_numeric(self.dataframe[value_column], errors="coerce").tolist()
            area_column = self.area_combo.currentData()
            areas = pd.to_numeric(self.dataframe[area_column], errors="coerce").tolist() if area_column else None
            factors = [spin.value() for spin in self._spins.values()]
            used_factors = [(name, spin.value()) for name, spin in self._spins.items()
                            if abs(spin.value() - 1.0) > 1e-9]
            result = factor_values(values, factors, area=areas,
                                   criterion=self.criterion.currentText())
        except Exception as exc:
            show_warning(self, f"Não foi possível calcular: {exc}")
            return
        outside = [(name, value) for name, value in used_factors if value < 0.5 or value > 2.0]
        interval_ok = (
            abs(result.factor_product - 1.0) < 1e-9
            or 0.5 <= result.factor_product <= 2.0
        ) and 0.5 <= result.factor_min <= 2.0 and 0.5 <= result.factor_max <= 2.0
        grades = factor_grades(
            result.n,
            str(self.item1.currentData()),
            str(self.item3.currentData()),
            interval_ok,
            result.cv_before,
            result.cv_after,
        )
        precision = precision_grade(result.amplitude_pct)
        factor_lines = [f"{name}: {format_number(value, 2)}" for name, value in used_factors] or ["Nenhum fator diferente de 1,00."]
        lines = [
            f"Valor analisado: {value_column}",
            f"Área usada: {self.area_combo.currentText() if self.area_combo.currentData() else 'valor já unitário'}",
            f"Critério de saneamento: {self.criterion.currentText()}",
            "",
            "Fatores aplicados:",
            *factor_lines,
            f"Produto dos fatores: {format_number(result.factor_product, 4)}",
            "",
            f"Valores válidos: {result.n}",
            f"Média homogeneizada: {format_number(result.mean, 2)}",
            f"Mediana: {format_number(result.median, 2)}",
            f"Desvio padrão: {format_number(result.std, 2)}",
            f"Coeficiente de variação antes: {format_number(result.cv_before, 2)}%",
            f"Coeficiente de variação depois: {format_number(result.cv_after, 2)}%",
            f"IC 80% da média: {format_number(result.ci_low, 2)} a {format_number(result.ci_high, 2)}",
            f"Amplitude do IC 80%: {format_number(result.amplitude_pct, 2)}%",
            "",
            f"Grau de fundamentação (Tabelas 3 e 4): {grades['final']} "
            f"(pontos: {grades['total']})",
            f"Itens: 1={grades['item1']}, 2={grades['item2']}, 3={grades['item3']}, 4={grades['item4']}",
            f"Grau de precisão (Tabela 5): {precision}",
            "",
        ]
        if outside:
            lines.append("ATENÇÃO: fatores fora de [0,50; 2,00]: " + ", ".join(f"{n} ({v:.2f})" for n, v in outside))
        if not interval_ok:
            lines.append("ATENÇÃO: o produto ou algum fator está fora do intervalo admissível de 0,50 a 2,00.")
        if grades["heterogeneizou"] == "Sim":
            lines.append(
                "ATENÇÃO: o coeficiente de variação aumentou. A homogeneização pode estar "
                "heterogeneizando a amostra (item B.6)."
            )
        if result.removed:
            lines.append(f"Discrepantes retirados, um a um: {len(result.removed)} (posições {result.removed}).")
        if not result.removed:
            lines.append("Nenhum discrepante retirado pelo critério escolhido.")
        lines.append("")
        lines.append(
            "Enquadramento orientativo: confira a Tabela 3/4/5 e o julgamento do avaliador. "
            "O plugin não altera a amostra original."
        )
        self.result_text = "\n".join(lines)
        self.result.setPlainText(self.result_text)
        self.result_data = {
            "value_column": value_column,
            "factors": dict(used_factors),
            "result": result,
            "grades": grades,
            "precision": precision,
        }

    def copy_result(self) -> None:
        text = getattr(self, "result_text", "").strip()
        if not text:
            show_info(self, "Calcule o tratamento antes de copiar.")
            return
        copy_text(text)
        show_info(self, "Resultado copiado.")

    def save_csv(self) -> None:
        if not getattr(self, "result_data", None):
            show_info(self, "Calcule o tratamento antes de salvar.")
            return
        filename = save_file_name(
            self, "Salvar tratamento por fatores", "tratamento_fatores.csv",
            "Planilha CSV (*.csv)", "csv",
        )
        if not filename:
            return
        target = Path(filename)
        if target.suffix.lower() != ".csv":
            target = target.with_suffix(".csv")
        data = self.result_data
        lines = ["variavel;valor_homogeneizado"]
        for value in data["result"].unit_values:
            lines.append(f"{data['value_column']};{value:.6f}".replace(".", ","))
        lines.append("")
        lines.append(self.result_text)
        target.write_text("\n".join(lines), encoding="utf-8-sig")
        show_info(self, f"Arquivo salvo em:\n{target}", title="CSV salvo")
