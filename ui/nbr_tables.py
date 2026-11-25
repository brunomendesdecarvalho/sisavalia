"""Consulta das tabelas-resumo da ABNT NBR 14653-2:2011."""
from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Optional, Sequence

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QTextBrowser,
    QScrollArea, QVBoxLayout, QWidget,
)

from .clipboard import copy_text
from .widgets import Banner, button, make_table, standard_icon


@dataclass(frozen=True)
class NBRTable:
    code: str
    title: str
    subtitle: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    notes: tuple[str, ...]
    source: str = "ABNT NBR 14653-2:2011"


NBR_TABLES: tuple[NBRTable, ...] = (
    NBRTable(
        code="Tabela 1",
        title="Fundamentação — modelos de regressão linear",
        subtitle="Critérios dos seis itens e pontuação III = 3, II = 2, I = 1.",
        headers=("Item", "Critério", "Grau III", "Grau II", "Grau I"),
        rows=(
            ("1", "Caracterização do imóvel avaliando",
             "Completa quanto a todas as variáveis", "Completa quanto às variáveis utilizadas",
             "Adoção de situação-paradigma"),
            ("2", "Quantidade mínima de dados efetivamente utilizados",
             "6 × (k + 1)", "4 × (k + 1)", "3 × (k + 1)"),
            ("3", "Identificação dos dados de mercado",
             "Todas as características observadas", "Informações dos dados analisadas",
             "Dados mínimos"),
            ("4", "Extrapolação",
             "Nenhuma", "Até 15% em uma variável", "Até 20% no conjunto, de per si e simultaneamente"),
            ("5", "Significância dos regressores (pior p-valor)",
             "≤ 10%", "≤ 20%", "≤ 30%"),
            ("6", "Significância do modelo (p-valor do F)",
             "≤ 1%", "≤ 2%", "≤ 5%"),
        ),
        notes=(
            "k é o número de variáveis independentes efetivamente usadas.",
            "Os limites de extrapolação valem para variáveis quantitativas; variáveis qualitativas não admitem extrapolação.",
        ),
    ),
    NBRTable(
        code="Tabela 2",
        title="Enquadramento — modelos de regressão linear",
        subtitle="Soma dos pontos da Tabela 1 e exigências obrigatórias.",
        headers=("Grau", "Pontos mínimos", "Itens obrigatórios"),
        rows=(
            ("III", "16", "Itens 2, 4, 5 e 6 no Grau III; os demais no mínimo no Grau II."),
            ("II", "10", "Itens 2, 4, 5 e 6 no mínimo no Grau II; os demais no mínimo no Grau I."),
            ("I", "6", "Todos os itens no mínimo no Grau I."),
        ),
        notes=("Se o Grau I não for atingido, o laudo deve indicar e justificar os itens não atendidos.",),
    ),
    NBRTable(
        code="Tabela 3",
        title="Fundamentação — tratamento por fatores",
        subtitle="Critérios da caracterização, quantidade, identificação e intervalo dos fatores.",
        headers=("Item", "Critério", "Grau III", "Grau II", "Grau I"),
        rows=(
            ("1", "Caracterização do imóvel avaliando",
             "Completa quanto a todos os fatores analisados", "Completa quanto aos fatores utilizados",
             "Adoção de situação-paradigma"),
            ("2", "Quantidade mínima de dados efetivamente utilizados",
             "12", "5", "3"),
            ("3", "Identificação dos dados de mercado",
             "Todas as características observadas", "Informações dos dados analisadas",
             "Dados mínimos"),
            ("4", "Intervalo admissível de ajuste para o conjunto de fatores",
             "0,50 a 2,00", "0,50 a 2,00", "0,50 a 2,00"),
        ),
        notes=(
            "Os fatores devem ser justificados e o produto dos fatores deve respeitar a faixa de 0,50 a 2,00.",
            "O tratamento por fatores não admite extrapolação.",
        ),
    ),
    NBRTable(
        code="Tabela 4",
        title="Enquadramento — tratamento por fatores",
        subtitle="Soma dos pontos da Tabela 3 e exigências obrigatórias.",
        headers=("Grau", "Pontos mínimos", "Itens obrigatórios"),
        rows=(
            ("III", "10", "Itens 2 e 4 no Grau III; os demais no mínimo no Grau II."),
            ("II", "6", "Itens 2 e 4 no mínimo no Grau II; os demais no mínimo no Grau I."),
            ("I", "4", "Todos os itens no mínimo no Grau I."),
        ),
        notes=("Os itens 1 e 3 são escolhidos pelo avaliador; os itens 2 e 4 são conferidos pelo programa.",),
    ),
    NBRTable(
        code="Tabela 5",
        title="Precisão — regressão e fatores",
        subtitle="Amplitude do intervalo de confiança de 80% em torno da estimativa de tendência central.",
        headers=("Grau", "Amplitude máxima do IC 80%"),
        rows=(("III", "≤ 30%"), ("II", "≤ 40%"), ("I", "≤ 50%")),
        notes=("Acima de 50%, o trabalho fica fora do enquadramento de precisão.",),
    ),
    NBRTable(
        code="Tabela 6",
        title="Fundamentação — quantificação do custo de benfeitorias",
        subtitle="Critérios de custo direto e BDI do método da quantificação de custo.",
        headers=("Item", "Critério", "Grau III", "Grau II", "Grau I"),
        rows=(
            ("1", "Estimativa do custo direto",
             "Orçamento, no mínimo sintético", "CUB para projeto semelhante ao padrão",
             "CUB para projeto diferente, com ajustes"),
            ("2", "BDI (benefícios e despesas indiretas)",
             "Calculado", "Justificado", "Atribuído"),
        ),
        notes=(
            "Tabela 6 de fundamentação; a Tabela 7 faz o enquadramento.",
            "Confira no laudo a composição do BDI e a fonte do custo.",
        ),
    ),
    NBRTable(
        code="Tabela 7",
        title="Enquadramento — quantificação do custo de benfeitorias",
        subtitle="Soma dos pontos da Tabela 6.",
        headers=("Grau", "Pontos mínimos", "Itens obrigatórios"),
        rows=(
            ("III", "6", "Itens 1 e 2 no Grau III."),
            ("II", "4", "Itens 1 e 2 no mínimo no Grau II."),
            ("I", "2", "Itens 1 e 2 no mínimo no Grau I."),
        ),
        notes=("A Tabela 7 deve ser lida junto com a Tabela 6 e com a Tabela 10 quando o método for evolutivo.",),
    ),
    NBRTable(
        code="Tabela 10",
        title="Fundamentação — método evolutivo",
        subtitle="Terreno, custo de reedição e fator de comercialização.",
        headers=("Item", "Critério", "Grau III", "Grau II", "Grau I"),
        rows=(
            ("1", "Estimativa do valor do terreno",
             "Grau III no comparativo ou no involutivo", "Grau II no comparativo ou no involutivo",
             "Grau I no comparativo ou no involutivo"),
            ("2", "Estimativa dos custos de reedição",
             "Grau III na quantificação de custo", "Grau II na quantificação de custo",
             "Grau I na quantificação de custo"),
            ("3", "Fator de comercialização",
             "Inferido em mercado semelhante", "Justificado", "Arbitrado"),
        ),
        notes=(
            "Pontuação: III = 3, II = 2, I = 1.",
            "A Tabela 11 faz o enquadramento do método evolutivo.",
        ),
    ),
    NBRTable(
        code="Tabela 11",
        title="Enquadramento — método evolutivo",
        subtitle="Soma dos pontos e itens obrigatórios da Tabela 10.",
        headers=("Grau", "Pontos mínimos", "Itens obrigatórios"),
        rows=(
            ("III", "8", "Itens 1 e 2 no Grau III; item 3 no mínimo no Grau II."),
            ("II", "5", "Itens 1 e 2 no mínimo no Grau II."),
            ("I", "3", "Todos os itens no mínimo no Grau I."),
        ),
        notes=("A precisão do método evolutivo segue a Tabela 5 quando aplicável ao intervalo de 80%.",),
    ),
)


class NBRTablesDialog(QDialog):
    """Janela de consulta, com tabela grande, rolável e copiável."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tabelas NBR 14653-2 — consulta")
        self.setWindowIcon(standard_icon("info"))
        self.resize(1120, 760)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        title = QLabel("Tabelas da ABNT NBR 14653-2:2011")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        subtitle = QLabel(
            "Resumo para consulta durante o trabalho. Prevalece o texto integral da norma. "
            "Use as setas do teclado para percorrer as tabelas."
        )
        subtitle.setObjectName("Hint")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)
        warning = Banner(
            "Estas tabelas são um resumo de apoio. A responsabilidade pela interpretação e pelo "
            "enquadramento é do avaliador.",
            "warning",
        )
        outer.addWidget(warning)
        body = QHBoxLayout()
        body.setSpacing(10)
        self.list = QListWidget()
        self.list.setMinimumWidth(265)
        self.list.setMaximumWidth(330)
        self.list.setAccessibleName("Lista de tabelas da NBR")
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for table in NBR_TABLES:
            item = QListWidgetItem(f"{table.code}\n{table.title}")
            item.setData(Qt.ItemDataRole.UserRole, table.code)
            item.setToolTip(table.title)
            item.setSizeHint(QSize(0, 58))
            self.list.addItem(item)
        self.list.currentRowChanged.connect(self._show_table)
        body.addWidget(self.list)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAccessibleName("Conteúdo da tabela da NBR")
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(8, 6, 8, 6)
        self.content_layout.setSpacing(8)
        self.scroll.setWidget(self.content)
        body.addWidget(self.scroll, 1)
        outer.addLayout(body, 1)
        actions = QHBoxLayout()
        self.copy_button = button("Copiar tabela", "copy")
        self.copy_button.clicked.connect(self.copy_current)
        self.close_button = button("Fechar", "close")
        self.close_button.clicked.connect(self.reject)
        actions.addWidget(self.copy_button)
        actions.addStretch(1)
        actions.addWidget(self.close_button)
        outer.addLayout(actions)
        self.table_widget: Optional[QTextBrowser] = None
        self.current = NBR_TABLES[0]
        self.list.setCurrentRow(0)

    def _clear_content(self) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _show_table(self, index: int) -> None:
        if not (0 <= index < len(NBR_TABLES)):
            return
        table = NBR_TABLES[index]
        self.current = table
        self._clear_content()
        heading = QLabel(table.title)
        heading.setObjectName("SectionTitle")
        heading.setWordWrap(True)
        self.content_layout.addWidget(heading)
        sub = QLabel(table.subtitle)
        sub.setObjectName("Hint")
        sub.setWordWrap(True)
        self.content_layout.addWidget(sub)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        rows_html = "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row) + "</tr>"
            for row in table.rows
        )
        heads = "".join(f"<th>{html.escape(str(h))}</th>" for h in table.headers)
        browser.setHtml(
            "<style>"
            "body { font-family: 'DejaVu Sans', sans-serif; font-size: 10.5pt; color: #0f172a; }"
            "table { border-collapse: collapse; width: 100%; }"
            "th { background: #e2e8f0; color: #1e3a8a; text-align: left; padding: 5px; border: 1px solid #cbd5e1; }"
            "td { padding: 5px; border: 1px solid #cbd5e1; vertical-align: top; }"
            "tr:nth-child(even) td { background: #f8fafc; }"
            "</style>"
            f"<table><thead><tr>{heads}</tr></thead><tbody>{rows_html}</tbody></table>"
        )
        browser.setMinimumHeight(min(560, 70 + 52 * len(table.rows)))
        browser.setAccessibleName(f"{table.code} — {table.title}")
        self.table_widget = browser
        self.content_layout.addWidget(browser)
        self.content_layout.addStretch(1)

    def copy_current(self) -> None:
        if self.table_widget is None:
            return
        lines = ["\t".join(self.current.headers)]
        lines.extend("\t".join(row) for row in self.current.rows)
        copy_text("\n".join(lines))
        self.copy_button.setText("Tabela copiada!")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1800, lambda: self.copy_button.setText("Copiar tabela"))
