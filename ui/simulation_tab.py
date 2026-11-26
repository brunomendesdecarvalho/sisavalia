"""Aba 7 — simulação de distribuições."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from core.data_manager import DataManager
from core.formatting import format_number
from core.simulation import (
    DISTRIBUTIONS, SimulationError, descriptive, export_csv, export_xlsx, simulate,
)
from .file_dialogs import save_file_name
from .plots import PlotCard
from .widgets import (
    Banner, Card, button, make_table, readonly_item, show_error, show_info,
    show_warning, toast, ask_yes_no,
)


PARAM_LABELS = {
    "normal": [("mean", "Média"), ("std", "Desvio padrão")],
    "uniform": [("low", "Valor mínimo"), ("high", "Valor máximo")],
    "triangular": [("low", "Valor mínimo"), ("mode", "Valor mais provável"), ("high", "Valor máximo")],
    "exponential": [("mean", "Média")],
    "poisson": [("mean", "Média (quantidade esperada)")],
}
DEFAULTS = {
    "normal": {"mean": "100", "std": "15"},
    "uniform": {"low": "0", "high": "100"},
    "triangular": {"low": "0", "mode": "50", "high": "100"},
    "exponential": {"mean": "10"},
    "poisson": {"mean": "5"},
}


class SimulationTab(QWidget):
    data_loaded = Signal()

    def __init__(self, manager: DataManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.values: Optional[Any] = None
        self._params: dict[str, QLineEdit] = {}
        self._param_holder: Optional[QWidget] = None
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)
        title = QLabel("6. Simulação")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        subtitle = QLabel(
            "Gera números aleatórios para estudar uma distribuição. Os valores são fictícios; "
            "não use em laudo como se fossem dados de mercado."
        )
        subtitle.setObjectName("Hint")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)
        controls = Card(title="Gerar valores")
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel("Distribuição:"))
        self.distribution_combo = QComboBox()
        self.distribution_combo.addItems(list(DISTRIBUTIONS.keys()))
        self.distribution_combo.currentTextChanged.connect(self._rebuild_params)
        top.addWidget(self.distribution_combo)
        top.addWidget(QLabel("Tamanho N:"))
        self.n_spin = QSpinBox()
        self.n_spin.setRange(1, 1_000_000)
        self.n_spin.setValue(1000)
        self.n_spin.setSingleStep(100)
        self.n_spin.setMinimumWidth(150)
        top.addWidget(self.n_spin)
        self.generate_button = button("Gerar simulação", "simulation", primary=True)
        self.generate_button.clicked.connect(self.generate)
        top.addWidget(self.generate_button)
        top.addStretch(1)
        controls.add_layout(top)
        self.param_container = QVBoxLayout()
        controls.add_layout(self.param_container)
        hint = QLabel(
            "Normal: valores em torno da média. Uniforme: todos os valores entre mínimo e máximo têm a mesma chance. "
            "Triangular: o modo é o valor mais provável. Exponencial: muitos valores baixos e alguns altos. "
            "Poisson: contagens inteiras."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        controls.add(hint)
        root.addWidget(controls)
        self.alert = Banner("Escolha os parâmetros e clique em Gerar simulação.", "info")
        root.addWidget(self.alert)
        stats_card = Card(title="Estatísticas da simulação")
        self.stats_table = make_table(["Medida", "Valor"])
        self.stats_table.setMaximumHeight(250)
        stats_card.add(self.stats_table)
        root.addWidget(stats_card)
        export_actions = QHBoxLayout()
        self.csv_button = button("Exportar .csv", "save_image")
        self.xlsx_button = button("Exportar .xlsx", "spreadsheet")
        self.load_button = button("Carregar como dados ativos", "open", primary=False)
        self.csv_button.clicked.connect(self.export_csv_clicked)
        self.xlsx_button.clicked.connect(self.export_xlsx_clicked)
        self.load_button.clicked.connect(self.load_as_data)
        export_actions.addWidget(self.csv_button)
        export_actions.addWidget(self.xlsx_button)
        export_actions.addWidget(self.load_button)
        export_actions.addStretch(1)
        root.addLayout(export_actions)
        self.plot = PlotCard("Histograma dos valores simulados")
        self.plot.setMinimumHeight(560)
        root.addWidget(self.plot)
        root.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self._rebuild_params("Normal")
        self._set_result_actions(False)

    def _rebuild_params(self, distribution: str) -> None:
        key = DISTRIBUTIONS.get(distribution, ("normal",))[0]
        if self._param_holder is not None:
            self.param_container.removeWidget(self._param_holder)
            self._param_holder.deleteLater()
            self._param_holder = None
        self._params = {}
        holder = QWidget()
        form = QFormLayout(holder)
        form.setSpacing(8)
        for param_key, label in PARAM_LABELS[key]:
            edit = QLineEdit(DEFAULTS[key].get(param_key, "0"))
            edit.setAccessibleName(label)
            edit.setToolTip("Aceita vírgula ou ponto decimal.")
            self._params[param_key] = edit
            form.addRow(label + ":", edit)
        self._param_holder = holder
        self.param_container.addWidget(holder)

    def _current_key(self) -> str:
        return DISTRIBUTIONS.get(self.distribution_combo.currentText(), ("normal",))[0]

    def generate(self) -> None:
        params = {key: edit.text() for key, edit in self._params.items()}
        try:
            values = simulate(self._current_key(), params, int(self.n_spin.value()))
        except SimulationError as exc:
            show_error(self, str(exc))
            return
        self.values = values
        stats = descriptive(values)
        rows = [
            ("Quantidade", format_number(stats["n"], 0)),
            ("Mínimo", format_number(stats["min"], 4)),
            ("Máximo", format_number(stats["max"], 4)),
            ("Média", format_number(stats["mean"], 4)),
            ("Mediana", format_number(stats["median"], 4)),
            ("Desvio padrão", format_number(stats["std"], 4)),
        ]
        self.stats_table.setRowCount(len(rows))
        for r, (label, value) in enumerate(rows):
            self.stats_table.setItem(r, 0, readonly_item(label))
            self.stats_table.setItem(r, 1, readonly_item(value, align_right=True))
        self.stats_table.resizeColumnsToContents()
        self.stats_table.setColumnWidth(0, 180)
        self.alert.setVisible(False)
        from core import charting
        fig, _ = charting.simulation_hist(values, distribution=self.distribution_combo.currentText())
        self.plot.set_figure(fig)
        self._set_result_actions(True)

    def _set_result_actions(self, enabled: bool) -> None:
        for button_obj in (self.csv_button, self.xlsx_button, self.load_button):
            button_obj.setEnabled(enabled)

    def _ask_path(self, extension: str) -> Optional[str]:
        filt = "CSV (*.csv)" if extension == "csv" else "Planilha Excel (*.xlsx)"
        path = save_file_name(
            self, "Onde guardar a simulação", str(Path.home() / f"simulacao.{extension}"),
            filt, extension,
        )
        if not path:
            return None
        target = Path(path)
        if target.suffix.lower() != "." + extension:
            target = target.with_suffix("." + extension)
        return str(target)

    def export_csv_clicked(self) -> None:
        if self.values is None:
            return
        path = self._ask_path("csv")
        if not path:
            return
        try:
            export_csv(path, self.values)
        except Exception:
            show_error(self, "Não foi possível gravar o CSV. Confira a pasta escolhida.")
            return
        show_info(self, f"Simulação salva em:\n{path}", title="CSV salvo")

    def export_xlsx_clicked(self) -> None:
        if self.values is None:
            return
        path = self._ask_path("xlsx")
        if not path:
            return
        try:
            export_xlsx(path, self.values)
        except Exception:
            show_error(self, "Não foi possível gravar a planilha. Confira se o arquivo não está aberto.")
            return
        show_info(self, f"Simulação salva em:\n{path}", title="Planilha salva")

    def refresh_theme(self) -> None:
        if self.values is not None:
            from core import charting
            fig, _ = charting.simulation_hist(self.values, distribution=self.distribution_combo.currentText())
            self.plot.set_figure(fig)

    def load_as_data(self) -> None:
        if self.values is None:
            return
        if self.manager.has_data():
            if not ask_yes_no(
                self, "Substituir a amostra atual?",
                "Carregar a simulação como dados ativos substitui todos os dados da tabela atual. "
                "Se quiser guardar o trabalho, salve o projeto antes. Deseja continuar?",
                yes_text="Substituir", no_text="Cancelar",
            ):
                return
        frame = pd.DataFrame({"Valor_simulado": self.values})
        try:
            self.manager.load_dataframe(frame)
        except Exception as exc:
            show_error(self, str(exc))
            return
        self.manager.metadata["sample_note"] = "Dados simulados. Não use em laudo."
        self.data_loaded.emit()
        show_info(
            self,
            "A simulação virou a amostra ativa. Confira as variáveis na aba 1 antes de modelar.",
            title="Dados carregados",
        )
