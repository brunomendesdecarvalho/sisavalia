"""Diálogos de metadados, colunas e imóveis avaliandos."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QRadioButton, QScrollArea, QVBoxLayout, QWidget,
)

from core.data_manager import COLUMN_TYPES, TIPOLOGIAS, DataManager
from core.formatting import format_number, parse_number
from .widgets import Banner, Card, button, standard_icon


class DialogBase(QDialog):
    def __init__(self, title: str, subtitle: str = "", parent: Optional[QWidget] = None,
                 width: int = 660) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(standard_icon("info"))
        self.setModal(True)
        self.resize(width, 520)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(16, 14, 16, 14)
        self.root.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("PageTitle")
        heading.setWordWrap(True)
        self.root.addWidget(heading)
        self.banner = Banner("", "error")
        self.banner.setVisible(False)
        if subtitle:
            hint = QLabel(subtitle)
            hint.setObjectName("Hint")
            hint.setWordWrap(True)
            self.root.addWidget(hint)
        self.card = Card()
        self.root.addWidget(self.card, 1)
        self.root.addWidget(self.banner)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.cancel_button = button("Cancelar", "cancel")
        self.confirm_button = button("Confirmar", "ok", primary=True)
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self._confirm)
        self.confirm_button.setDefault(True)
        self.confirm_button.setAutoDefault(True)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.confirm_button)
        self.root.addLayout(actions)

    def show_problem(self, message: str) -> None:
        self.banner.setText(message)
        self.banner.set_role("error")
        self.banner.setVisible(True)

    def _confirm(self) -> None:
        self.accept()


class MetadataDialog(DialogBase):
    def __init__(self, metadata: dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(
            "Dados do trabalho",
            "Estas informações aparecem no laudo e podem ser mudadas depois.",
            parent,
            width=780,
        )
        self.resize(780, 720)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)
        self.author = QLineEdit(str(metadata.get("author", "")))
        self.author.setPlaceholderText("Seu nome ou da empresa")
        self.work = QLineEdit(str(metadata.get("work_name", "")))
        self.work.setPlaceholderText("Ex.: Avaliação de apartamento — Rua das Flores")
        self.date = QDateEdit()
        self.date.setDisplayFormat("dd/MM/yyyy")
        self.date.setCalendarPopup(True)
        self.date.setLocale(self.locale())
        parsed = QDate.fromString(str(metadata.get("date", "")), "dd/MM/yyyy")
        self.date.setDate(parsed if parsed.isValid() else QDate.currentDate())
        self.reference_date = QDateEdit()
        self.reference_date.setDisplayFormat("dd/MM/yyyy")
        self.reference_date.setCalendarPopup(True)
        self.reference_date.setLocale(self.locale())
        parsed_ref = QDate.fromString(str(metadata.get("reference_date", "")), "dd/MM/yyyy")
        self.reference_date.setDate(parsed_ref if parsed_ref.isValid() else QDate.currentDate())
        self.city = QLineEdit(str(metadata.get("city", "")))
        self.city.setPlaceholderText("Município do imóvel avaliando")
        self.tipologia = QComboBox()
        self.tipologia.addItems(list(TIPOLOGIAS))
        current_type = str(metadata.get("tipologia", "Apartamento"))
        if current_type in TIPOLOGIAS:
            self.tipologia.setCurrentText(current_type)
        self.requester = QLineEdit(str(metadata.get("requester", "")))
        self.requester.setPlaceholderText("Quem pediu a avaliação")
        self.purpose = QLineEdit(str(metadata.get("purpose", "")))
        self.purpose.setPlaceholderText("Ex.: compra e venda, garantia, locação, desapropriação")
        self.objective = QLineEdit(str(metadata.get("objective", "")))
        self.objective.setPlaceholderText("Ex.: determinar o valor de mercado do imóvel")
        self.description = QPlainTextEdit(str(metadata.get("description", "")))
        self.description.setPlaceholderText("Identificação e caracterização resumida do avaliando e diagnóstico de mercado.")
        self.description.setMinimumHeight(90)
        self.assumptions = QPlainTextEdit(str(metadata.get("assumptions", "")))
        self.assumptions.setPlaceholderText(
            "Pressupostos, ressalvas e condições limitantes. Ex.: não houve vistoria interna; "
            "o imóvel foi considerado em situação-paradigma."
        )
        self.assumptions.setMinimumHeight(90)
        self.no_inspection = QCheckBox("Sem vistoria interna — adotar situação-paradigma")
        self.no_inspection.setToolTip(
            "Preenche uma ressalva padrão. Revise o texto antes de exportar o laudo."
        )
        self.no_inspection.toggled.connect(self._inspection_toggled)
        self.technical_name = QLineEdit(str(metadata.get("technical_name", "")))
        self.technical_name.setPlaceholderText("Nome do responsável técnico")
        self.technical_registry = QLineEdit(str(metadata.get("technical_registry", "")))
        self.technical_registry.setPlaceholderText("CREA/CAU do responsável")
        self.signature_city = QLineEdit(str(metadata.get("signature_city", "")))
        self.signature_city.setPlaceholderText("Cidade da assinatura")
        self.sample_note = QLineEdit(str(metadata.get("sample_note", "")))
        self.sample_note.setPlaceholderText("Opcional. Ex.: Dados de exemplo. Não use em laudo.")
        for label, widget in (
            ("Autor:", self.author),
            ("Responsável técnico:", self.technical_name),
            ("CREA/CAU:", self.technical_registry),
            ("Solicitante:", self.requester),
            ("Nome do trabalho:", self.work),
            ("Data do trabalho:", self.date),
            ("Data de referência:", self.reference_date),
            ("Município:", self.city),
            ("Tipologia:", self.tipologia),
            ("Finalidade:", self.purpose),
            ("Objetivo:", self.objective),
            ("Identificação / diagnóstico de mercado:", self.description),
            ("Pressupostos e ressalvas:", self.assumptions),
            ("", self.no_inspection),
            ("Cidade da assinatura:", self.signature_city),
            ("Observação da amostra:", self.sample_note),
        ):
            form.addRow(label, widget)
        holder = QWidget()
        holder.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(500)
        scroll.setWidget(holder)
        self.card.add(scroll)
        self.confirm_button.setText("Salvar dados")

    def _inspection_toggled(self, checked: bool) -> None:
        if checked and not self.assumptions.toPlainText().strip():
            self.assumptions.setPlainText(
                "Não houve vistoria interna. O imóvel foi avaliado em situação-paradigma, "
                "com base nas características informadas e nos dados de mercado disponíveis."
            )

    def metadata(self) -> dict[str, Any]:
        return {
            "author": self.author.text().strip(),
            "work_name": self.work.text().strip() or "Trabalho sem nome",
            "date": self.date.date().toString("dd/MM/yyyy"),
            "reference_date": self.reference_date.date().toString("dd/MM/yyyy"),
            "city": self.city.text().strip(),
            "tipologia": self.tipologia.currentText(),
            "requester": self.requester.text().strip(),
            "purpose": self.purpose.text().strip(),
            "objective": self.objective.text().strip(),
            "description": self.description.toPlainText().strip(),
            "assumptions": self.assumptions.toPlainText().strip(),
            "limitations": "",
            "technical_name": self.technical_name.text().strip(),
            "technical_registry": self.technical_registry.text().strip(),
            "signature_city": self.signature_city.text().strip(),
            "inspection": "Sem vistoria interna" if self.no_inspection.isChecked() else "",
            "sample_note": self.sample_note.text().strip(),
        }


class AddColumnDialog(DialogBase):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            "Incluir coluna",
            "A coluna começa vazia. Depois você pode preencher as células ou usar Nova coluna calculada.",
            parent,
        )
        form = QFormLayout()
        form.setSpacing(10)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ex.: Vagas")
        self.type_combo = QComboBox()
        self.type_combo.addItems(list(COLUMN_TYPES))
        form.addRow("Nome da nova coluna:", self.name_edit)
        form.addRow("Tipo:", self.type_combo)
        holder = QWidget()
        holder.setLayout(form)
        self.card.add(holder)
        self.confirm_button.setText("Incluir coluna")

    def values(self) -> tuple[str, str]:
        return self.name_edit.text().strip(), self.type_combo.currentText()


class RenameColumnDialog(DialogBase):
    def __init__(self, columns: list[str], parent: Optional[QWidget] = None) -> None:
        super().__init__("Renomear coluna", "O novo nome aparece na tabela e nos cálculos.", parent)
        form = QFormLayout()
        form.setSpacing(10)
        self.column_combo = QComboBox()
        self.column_combo.addItems(columns)
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText("Novo nome")
        self.column_combo.currentTextChanged.connect(self.new_name.setText)
        if columns:
            self.new_name.setText(columns[0])
        form.addRow("Coluna:", self.column_combo)
        form.addRow("Novo nome:", self.new_name)
        holder = QWidget()
        holder.setLayout(form)
        self.card.add(holder)
        self.confirm_button.setText("Renomear")

    def values(self) -> tuple[str, str]:
        return self.column_combo.currentText(), self.new_name.text().strip()


class DeleteColumnDialog(DialogBase):
    def __init__(self, columns: list[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(
            "Excluir coluna",
            "A coluna e todos os valores dela serão apagados. Não é possível desfazer depois de fechar o projeto.",
            parent,
        )
        form = QFormLayout()
        form.setSpacing(10)
        self.column_combo = QComboBox()
        self.column_combo.addItems(columns)
        form.addRow("Coluna que será excluída:", self.column_combo)
        holder = QWidget()
        holder.setLayout(form)
        self.card.add(holder)
        self.confirm_button.setText("Excluir coluna")
        self.confirm_button.setProperty("danger", True)

    def column(self) -> str:
        return self.column_combo.currentText()


class CalculatedColumnDialog(DialogBase):
    def __init__(self, manager: DataManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            "Nova coluna calculada",
            "Exemplo muito usado: Valor unitário = Valor total ÷ Área. O resultado entra como nova coluna.",
            parent,
        )
        self.manager = manager
        form = QFormLayout()
        form.setSpacing(10)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ex.: Valor_unitario")
        self.column_a = QComboBox()
        self.column_a.addItems(manager.numeric_columns())
        self.operator = QComboBox()
        self.operator.addItems(["+", "−", "×", "÷"])
        self.column_b = QComboBox()
        self.column_b.addItems(manager.numeric_columns())
        self.constant_radio = QRadioButton("Usar uma constante no lugar da coluna B")
        self.constant_edit = QLineEdit()
        self.constant_edit.setPlaceholderText("Ex.: 1000")
        self.constant_edit.setEnabled(False)
        self.constant_radio.toggled.connect(self._toggle_constant)
        form.addRow("Nome da nova coluna:", self.name_edit)
        form.addRow("Coluna A:", self.column_a)
        form.addRow("Operação:", self.operator)
        form.addRow("Coluna B:", self.column_b)
        form.addRow("", self.constant_radio)
        form.addRow("Constante:", self.constant_edit)
        holder = QWidget()
        holder.setLayout(form)
        self.card.add(holder)
        self.confirm_button.setText("Criar coluna")
        self.created_column: Optional[str] = None

    def _toggle_constant(self, checked: bool) -> None:
        self.constant_edit.setEnabled(checked)
        self.column_b.setEnabled(not checked)

    def _confirm(self) -> None:
        try:
            if self.constant_radio.isChecked():
                constant = parse_number(self.constant_edit.text())
                column = self.manager.add_calculated_column(
                    self.name_edit.text(), self.column_a.currentText(),
                    self.operator.currentText(), constant=constant,
                )
            else:
                column = self.manager.add_calculated_column(
                    self.name_edit.text(), self.column_a.currentText(),
                    self.operator.currentText(), column_b=self.column_b.currentText(),
                )
        except ValueError as exc:
            self.show_problem(str(exc))
            return
        self.created_column = column
        self.accept()


class EvaluatedDialog(DialogBase):
    def __init__(self, manager: DataManager, item: Optional[dict[str, Any]] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(
            "Editar imóvel avaliando" if item else "Incluir imóvel avaliando",
            "Preencha os mesmos tipos de informação usados na amostra. Use vírgula ou ponto nos números.",
            parent,
        )
        self.manager = manager
        self.item = item
        specs = manager.x_specs(True)
        if not specs:
            raise ValueError("Escolha pelo menos uma variável X na aba 1 antes de incluir o avaliando.")
        form = QFormLayout()
        form.setSpacing(10)
        self.name_edit = QLineEdit(str((item or {}).get("name", "")))
        self.name_edit.setPlaceholderText("Ex.: Imóvel da Rua das Flores, 123")
        form.addRow("Nome do avaliando:", self.name_edit)
        self.fields: dict[str, QLineEdit] = {}
        existing = (item or {}).get("values", {})
        for spec in specs:
            name = spec["name"]
            edit = QLineEdit()
            if existing.get(name) is not None:
                try:
                    edit.setText(format_number(existing[name], 4))
                except Exception:
                    edit.setText(str(existing[name]))
            edit.setPlaceholderText(f"Valor de {name}")
            edit.setAccessibleName(f"{name} do avaliando")
            suffix = QLabel(f"Transformação no modelo: {spec['transformation']}")
            suffix.setObjectName("Hint")
            form.addRow(f"{name}:", edit)
            form.addRow("", suffix)
            self.fields[name] = edit
        holder = QWidget()
        holder.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        scroll.setMinimumHeight(280)
        self.card.add(scroll)
        self.confirm_button.setText("Salvar avaliando")

    def _confirm(self) -> None:
        name = self.name_edit.text().strip()
        values: dict[str, float] = {}
        for column, edit in self.fields.items():
            if not edit.text().strip():
                self.show_problem(f"Preencha o campo “{column}”.")
                edit.setFocus()
                return
            try:
                values[column] = parse_number(edit.text())
            except ValueError as exc:
                self.show_problem(f"O campo “{column}” precisa de um número. Exemplo: 1.234,56.")
                edit.setFocus()
                return
        if not name:
            self.show_problem("Dê um nome ao avaliando para identificá-lo nas listas.")
            self.name_edit.setFocus()
            return
        self.result = {"name": name, "values": values}
        self.accept()
