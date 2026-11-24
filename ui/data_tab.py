"""Aba 1 — Dados, colunas, tipos, transformações e avaliandos."""
from __future__ import annotations

import copy
from typing import Any, Optional

import pandas as pd

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.data_manager import (
    CATEGORICAL_TYPES, COLUMN_TYPES, SIGNS, TEXT_TYPE, TRANSFORMS, DataManager,
)
from core.formatting import format_number, is_missing
from .clipboard import copy_text
from .dialogs import (
    AddColumnDialog, CalculatedColumnDialog, DeleteColumnDialog, EvaluatedDialog,
    MetadataDialog, RenameColumnDialog,
)
from .tooltips import tip
from .widgets import (
    Banner, Card, button, format_data_number, make_table, refresh_style,
    show_error, show_info, show_warning, standard_icon, toast, ask_yes_no,
)
from .theme import table_row_height


SIGN_LABEL = {1: "Subir", -1: "Descer", 0: "Tanto faz"}
SIGN_VALUE = {v: k for k, v in SIGN_LABEL.items()}


class DataTab(QWidget):
    data_changed = Signal(str)
    status_message = Signal(str)
    open_spreadsheet_requested = Signal()

    def __init__(self, manager: DataManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self._loading = False
        self._sort_column = -1
        self._sort_ascending = True
        self._last_search_row = -1
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ visual
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setAccessibleName("Conteúdo da aba Dados")
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("1. Dados")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "A primeira coluna desliga o imóvel de todos os cálculos sem apagar os dados. "
            "Clique no título de uma coluna para ordenar."
        )
        subtitle.setObjectName("Hint")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        self.metadata_button = button("Dados do trabalho", "metadata",
                                      tooltip="Nome do trabalho, autor, data, município e tipologia.")
        self.metadata_button.clicked.connect(self.edit_metadata)
        header.addWidget(self.metadata_button, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)
        self.sample_note = Banner("", "warning")
        self.sample_note.setVisible(False)
        root.addWidget(self.sample_note)
        actions1 = QGridLayout()
        actions1.setSpacing(7)
        self.import_button = button("Importar planilha", "open")
        self.paste_button = button("Colar do Calc", "copy")
        self.add_row_button = button("Incluir linha", "add")
        self.delete_row_button = button("Excluir linha", "delete", danger=True)
        self.add_column_button = button("Incluir coluna", "add")
        self.rename_column_button = button("Renomear coluna", "edit")
        self.delete_column_button = button("Excluir coluna", "delete", danger=True)
        self.import_button.clicked.connect(self.open_spreadsheet_requested)
        self.paste_button.clicked.connect(self.paste_from_calc)
        self.add_row_button.clicked.connect(self.add_row)
        self.delete_row_button.clicked.connect(self.delete_rows)
        self.add_column_button.clicked.connect(self.add_column)
        self.rename_column_button.clicked.connect(self.rename_column)
        self.delete_column_button.clicked.connect(self.delete_column)
        for index, btn in enumerate((
            self.import_button, self.paste_button, self.add_row_button,
            self.delete_row_button, self.add_column_button,
            self.rename_column_button, self.delete_column_button,
        )):
            actions1.addWidget(btn, index // 4, index % 4)
        root.addLayout(actions1)
        actions2 = QHBoxLayout()
        actions2.setSpacing(7)
        self.calc_button = button("Nova coluna calculada", "calculator",
                                  tooltip="Cria uma coluna a partir de outra, como Valor total ÷ Área.")
        self.undo_button = button("Desfazer", "undo",
                                  tooltip="Desfaz a última alteração estrutural ou a última desativação em lote.")
        self.reactivate_button = button("Reativar todos", "refresh",
                                        tooltip="Liga de novo todos os imóveis desligados.")
        self.copy_button = button("Copiar tabela", "copy",
                                  tooltip="Copia a tabela para colar no LibreOffice Calc.")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Localizar na tabela...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(210)
        self.search_edit.returnPressed.connect(self.find_next)
        self.search_button = button("Localizar", "search")
        self.calc_button.clicked.connect(self.calculated_column)
        self.undo_button.clicked.connect(self.undo)
        self.reactivate_button.clicked.connect(self.reactivate_all)
        self.copy_button.clicked.connect(self.copy_table)
        self.search_button.clicked.connect(self.find_next)
        for btn in (self.calc_button, self.undo_button, self.reactivate_button, self.copy_button):
            actions2.addWidget(btn)
        actions2.addStretch(1)
        root.addLayout(actions2)
        actions3 = QHBoxLayout()
        actions3.setSpacing(7)
        actions3.addStretch(1)
        actions3.addWidget(QLabel("Localizar:"))
        actions3.addWidget(self.search_edit)
        actions3.addWidget(self.search_button)
        root.addLayout(actions3)
        self.alert_banner = Banner("", "info")
        self.alert_banner.setVisible(False)
        root.addWidget(self.alert_banner)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                   QAbstractItemView.EditTrigger.EditKeyPressed |
                                   QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().sectionClicked.connect(self.sort_by_header)
        self.table.horizontalHeader().setSortIndicatorShown(False)
        self.table.setWordWrap(False)
        self.table.itemChanged.connect(self.cell_changed)
        self.table.setAccessibleName("Tabela de dados dos imóveis")
        left_layout.addWidget(self.table, 1)
        self.table_hint = QLabel(
            "Dica: desmarque Ativo para tirar o imóvel das contas. Clique duas vezes numa célula para corrigir."
        )
        self.table_hint.setObjectName("Hint")
        self.table_hint.setWordWrap(True)
        left_layout.addWidget(self.table_hint)
        splitter.addWidget(left)
        splitter.addWidget(self._build_variables_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([800, 570])
        root.addWidget(splitter, 1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def _build_variables_panel(self) -> QWidget:
        panel = Card(title="Variáveis do modelo",
                     subtitle="Texto não entra na conta. Marque uma coluna de texto como rótulo para identificar os imóveis.")
        form = QFormLayout()
        form.setSpacing(8)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.y_combo = QComboBox()
        self.y_combo.setToolTip("Variável dependente: é o valor que a equação vai explicar.")
        self.y_combo.setAccessibleName("Variável dependente Y")
        self.y_transform_combo = QComboBox()
        self.y_transform_combo.addItems(list(TRANSFORMS))
        self.y_transform_combo.setToolTip(tip("transformacao"))
        self.label_combo = QComboBox()
        self.label_combo.setToolTip("Coluna de texto que identifica o imóvel nos gráficos e nas tabelas.")
        form.addRow("Variável Y:", self.y_combo)
        form.addRow("Transformação de Y:", self.y_transform_combo)
        form.addRow("Coluna de rótulo:", self.label_combo)
        panel.add_layout(form)
        self.y_combo.currentTextChanged.connect(self.y_changed)
        self.y_transform_combo.currentTextChanged.connect(self.y_transform_changed)
        self.label_combo.currentTextChanged.connect(self.label_changed)
        hint = QLabel(
            "Marque as variáveis que entram como X. “Dicotômica”, “Código alocado” e “Código ajustado” só usam x. "
            "O sinal esperado gera aviso quando a equação vai no sentido contrário; o coeficiente não é forçado."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        panel.add(hint)
        self.var_scroll = QScrollArea()
        self.var_scroll.setWidgetResizable(True)
        self.var_scroll.setMinimumHeight(300)
        self.var_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.var_scroll.setAccessibleName("Configuração das variáveis independentes")
        self.var_container = QWidget()
        self.var_rows_layout = QVBoxLayout(self.var_container)
        self.var_rows_layout.setContentsMargins(0, 0, 4, 0)
        self.var_rows_layout.setSpacing(6)
        self.var_scroll.setWidget(self.var_container)
        panel.body.addWidget(self.var_scroll, 1)
        return panel

    # --------------------------------------------------------------- carregar
    def set_manager(self, manager: DataManager) -> None:
        self.manager = manager
        self._sort_column = -1
        self._sort_ascending = True
        self.refresh()

    def refresh(self) -> None:
        self._loading = True
        try:
            self._refresh_table()
            self._refresh_variable_panel()
            self._update_sample_note()
            self._validate()
            self.undo_button.setEnabled(self.manager.can_undo())
            self.table_hint.setText(
                f"Clique duas vezes numa célula para corrigir. {self.manager.n_active} imóvel(is) ligado(s), "
                f"{self.manager.n_inactive} desligado(s)."
            )
        finally:
            self._loading = False

    def _refresh_table(self) -> None:
        selected_ids = self._selected_row_ids()
        self.table.blockSignals(True)
        self.table.clear()
        headers = ["Ativo"] + [str(c) for c in self.manager.df.columns]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(self.manager.df))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for col in range(1, len(headers)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(col, 130)
        for row in range(len(self.manager.df)):
            check = QCheckBox()
            check.setChecked(bool(self.manager.active[row]))
            check.setToolTip(
                "Marque para este imóvel entrar em todos os cálculos. Desmarque para tirá-lo sem apagar."
            )
            check.setAccessibleName(f"Ativo: {self.manager.label_for_row(row)}")
            check.toggled.connect(lambda checked, r=row: self._active_toggled(r, checked))
            wrap = QWidget()
            wrap_layout = QHBoxLayout(wrap)
            wrap_layout.setContentsMargins(2, 0, 2, 0)
            wrap_layout.addWidget(check, 0, Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 0, wrap)
            for col_idx, column in enumerate(self.manager.df.columns, start=1):
                value = self.manager.df.iloc[row][column]
                if self.manager.column_types.get(column) == TEXT_TYPE:
                    text = "" if is_missing(value) else str(value)
                else:
                    text = format_data_number(value)
                item = QTableWidgetItem(text)
                if self.manager.column_types.get(column) != TEXT_TYPE:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setToolTip(f"{column}: {text}" if text else f"{column}: vazio")
                self.table.setItem(row, col_idx, item)
            self.table.setRowHeight(row, table_row_height())
        header = self.table.horizontalHeader()
        header.setSortIndicatorShown(self._sort_column >= 0)
        if self._sort_column >= 0:
            header.setSortIndicator(self._sort_column,
                                    Qt.SortOrder.AscendingOrder if self._sort_ascending
                                    else Qt.SortOrder.DescendingOrder)
        self.table.blockSignals(False)
        if selected_ids:
            self._select_row_ids(selected_ids)
        elif self.manager.df.shape[0]:
            self.table.selectRow(0)

    def _refresh_variable_panel(self) -> None:
        self._loading = True
        try:
            numeric = self.manager.numeric_columns()
            current_y = self.manager.y_column or ""
            self.y_combo.blockSignals(True)
            self.y_combo.clear()
            self.y_combo.addItem("— escolha —", "")
            for col in numeric:
                self.y_combo.addItem(col, col)
            index = self.y_combo.findData(current_y)
            self.y_combo.setCurrentIndex(index if index >= 0 else 0)
            self.y_combo.blockSignals(False)
            self.y_transform_combo.blockSignals(True)
            self.y_transform_combo.setCurrentText(self.manager.y_transform)
            self.y_transform_combo.blockSignals(False)
            text_cols = self.manager.text_columns()
            current_label = self.manager.label_column or ""
            self.label_combo.blockSignals(True)
            self.label_combo.clear()
            self.label_combo.addItem("— nenhuma —", "")
            for col in text_cols:
                self.label_combo.addItem(col, col)
            idx = self.label_combo.findData(current_label)
            self.label_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.label_combo.blockSignals(False)
            self._build_var_rows()
        finally:
            self._loading = False

    def _build_var_rows(self) -> None:
        while self.var_rows_layout.count():
            item = self.var_rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        numeric = self.manager.numeric_columns()
        if not numeric:
            empty = QLabel("Não há variáveis numéricas. Colunas de texto não entram no modelo.")
            empty.setObjectName("Hint")
            empty.setWordWrap(True)
            self.var_rows_layout.addWidget(empty)
            self.var_rows_layout.addStretch(1)
            return
        for column in numeric:
            cfg = self.manager.x_config.setdefault(
                column, {"selected": False, "transformation": "x", "expected_sign": 0}
            )
            holder = QFrame()
            holder.setObjectName("SubCard")
            row_layout = QVBoxLayout(holder)
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(4)
            top_row = QHBoxLayout()
            top_row.setSpacing(6)
            check = QCheckBox(column)
            font = check.font()
            font.setBold(True)
            check.setFont(font)
            is_y = column == self.manager.y_column
            check.setChecked(bool(cfg.get("selected", False)) and not is_y)
            check.setEnabled(not is_y)
            check.setToolTip(
                "Marque para esta variável entrar como X."
                if not is_y else "Esta é a variável Y; escolha outra coluna para ser X."
            )
            check.setAccessibleName(f"Usar {column} como X")
            if is_y:
                check.setText(f"{column}  —  variável Y")
            check.stateChanged.connect(
                lambda state, col=column: self.var_selection_changed(col, state)
            )
            top_row.addWidget(check, 1)
            top_row.addWidget(QLabel("Tipo:"), 0)
            type_combo = QComboBox()
            type_combo.addItems(list(COLUMN_TYPES))
            type_combo.setCurrentText(self.manager.column_types.get(column, "Quantitativa"))
            type_combo.setMaximumWidth(185)
            type_combo.setToolTip(
                "Quantitativa: número medido. Dicotômica: dois valores, como 0 e 1. "
                "Código alocado: escala ordinal 1, 2, 3... Código ajustado: categoria já "
                "transformada em código por dummies. Proxy: substituta de outra medida."
            )
            type_combo.setAccessibleName(f"Tipo de {column}")
            type_combo.currentTextChanged.connect(
                lambda value, col=column: self.var_type_changed(col, value)
            )
            top_row.addWidget(type_combo, 0)
            row_layout.addLayout(top_row)
            bottom_row = QHBoxLayout()
            bottom_row.setSpacing(5)
            bottom_row.addWidget(QLabel("Transformação:"))
            trans_combo = QComboBox()
            allowed = ["x"] if self.manager.column_types.get(column) in CATEGORICAL_TYPES else list(TRANSFORMS)
            trans_combo.addItems(allowed)
            trans_combo.setCurrentText(cfg.get("transformation", "x"))
            trans_combo.setToolTip(tip("transformacao"))
            trans_combo.setAccessibleName(f"Transformação de {column}")
            trans_combo.setEnabled(not is_y)
            trans_combo.setMaximumWidth(125)
            trans_combo.currentTextChanged.connect(
                lambda value, col=column: self.var_transform_changed(col, value)
            )
            bottom_row.addWidget(trans_combo)
            bottom_row.addWidget(QLabel("Sinal:"))
            sign_combo = QComboBox()
            sign_combo.addItems(list(SIGNS))
            sign_combo.setCurrentText(SIGN_LABEL.get(int(cfg.get("expected_sign", 0)), "Tanto faz"))
            sign_combo.setToolTip(tip("sinal_esperado"))
            sign_combo.setAccessibleName(f"Sinal esperado de {column}")
            sign_combo.setEnabled(not is_y)
            sign_combo.setMaximumWidth(150)
            sign_combo.currentTextChanged.connect(
                lambda value, col=column: self.var_sign_changed(col, value)
            )
            bottom_row.addWidget(sign_combo)
            bottom_row.addStretch(1)
            row_layout.addLayout(bottom_row)
            description_edit = QLineEdit()
            description_edit.setPlaceholderText(
                "Critério da escala / descrição para o laudo (opcional)"
            )
            description_edit.setToolTip(
                "Ex.: “1 = sem vista; 2 = vista parcial; 3 = vista para o mar”. "
                "Este texto pode ser incluído no laudo (NBR 14653-2, item 10.1 j)."
            )
            description_edit.setAccessibleName(f"Descrição da escala de {column}")
            description_edit.setText(str(cfg.get("description", "") or ""))
            description_edit.textChanged.connect(
                lambda text, col=column: self.variable_description_changed(col, text)
            )
            row_layout.addWidget(description_edit)
            self.var_rows_layout.addWidget(holder)
        self.var_rows_layout.addStretch(1)

    def _update_sample_note(self) -> None:
        note = str(self.manager.metadata.get("sample_note", "") or "")
        if note:
            self.sample_note.setText(note)
            self.sample_note.setVisible(True)
        else:
            self.sample_note.setVisible(False)

    def _validate(self) -> None:
        errors, warnings = self.manager.validate()
        messages = []
        if errors:
            messages.extend("• " + e for e in errors)
        if warnings:
            messages.extend("• " + w for w in warnings)
        if messages:
            self.alert_banner.setText("\n".join(messages))
            self.alert_banner.set_role("error" if errors else "warning")
            self.alert_banner.setVisible(True)
        else:
            self.alert_banner.setVisible(False)

    # --------------------------------------------------------------- seleção
    def _selected_row_ids(self) -> list[int]:
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()})
        return [self.manager.row_ids[r] for r in rows if 0 <= r < len(self.manager.row_ids)]

    def _select_row_ids(self, row_ids: list[int]) -> None:
        rows = [self.manager.row_ids.index(rid) for rid in row_ids if rid in self.manager.row_ids]
        if not rows:
            return
        self.table.clearSelection()
        for row in rows[:1]:
            self.table.selectRow(row)
            self.table.scrollToItem(self.table.item(row, 0))

    @property
    def selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    # ------------------------------------------------------------------ edição
    def _active_toggled(self, row: int, checked: bool) -> None:
        if self._loading:
            return
        if not (0 <= row < len(self.manager.active)):
            return
        if bool(self.manager.active[row]) == bool(checked):
            return
        self.manager.toggle_active(row, checked)
        self._update_active_labels()
        self._validate()
        self.data_changed.emit("active")

    def cell_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        row, col = item.row(), item.column()
        if row < 0 or col < 0:
            return
        if col == 0:
            active = item.checkState() == Qt.CheckState.Checked
            if bool(self.manager.active[row]) != active:
                self.manager.toggle_active(row, active)
                self._update_active_labels()
                self.data_changed.emit("active")
                self._validate()
            return
        column = self.manager.df.columns[col - 1]
        try:
            self.manager.update_cell(row, column, item.text())
        except ValueError as exc:
            show_error(self, str(exc), title="Valor não aceito")
            self.refresh()
            return
        self.refresh()
        self.data_changed.emit("data")

    def _update_active_labels(self) -> None:
        self.table_hint.setText(
            f"Clique duas vezes numa célula para corrigir. {self.manager.n_active} imóvel(is) ligado(s), "
            f"{self.manager.n_inactive} desligado(s)."
        )

    def y_changed(self, text: str) -> None:
        if self._loading:
            return
        value = self.y_combo.currentData() or None
        if value == self.manager.y_column:
            return
        try:
            self.manager.set_y(value)
        except ValueError as exc:
            show_error(self, str(exc))
            self.refresh()
            return
        if value and value in self.manager.x_config:
            self.manager.x_config[value]["selected"] = False
        self.refresh()
        self.data_changed.emit("config")

    def y_transform_changed(self, text: str) -> None:
        if self._loading:
            return
        problem = self._transform_problem(self.manager.y_column, text)
        if problem:
            show_error(self, problem)
            self.refresh()
            return
        self.manager.set_y_transform(text)
        self._validate()
        self.data_changed.emit("config")

    def _transform_problem(self, column: Optional[str], transformation: str) -> str:
        if not column or transformation == "x":
            return ""
        if column not in self.manager.df.columns:
            return "A coluna escolhida não existe."
        values = pd.to_numeric(self.manager.df[column], errors="coerce")[self.manager.active_mask()].dropna()
        if transformation in ("ln(x)", "1/x") and len(values) and (values <= 0).any():
            return (
                f"Não é possível usar {transformation} em “{column}”: há valor zero ou negativo. "
                "Corrija os dados ou escolha x."
            )
        if transformation == "√x" and len(values) and (values < 0).any():
            return f"Não é possível usar √x em “{column}”: há valor negativo."
        return ""

    def label_changed(self, text: str) -> None:
        if self._loading:
            return
        self.manager.label_column = self.label_combo.currentData() or None
        self.data_changed.emit("data")

    def var_selection_changed(self, column: str, state: int) -> None:
        if self._loading:
            return
        selected = bool(state)
        if selected and column == self.manager.y_column:
            show_warning(self, "Esta coluna é a variável Y. Escolha outra coluna para ser X.")
            self._build_var_rows()
            return
        self.manager.set_x(column, selected=selected)
        self._validate()
        self.data_changed.emit("config")

    def var_type_changed(self, column: str, value: str) -> None:
        if self._loading:
            return
        try:
            self.manager.set_column_type(column, value)
        except ValueError as exc:
            show_error(self, str(exc))
            self.refresh()
            return
        QTimer.singleShot(0, self.refresh)
        self.data_changed.emit("config")

    def var_transform_changed(self, column: str, value: str) -> None:
        if self._loading:
            return
        problem = self._transform_problem(column, value)
        if problem:
            show_error(self, problem)
            self.refresh()
            return
        try:
            self.manager.set_x(column, transformation=value)
        except ValueError as exc:
            show_error(self, str(exc))
            self.refresh()
            return
        self._validate()
        self.data_changed.emit("config")

    def var_sign_changed(self, column: str, value: str) -> None:
        if self._loading:
            return
        self.manager.set_x(column, expected_sign=SIGN_VALUE.get(value, 0))
        self.data_changed.emit("config")

    def variable_description_changed(self, column: str, text: str) -> None:
        if self._loading:
            return
        self.manager.set_x_description(column, text)
        self.data_changed.emit("metadata")

    # --------------------------------------------------------------- estruturas
    def add_row(self) -> None:
        if not self.manager.has_data():
            show_warning(self, "Inclua ou importe dados antes de adicionar uma linha.")
            return
        self.manager.add_row()
        self.refresh()
        self.table.scrollToBottom()
        self.data_changed.emit("structure")

    def delete_rows(self) -> None:
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()})
        if not rows:
            show_warning(self, "Selecione a linha ou as linhas que deseja excluir.")
            return
        if not ask_yes_no(
            self, "Excluir linha",
            f"Excluir {len(rows)} imóvel(is) da tabela? Esta ação apaga os valores. "
            "Use Desfazer se foi engano.",
            yes_text="Excluir", no_text="Cancelar",
        ):
            return
        removed = self.manager.delete_rows(rows)
        self.refresh()
        self.data_changed.emit("structure")
        self.status_message.emit(f"{removed} linha(s) excluída(s).")

    def add_column(self) -> None:
        dialog = AddColumnDialog(self)
        if dialog.exec() != AddColumnDialog.DialogCode.Accepted:
            return
        name, column_type = dialog.values()
        try:
            self.manager.add_column(name, column_type=column_type)
        except ValueError as exc:
            show_error(self, str(exc))
            return
        self.refresh()
        self.data_changed.emit("structure")

    def rename_column(self) -> None:
        if not list(self.manager.df.columns):
            show_warning(self, "Ainda não há colunas para renomear.")
            return
        dialog = RenameColumnDialog([str(c) for c in self.manager.df.columns], self)
        if dialog.exec() != RenameColumnDialog.DialogCode.Accepted:
            return
        old, new = dialog.values()
        try:
            self.manager.rename_column(old, new)
        except ValueError as exc:
            show_error(self, str(exc))
            return
        self.refresh()
        self.data_changed.emit("structure")

    def delete_column(self) -> None:
        if not list(self.manager.df.columns):
            show_warning(self, "Ainda não há colunas para excluir.")
            return
        dialog = DeleteColumnDialog([str(c) for c in self.manager.df.columns], self)
        if dialog.exec() != DeleteColumnDialog.DialogCode.Accepted:
            return
        column = dialog.column()
        if not ask_yes_no(
            self, "Excluir coluna",
            f"Excluir a coluna “{column}” e todos os valores dela?",
            yes_text="Excluir", no_text="Cancelar",
        ):
            return
        try:
            self.manager.delete_column(column)
        except ValueError as exc:
            show_error(self, str(exc))
            return
        self.refresh()
        self.data_changed.emit("structure")

    def calculated_column(self) -> None:
        if not self.manager.numeric_columns():
            show_warning(self, "É preciso ter pelo menos uma coluna numérica para calcular.")
            return
        dialog = CalculatedColumnDialog(self.manager, self)
        if dialog.exec() == CalculatedColumnDialog.DialogCode.Accepted:
            self.refresh()
            self.data_changed.emit("structure")
            if dialog.created_column:
                self.status_message.emit(f"Coluna “{dialog.created_column}” criada.")

    def undo(self) -> None:
        if not self.manager.undo():
            show_info(self, "Não há alteração estrutural ou desativação em lote para desfazer.")
            return
        self.refresh()
        self.data_changed.emit("structure")
        self.status_message.emit("Última alteração desfeita.")

    def reactivate_all(self) -> None:
        changed = self.manager.reactivate_all()
        if not changed:
            show_info(self, "Todos os imóveis já estão ligados.")
            return
        self.refresh()
        self.data_changed.emit("active")
        self.status_message.emit(f"{changed} imóvel(is) reativado(s).")

    def copy_table(self) -> None:
        if not self.manager.has_data():
            show_warning(self, "Ainda não há dados para copiar.")
            return
        copy_text(self.manager.copy_table_tsv())
        toast(self, "Tabela copiada. Cole no LibreOffice Calc com Ctrl+V.")

    def paste_from_calc(self) -> None:
        from PySide6.QtWidgets import QApplication
        text = QApplication.clipboard().text()
        try:
            frame = self.manager.parse_pasted_text(text)
        except ValueError as exc:
            show_error(self, str(exc), title="Não foi possível colar")
            return
        if self.manager.has_data():
            if not ask_yes_no(
                self, "Substituir os dados atuais?",
                "Há dados na tabela. Colar do Calc substitui toda a amostra atual. Deseja continuar?",
                yes_text="Substituir", no_text="Cancelar",
            ):
                return
        try:
            self.manager.load_dataframe(frame)
        except ValueError as exc:
            show_error(self, str(exc))
            return
        self.refresh()
        self.data_changed.emit("replaced")

    def edit_metadata(self) -> None:
        dialog = MetadataDialog(self.manager.metadata, self)
        if dialog.exec() != MetadataDialog.DialogCode.Accepted:
            return
        self.manager.set_metadata(dialog.metadata())
        self._update_sample_note()
        self.data_changed.emit("metadata")

    # ---------------------------------------------------------------- ordenação
    def sort_by_header(self, section: int) -> None:
        if not self.manager.has_data() or section < 0:
            return
        selected_ids = self._selected_row_ids()
        ascending = not (self._sort_column == section and self._sort_ascending)
        self._sort_column = section
        self._sort_ascending = ascending
        try:
            if section == 0:
                order = sorted(range(len(self.manager.df)),
                               key=lambda i: (not self.manager.active[i], i),
                               reverse=not ascending)
                self.manager.push_undo()
                self.manager.df = self.manager.df.iloc[order].reset_index(drop=True)
                self.manager.active = [self.manager.active[i] for i in order]
                self.manager.row_ids = [self.manager.row_ids[i] for i in order]
            else:
                column = self.manager.df.columns[section - 1]
                self.manager.sort_by(str(column), ascending=ascending)
        except ValueError as exc:
            show_error(self, str(exc))
            return
        self.refresh()
        self._select_row_ids(selected_ids)
        self.data_changed.emit("structure")

    # ------------------------------------------------------------------ buscar
    def find_next(self) -> None:
        term = self.search_edit.text().strip()
        if not term:
            show_info(self, "Digite o que deseja localizar.")
            return
        if not self.manager.has_data():
            show_warning(self, "Ainda não há dados para localizar.")
            return
        start = self.selected_row + 1
        if start < 0:
            start = 0
        total = self.table.rowCount()
        term_folded = term.casefold()
        order = list(range(start, total)) + list(range(0, start))
        for row in order:
            for col in range(1, self.table.columnCount()):
                item = self.table.item(row, col)
                if item is not None and term_folded in item.text().casefold():
                    self.table.clearSelection()
                    self.table.selectRow(row)
                    self.table.scrollToItem(item)
                    self._last_search_row = row
                    return
        show_info(self, f"Não encontrei “{term}” na tabela.")

    # --------------------------------------------------------- API para janela
    def apply_suggested_spec(self, spec: dict[str, Any]) -> None:
        try:
            self.manager.apply_model_spec(spec)
        except ValueError as exc:
            show_error(self, str(exc))
            return
        self.refresh()
        self.data_changed.emit("config")

    def current_model_spec(self) -> dict[str, Any]:
        return self.manager.model_spec()

    def refresh_theme(self) -> None:
        from .theme import table_row_height
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, table_row_height())
        self.table.resizeRowsToContents()
        self.refresh_style_buttons()

    def refresh_style_buttons(self) -> None:
        for widget in self.findChildren(QPushButton):
            from .theme import icon_size
            widget.setIconSize(QSize(icon_size(), icon_size()))
