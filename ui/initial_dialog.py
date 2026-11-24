"""Tela inicial exibida quando ainda não há arquivo aberto."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from .widgets import Card, button, standard_icon


class ChoiceCard(QFrame):
    def __init__(self, title: str, description: str, icon: str, primary: bool = False,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SubCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(7)
        self.button = button(title, icon, primary=primary)
        self.button.setSizePolicy(self.button.sizePolicy().horizontalPolicy(),
                                  self.button.sizePolicy().verticalPolicy())
        self.button.setMinimumHeight(64)
        self.description = QLabel(description)
        self.description.setObjectName("Hint")
        self.description.setWordWrap(True)
        layout.addWidget(self.button)
        layout.addWidget(self.description)


class InitialPage(QWidget):
    new_requested = Signal()
    open_spreadsheet_requested = Signal()
    open_project_requested = Signal()
    open_example_requested = Signal()
    open_recent_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(16)
        header = QLabel("SisAvalia")
        header.setObjectName("Title")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel(
            "Análise estatística, regressão e avaliação de imóveis em linguagem simples."
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(header)
        layout.addWidget(subtitle)
        intro = QLabel("Comece por uma das opções abaixo. Você pode Trocar de arquivo quando quiser.")
        intro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        grid = QGridLayout()
        grid.setSpacing(12)
        self.new_card = ChoiceCard("Novo", "Começa um trabalho vazio, com os seus dados.", "new", primary=True)
        self.open_sheet_card = ChoiceCard("Abrir planilha", "Abre um arquivo .xlsx, .xls ou .csv.", "spreadsheet")
        self.open_project_card = ChoiceCard("Abrir projeto", "Continua um trabalho salvo em .sisproj.", "open")
        self.example_card = ChoiceCard("Abrir exemplo", "Amostra fictícia para aprender, com 20 apartamentos.", "chart")
        self.new_card.button.clicked.connect(self.new_requested)
        self.open_sheet_card.button.clicked.connect(self.open_spreadsheet_requested)
        self.open_project_card.button.clicked.connect(self.open_project_requested)
        self.example_card.button.clicked.connect(self.open_example_requested)
        grid.addWidget(self.new_card, 0, 0)
        grid.addWidget(self.open_sheet_card, 0, 1)
        grid.addWidget(self.open_project_card, 1, 0)
        grid.addWidget(self.example_card, 1, 1)
        layout.addLayout(grid)
        example_note = QLabel("Dados de exemplo. Não use em laudo.")
        example_note.setProperty("role", "warning")
        example_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        example_note.setWordWrap(True)
        layout.addWidget(example_note)
        self.recent_card = Card(title="Projetos recentes",
                                subtitle="Os últimos cinco projetos abertos ou salvos aparecem aqui.")
        self.recent_layout = QVBoxLayout()
        self.recent_layout.setSpacing(6)
        self.recent_card.add_layout(self.recent_layout)
        layout.addWidget(self.recent_card)
        footer = QLabel(
            "Os seus arquivos ficam no computador. O SisAvalia guarda um backup automático a cada 5 minutos."
        )
        footer.setObjectName("Hint")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setWordWrap(True)
        layout.addWidget(footer)
        layout.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self.set_recent([])

    def set_recent(self, paths: Iterable[str]) -> None:
        while self.recent_layout.count():
            item = self.recent_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        paths = list(paths)[:5]
        if not paths:
            hint = QLabel("Nenhum projeto recente ainda.")
            hint.setObjectName("Hint")
            self.recent_layout.addWidget(hint)
            return
        for path in paths:
            file_path = Path(path)
            exists = file_path.exists()
            btn = QPushButton(file_path.stem, self)
            btn.setIcon(standard_icon("open"))
            btn.setToolTip(str(file_path))
            btn.setAccessibleName(f"Abrir projeto recente {file_path.stem}")
            btn.setEnabled(exists)
            if not exists:
                btn.setText(f"{file_path.stem} (arquivo não encontrado)")
            btn.clicked.connect(lambda _checked=False, p=path: self.open_recent_requested.emit(p))
            self.recent_layout.addWidget(btn)
