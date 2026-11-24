"""Textos de ajuda em linguagem leiga, usados em tooltips e na ajuda."""
from __future__ import annotations

TOOLTIPS: dict[str, str] = {
    "vif": "Mede se uma variável está repetindo a informação de outra. Acima de 10 indica problema.",
    "p_valor": "Indica se a variável realmente influencia o resultado. Quanto menor, mais confiável; abaixo de 0,05 é o usual.",
    "r2_ajustado": "Mostra quanto o modelo explica da variação, com desconto pelo número de variáveis. Quanto mais perto de 1, melhor.",
    "r2": "Mostra quanto da variação do valor é explicada pela equação. Quanto mais perto de 1, melhor.",
    "campo_arbitrio": "É a margem de ±15% em torno da estimativa. Dentro dela você pode adotar um valor diferente, desde que escreva a justificativa.",
    "extrapolacao": "Acontece quando o imóvel avaliando tem uma variável fora do menor ou do maior valor da amostra. Quanto mais longe, maior o risco.",
    "cook": "Mostra se um imóvel puxa o resultado sozinho. Quanto maior, mais influente. Valores acima de 4 dividido pelo número de imóveis merecem atenção.",
    "mahalanobis": "Mostra se um imóvel está distante do conjunto nas variáveis explicativas. Quanto maior, mais atípico.",
    "ic80": "Faixa em que a média estimada deve estar com 80% de confiança. A largura dessa faixa define o grau de precisão.",
    "predicao": "Faixa provável para um imóvel individual, mais larga que a do IC. Ela não entra no grau de precisão.",
    "fundamentacao": "Grau que soma os seis itens da NBR 14653-2: caracterização, amostra, dados de mercado, extrapolação, significância das variáveis e do modelo.",
    "precisao": "Grau separado da fundamentação. Depende só da largura do intervalo de confiança de 80% em relação à estimativa.",
    "residuo": "Diferença entre o valor observado e o estimado. Quanto maior, mais o imóvel se afasta da equação.",
    "residuo_relativo": "O resíduo dividido pelo valor observado. Acima de 40% merece atenção; acima de 70% é bastante alto.",
    "padronizado": "Resíduo medido em desvios padrão. Valores acima de 2 (ou abaixo de −2) ficam em destaque.",
    "studentizado": "Resíduo ajustado pela influência de cada imóvel. Ajuda a comparar pontos de tamanhos diferentes.",
    "codigo_alocado": "Número usado para representar uma categoria, como padrão 1, 2 e 3. Ele não mede distância real entre as categorias.",
    "dicotomica": "Variável com dois resultados, como 0 e 1, ou sim e não.",
    "proxy": "Variável que substitui outra que não foi medida diretamente, como o padrão do prédio no lugar da vista.",
    "transformacao": "Muda a forma da variável para o cálculo. Em ln(x) e 1/x, todos os valores precisam ser maiores que zero.",
    "extrapolacao_regra": "Fora da amostra, o valor ainda é aceitável para os graus I e II se ficar entre a metade do mínimo e o dobro do máximo. Se o mínimo for zero ou negativo, a regra da metade não é aplicada.",
    "grau_estimado": "Prévia do grau de fundamentação que a equação provavelmente alcança. A confirmação depende do imóvel avaliando e da extrapolação.",
    "p_f": "Indica se a equação como um todo é confiável. Quanto menor, melhor; abaixo de 0,05 é o usual.",
    "anova": "Tabela que compara a variação explicada pela equação com a variação que sobra nos resíduos.",
    "micronumerosidade": "Micronumerosidade: poucos imóveis em uma categoria ou código. O ideal é pelo menos 3 em cada lado.",
    "elasticidade": "Mostra a mudança percentual no valor quando uma variável sobe 1%, mantendo as outras paradas.",
    "sinal_esperado": "O que você espera que aconteça com o valor quando a variável aumenta. O programa avisa se a equação fizer o contrário, mas não força o coeficiente.",
    "listwise": "Quando falta um dado em qualquer variável, o imóvel inteiro sai somente daquele cálculo. Ele continua na tabela.",
    "adotado": "Valor final escolhido por você. Ele precisa caber no intervalo de confiança e, se for diferente da estimativa, precisa de justificativa.",
    "resumo": "Relatório curto de cerca de uma página, com equação, estimativa, intervalo, valor adotado, graus e gráfico de aderência.",
    "nbr": "Norma brasileira de avaliação de imóveis. O programa faz uma conta simplificada de enquadramento, mas a decisão final é do avaliador.",
}


def tip(key: str) -> str:
    return TOOLTIPS.get(key, "")
