"""Plugin de exemplo: mostra um resumo estatístico das colunas numéricas."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core.formatting import format_number
from core.plugin_base import BasePlugin
from ui.widgets import standard_icon


class ResumoEstatistico(BasePlugin):
    name = "Resumo estatístico"
    description = (
        "Mostra mínimo, máximo, média, mediana, desvio padrão e quantidade de "
        "vazios de cada coluna numérica da amostra."
    )

    def run(self, dataframe: pd.DataFrame, parent_widget: Any) -> Any:
        dialog = QDialog(parent_widget)
        dialog.setWindowTitle("Resumo estatístico — plugin de exemplo")
        dialog.resize(820, 520)
        layout = QVBoxLayout(dialog)
        title = QLabel("Resumo das colunas numéricas")
        title.setFont(QFont("DejaVu Sans", 16, QFont.Weight.Bold))
        layout.addWidget(title)
        subtitle = QLabel(
            "Este é um plugin de exemplo. Ele usa os dados originais, sem alterar a amostra."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        rows = []
        for column in dataframe.columns:
            values = pd.to_numeric(dataframe[column], errors="coerce")
            if values.notna().sum() == 0:
                continue
            rows.append((
                str(column),
                format_number(values.min(), 2),
                format_number(values.max(), 2),
                format_number(values.mean(), 2),
                format_number(values.median(), 2),
                format_number(values.std(), 2),
                str(int(values.isna().sum())),
            ))
        table = QTableWidget(len(rows), 7)
        table.setHorizontalHeaderLabels([
            "Coluna", "Mínimo", "Máximo", "Média", "Mediana", "Desvio padrão", "Vazios",
        ])
        table.setAccessibleName("Tabela de resumo estatístico")
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(value)
                if c > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(r, c, item)
        table.resizeColumnsToContents()
        table.setAlternatingRowColors(True)
        layout.addWidget(table)
        if not rows:
            layout.addWidget(QLabel("Não há colunas numéricas nesta amostra."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setText("Fechar")
            close_button.setIcon(standard_icon("close"))
            close_button.setMinimumHeight(44)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
        return {"rows": len(rows)}
