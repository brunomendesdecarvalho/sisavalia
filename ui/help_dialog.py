"""Ajuda rápida não-modal."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QTextBrowser, QVBoxLayout, QWidget

from .nbr_tables import NBRTablesDialog
from .widgets import button


HELP_HTML = """
<h2>Importar → Explorar → Modelar → Avaliar → Exportar</h2>
<p>O caminho é sempre este. Você pode voltar a qualquer aba para conferir ou corrigir.</p>
<ol>
<li><b>Importar.</b> Na tela inicial, use <i>Abrir planilha</i> ou <i>Abrir exemplo</i>. Na aba 1,
confira a coluna <i>Ativo</i> e escolha as variáveis Y e X. Desmarque um imóvel para tirá-lo das contas
sem apagar os dados.</li>
<li><b>Explorar.</b> Na aba 2, veja a média, os vazios e os gráficos. Isso ajuda a perceber erros de digitação
e imóveis muito diferentes antes de montar a equação.</li>
<li><b>Modelar.</b> Na aba 3, escolha a equação e clique em <i>Calcular este modelo</i>. Se preferir,
clique em <i>Sugerir equações</i> e depois em <i>Usar este modelo</i>. A sugestão não substitui o seu julgamento.</li>
<li><b>Avaliar.</b> Na aba 4, inclua os imóveis avaliandos. Leia o intervalo de confiança, o grau de
fundamentação e o grau de precisão. Escolha o valor adotado e escreva a justificativa se ele for diferente
da estimativa.</li>
<li><b>Exportar.</b> Use <i>Exportar Relatório</i> para PDF ou DOCX. Use <i>Exportar Planilha</i> para
levar os dados, resíduos e avaliandos para o software de planilhas de sua preferência.</li>
</ol>
<h3>Dicas para facilitar</h3>
<ul>
<li>Passe o mouse sobre os termos: quase todos têm uma explicação curta.</li>
<li>Use Tab para andar entre os campos e Enter ou Espaço para acionar botões.</li>
<li>A aba 5 mostra se algum imóvel está puxando o resultado. Você pode desligá-lo com confirmação.</li>
<li>O programa guarda um backup automático a cada 5 minutos. Se o computador desligar sem salvar,
ao abrir você poderá recuperar o trabalho.</li>
<li>Em <b>Tabelas NBR 14653-2</b> você consulta as tabelas de fundamentação, enquadramento e precisão.</li>
<li>Não use os dados de exemplo em laudo: eles são fictícios.</li>
</ul>
<h3>Sobre os números</h3>
<p>Todos os números aparecem no padrão brasileiro, com vírgula decimal e ponto de milhar.
Você pode digitar vírgula ou ponto nos campos; os dois funcionam.</p>
"""


class HelpDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ajuda Rápida")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setModal(False)
        self.resize(780, 680)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        title = QLabel("Ajuda Rápida")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(HELP_HTML)
        browser.setAccessibleName("Passo a passo do SisAvalia")
        layout.addWidget(browser, 1)
        actions = QHBoxLayout()
        nbr_button = button(
            "Tabelas NBR 14653-2", "info",
            tooltip="Abre a consulta das Tabelas 1 a 7, 10 e 11.",
        )
        nbr_button.clicked.connect(lambda: NBRTablesDialog(self).exec())
        actions.addWidget(nbr_button)
        actions.addStretch(1)
        close_button = button("Fechar", "close")
        close_button.clicked.connect(self.close)
        actions.addWidget(close_button)
        layout.addLayout(actions)
