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
<li><b>Importar e explorar.</b> Na tela inicial, use <i>Abrir planilha</i> ou <i>Abrir exemplo</i>. Na aba 1,
confira a coluna <i>Ativo</i>, escolha as variáveis Y e X e veja as estatísticas e os gráficos exploratórios
logo acima da tabela. Desmarque um imóvel para tirá-lo das contas sem apagar os dados.</li>
<li><b>Modelar.</b> Na aba 2, escolha a equação e clique em <i>Calcular este modelo</i>. Se preferir,
clique em <i>Sugerir equações</i> e depois em <i>Usar este modelo</i>. A sugestão não substitui o seu julgamento.</li>
<li><b>Avaliar.</b> Na aba 3, inclua os imóveis avaliandos. Leia o intervalo de confiança, o grau de
fundamentação e o grau de precisão. Escolha o valor adotado e escreva a justificativa se ele for diferente
da estimativa.</li>
<li><b>Exportar.</b> Use <i>Exportar Relatório</i> para PDF ou DOCX. Use <i>Exportar Planilha</i> para
levar os dados, resíduos e avaliandos para o software de planilhas de sua preferência.</li>
</ol>
<h3>Dicas para facilitar</h3>
<ul>
<li>Passe o mouse sobre os termos: quase todos têm uma explicação curta.</li>
<li>Use Tab para andar entre os campos e Enter ou Espaço para acionar botões.</li>
<li>A aba 4 mostra se algum imóvel está puxando o resultado. Você pode desligá-lo com confirmação.</li>
<li>O programa guarda um backup automático a cada 5 minutos. Se o computador desligar sem salvar,
ao abrir você poderá recuperar o trabalho.</li>
<li>Em <b>Tabelas NBR 14653-2</b> você consulta as tabelas de fundamentação, enquadramento e precisão.</li>
<li>Não use os dados de exemplo em laudo: eles são fictícios.</li>
</ul>

<h3>Glossário de medições</h3>
<table border="1" cellspacing="0" cellpadding="5" width="100%">
<tr><th width="26%">Termo</th><th>O que significa</th><th width="30%">Exemplo prático</th></tr>
<tr><td><b>R² (Coeficiente de Determinação)</b></td><td>Quanto da variação de Y é explicado pelo modelo. Vai de 0 a 1; quanto maior, melhor o ajuste.</td><td>R² = 0,85: 85% da variação dos valores é explicada pelas variáveis escolhidas.</td></tr>
<tr><td><b>R² ajustado</b></td><td>Parecido com o R², mas penaliza variáveis que não ajudam. Serve para comparar modelos com números diferentes de X.</td><td>Se o R² sobe mas o ajustado cai, a variável nova pode estar só complicando.</td></tr>
<tr><td><b>Erro padrão dos resíduos</b></td><td>Tamanho médio do erro da equação, na escala de Y.</td><td>Erro de R$ 3.000 significa que os desvios típicos ficam nessa ordem.</td></tr>
<tr><td><b>F e p-valor do modelo</b></td><td>Testam se o conjunto de variáveis explica Y. p-valor baixo indica modelo estatisticamente significativo.</td><td>p &lt; 0,05 costuma ser aceito como evidência de que o modelo não é só sorte.</td></tr>
<tr><td><b>t e p-valor do coeficiente</b></td><td>Testam se cada variável, isoladamente, tem efeito diferente de zero.</td><td>p = 0,03 para Área indica efeito estatisticamente significativo.</td></tr>
<tr><td><b>IC 80% da média</b></td><td>Faixa provável para o valor médio estimado. É o intervalo usado na precisão da NBR 14653.</td><td>IC de R$ 500.000 a R$ 540.000 para a média.</td></tr>
<tr><td><b>IP 80% (predição)</b></td><td>Faixa provável para um imóvel individual, mais larga que o IC da média.</td><td>Um imóvel novo pode ficar entre R$ 480.000 e R$ 560.000.</td></tr>
<tr><td><b>Campo de arbítrio</b></td><td>Margem de ±15% em torno da estimativa em que o avaliador pode adotar outro valor, com justificativa.</td><td>Estimativa R$ 500.000: arbítrio de R$ 425.000 a R$ 575.000.</td></tr>
<tr><td><b>Grau de fundamentação</b></td><td>Pontuação da qualidade da fundamentação do laudo (itens da NBR 14653-2).</td><td>Grau III é o mais completo; Grau I, o mínimo.</td></tr>
<tr><td><b>Grau de precisão</b></td><td>Depende da amplitude do IC 80% em relação à estimativa.</td><td>Amplitude até 30% = Grau III; até 40% = II; até 50% = I.</td></tr>
<tr><td><b>VIF</b></td><td>Mede quanto uma variável é explicada pelas outras. VIF alto indica redundância.</td><td>VIF acima de 10 pede revisão das variáveis repetidas.</td></tr>
<tr><td><b>Durbin-Watson</b></td><td>Verifica independência dos resíduos ao longo dos valores ajustados.</td><td>Perto de 2 indica resíduos sem padrão sequencial.</td></tr>
<tr><td><b>Shapiro-Wilk</b></td><td>Testa se os resíduos se aproximam de uma distribuição normal.</td><td>p &gt; 0,05 sugere que a normalidade é razoável.</td></tr>
<tr><td><b>Distância de Cook</b></td><td>Mostra imóveis com influência grande sobre a equação.</td><td>Um ponto muito acima do corte pode estar puxando o resultado.</td></tr>
<tr><td><b>Mahalanobis</b></td><td>Mede se a combinação de características do imóvel é atípica em relação à amostra.</td><td>Valor acima do corte pede conferência dos dados e da coerência.</td></tr>
<tr><td><b>Elasticidade</b></td><td>Variação percentual de Y para 1% de variação em X, com os demais fatores parados.</td><td>Elasticidade 0,8: 1% mais área tende a aumentar o valor em 0,8%.</td></tr>
<tr><td><b>Extrapolação</b></td><td>Uso de valor fora da faixa observada na amostra. A NBR restringe, sobretudo em variável qualitativa.</td><td>Padrão 4 quando a amostra só tem 1 a 3 é extrapolação vedada.</td></tr>
<tr><td><b>Resíduo padronizado</b></td><td>Erro dividido pelo desvio padrão; facilita comparar imóveis de escalas diferentes.</td><td>Fora de ±2, o ponto merece justificativa no laudo.</td></tr>
</table>
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
