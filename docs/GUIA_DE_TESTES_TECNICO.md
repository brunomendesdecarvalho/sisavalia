# Guia de testes do SisAvalia

## Testes automáticos do núcleo (sem tela)

Na pasta do projeto, com o ambiente virtual ativo:

```bash
python3 tests/verificar_nucleo.py
pytest -q
```

O script `verificar_nucleo.py` confere, usando a amostra de exemplo:

- 20 apartamentos e configuração válida;
- R² ajustado da equação;
- IC 80% inferior e superior;
- grau de precisão;
- pontuação e grau de fundamentação;
- extrapolação aceitável e extrapolação acima do dobro;
- valor adotado dentro do IC;
- busca de equações e ordenação por R² ajustado;
- diagnóstico dos 20 imóveis.

A suíte `pytest` cobre também:

- formatação brasileira e leitura de vírgula/ponto;
- transformações inválidas;
- ANOVA e coeficientes;
- item 2, item 5 e item 6;
- teto de código alocado;
- extrapolação com mínimo zero/negativo;
- justificativa obrigatória;
- busca exaustiva, busca simplificada com teto de 400 ajustes e cancelamento;
- Cook, Mahalanobis e Shapiro;
- K-médias, PCA e simulações;
- ida e volta do projeto `.sisproj`;
- relatório DOCX e planilha XLSX.

## Casos de teste manuais

Use a amostra **Abrir exemplo**. Todos os testes abaixo podem ser feitos apenas com o mouse.

### CT-01 — Instalação e abertura sem terminal

1. Instale o `.deb` pelo Instalador de Pacotes do Mint.
2. Abra o SisAvalia pelo menu (categoria Educação ou busca).
3. **Esperado:** a janela abre, sem terminal, e mostra a tela inicial.

### CT-02 — Abrir o exemplo

1. Clique em **Abrir exemplo**.
2. **Esperado:** 20 imóveis ligados, aviso amarelo “Dados de exemplo. Não use em laudo.”, Y = Valor_unitario, X = Area_m2, Padrao, Idade_anos.
3. **Esperado:** a barra de status mostra “Na conta: 20 / Desligados: 0 / Modelo: calculado”.

### CT-03 — Desligar um imóvel

1. Na aba 1, desmarque a caixa **Ativo** da primeira linha.
2. **Esperado:** a linha continua na tabela; a contagem vai para 19 ativos e 1 desligado; o modelo é recalculado com n = 19.
3. Clique em **Reativar todos**.
4. **Esperado:** 20 ativos, modelo com n = 20.

### CT-04 — Editar célula e aceitar vírgula/ponto

1. Dê dois cliques na célula de área do primeiro imóvel.
2. Digite `55,5` e confirme; depois digite `56.5` e confirme.
3. **Esperado:** os dois valores são aceitos e exibidos no padrão brasileiro.

### CT-05 — Coluna calculada

1. Clique em **Nova coluna calculada**.
2. Nome: `Valor_unitario_teste`; A: `Valor_total`; operação `÷`; B: `Area_m2`.
3. **Esperado:** a coluna é criada e o primeiro valor é aproximadamente 9.140,00.

### CT-06 — Sugerir equações

1. Na aba 3, clique em **Sugerir equações**.
2. **Esperado:** a barra de progresso aparece, a busca termina e a tabela mostra até 30 equações com R², R² ajustado, p do F, pior p, sinais, n e grau estimado.
3. Selecione a primeira e clique em **Usar este modelo**.
4. **Esperado:** a equação vai para a aba 1, o modelo é recalculado e aparece a nova equação na aba 3.
5. **Esperado:** o texto “A sugestão não substitui o seu julgamento.” está visível.

### CT-07 — Cancelar a busca

1. Use uma amostra maior, se possível, e clique em **Sugerir equações**.
2. Clique em **Cancelar busca**.
3. **Esperado:** a busca para no próximo passo, sem travar a janela, e as sugestões antigas não são substituídas por uma busca incompleta.

### CT-08 — Dois avaliandos

1. Na aba 4, clique em **Incluir avaliando**.
2. Nome: `Apartamento A`; Area_m2: `80`; Padrao: `2`; Idade_anos: `5`.
3. Repita com `Apartamento B`; Area_m2: `120`; Padrao: `3`; Idade_anos: `2`.
4. **Esperado:** duas linhas na tabela, cada uma com estimativa, IC 80%, adotado, fundamentação e precisão.
5. Clique em cada linha e confira que os painéis e gráficos mudam para o avaliando selecionado.

### CT-09 — Intervalo e precisão

1. Selecione o primeiro avaliando.
2. Confira a estimativa, o IC 80% e a amplitude.
3. **Esperado:** a amplitude e o grau de precisão seguem: III até 30%, II até 40%, I até 50%, acima disso Fora de norma.
4. Confira que o intervalo de predição aparece com o rótulo “não entra no grau”.

### CT-10 — Valor adotado e justificativa

1. No campo **Valor adotado**, digite um valor dentro do IC.
2. Marque **Usar campo de arbítrio**.
3. Se o valor estiver fora de ±15%, **esperado:** campo vermelho e frase explicando.
4. Com valor diferente da estimativa e justificativa vazia, tente exportar o relatório.
5. **Esperado:** o programa bloqueia e pede a justificativa.
6. Preencha a justificativa e exporte.
7. **Esperado:** o relatório é gerado.

### CT-11 — Fora do IC

1. Digite um valor muito acima do IC.
2. **Esperado:** campo vermelho, frase dizendo que o valor precisa caber no intervalo e bloqueio da exportação.

### CT-12 — Arredondar 1%

1. Clique em **Arredondar 1%**.
2. **Esperado:** o valor adotado fica em um múltiplo de 1% da estimativa e continua validado contra o IC.

### CT-13 — Extrapolação e item 4

1. Inclua um avaliando com Area_m2 = 300 e os demais campos dentro da amostra.
2. **Esperado:** situação “acima”; aceitável; afastamento ≤ 15%; item 4 grau II.
3. Troque Area_m2 para 500.
4. **Esperado:** fora da faixa tolerada; item 4 sem grau.
5. Use Idade_anos = -1 (mínimo da amostra é 0).
6. **Esperado:** aviso de que a regra da metade não se aplica e item 4 sem grau.

### CT-14 — Teto de código alocado

1. Use uma amostra com código alocado 1, 2, 3 e pelo menos 24 imóveis.
2. Monte um modelo com p-valores baixos e itens 1 e 3 em III.
3. **Esperado:** se a soma chegar a Grau III, o grau final fica limitado a II, com frase explicando o teto.

### CT-15 — Resíduos e Cook

1. Vá à aba 5.
2. **Esperado:** semáforo das premissas, três faixas de normalidade, Shapiro-Wilk como linha extra, Breusch-Pagan, VIF, pares de correlação e Durbin-Watson informativo.
3. Confira a tabela: resíduo relativo ≥ 40% amarelo, ≥ 70% vermelho, |z| > 2 destacado.
4. Clique em **Desativar pontos influentes (Cook)**.
5. **Esperado:** confirmação diz quantos imóveis serão desmarcados na aba 1; depois de confirmar, eles ficam desligados e o modelo é recalculado.

### CT-16 — Mahalanobis

1. Clique em **Desativar pontos atípicos (Mahalanobis)**.
2. **Esperado:** confirmação com a contagem; se a amostra for pequena, a tela avisa que o corte foi aproximado pela qui-quadrado.

### CT-17 — K-médias

1. Na aba 6, marque duas ou mais variáveis.
2. Escolha K = 3 e clique em **Rodar K-médias**.
3. **Esperado:** gráfico 2D, cotovelo e tamanho dos grupos.
4. Clique em **Gravar coluna Cluster**.
5. **Esperado:** a coluna aparece na aba 1 e o projeto fica marcado como alterado.

### CT-18 — PCA

1. Clique em **Rodar PCA**.
2. **Esperado:** scree plot, cargas, biplot PC1 × PC2 e percentuais de variação explicada.

### CT-19 — Simulação

1. Na aba 7, escolha Normal, média 100, desvio 15, N = 1000.
2. Clique em **Gerar simulação**.
3. **Esperado:** histograma e estatísticas.
4. Exporte `.csv` e confira no Calc que o separador é `;` e o decimal é vírgula.
5. Clique em **Carregar como dados ativos**.
6. **Esperado:** o programa pergunta antes de substituir a amostra.

### CT-20 — Plugin

1. Na aba 8, selecione **Resumo estatístico**.
2. Clique em **Executar plugin**.
3. **Esperado:** abre uma janela com uma tabela por variável numérica, sem alterar a amostra.

### CT-21 — Salvar, fechar e reabrir

1. Salve o projeto em `.sisproj`.
2. Feche o programa; se houver alteração, ele pergunta se quer salvar.
3. Abra o `.sisproj` com duplo clique.
4. **Esperado:** metadados, avaliandos, valor adotado, justificativa, itens manuais e sugestões voltam.

### CT-22 — Recuperação de backup

1. Faça uma alteração e espere o próximo backup (ou aguarde 5 minutos).
2. Feche o programa de forma abrupta (por exemplo, encerrando o processo).
3. Abra de novo.
4. **Esperado:** a pergunta “Encontramos um trabalho não salvo da última vez. Deseja recuperá-lo?” aparece. Ao aceitar, o trabalho volta.

### CT-23 — Exportar PDF completo

1. Com dois avaliandos válidos, clique em **Exportar Relatório**.
2. Escolha PDF, sem modo resumo.
3. **Esperado:** relatório A4 com metadados, amostra, equação, ANOVA, coeficientes, projeções, fundamentação, precisão, extrapolação, premissas, tabela de resíduos e gráficos.
4. Ao terminar, clique em **Abrir arquivo agora**.
5. **Esperado:** o PDF abre no leitor do sistema.

### CT-24 — Resumo de 1 página

1. Exporte novamente em PDF com **Modo resumo (1 página)**.
2. **Esperado:** o PDF tem exatamente 1 página, com equação, estimativa, IC, valor adotado, graus e gráfico de aderência.

### CT-25 — DOCX

1. Exporte em DOCX, completo e resumo.
2. **Esperado:** os arquivos abrem no LibreOffice Writer e podem ser editados.

### CT-26 — Planilha XLSX

1. Clique em **Exportar Planilha**.
2. Abra no Calc.
3. **Esperado:** aba Dados com Ativo, rótulo, dados originais, Estimado, Resíduo, Resíduo relativo, Cook, Mahalanobis e, se existir, Cluster; aba Avaliandos com as projeções.

### CT-27 — Formatação brasileira

1. Percorra as abas 1 a 8 e os diálogos.
2. **Esperado:** números como 1.234,56; datas como dd/mm/aaaa; nenhum número decimal com ponto americano na tela, nos gráficos ou no relatório.

### CT-28 — Tema escuro, ícones e seletor de arquivos

1. Coloque o Linux no tema escuro e abra o SisAvalia.
2. **Esperado:** a interface continua clara; todos os ícones dos botões ficam escuros e visíveis.
3. Clique em **Abrir Planilha**.
4. **Esperado:** o seletor de arquivos abre claro, com a linha selecionada em azul e texto escuro legível; os ícones da barra do seletor também estão visíveis.
5. Troque para o tema claro e repita.
6. **Esperado:** o resultado é o mesmo.

### CT-29 — Gráficos ajustados

1. Abra a aba 3 e role até os gráficos.
2. Reduza e aumente a janela e o tamanho da fonte.
3. **Esperado:** os eixos, os rótulos e os títulos dos gráficos se ajustam ao espaço do cartão, sem ficar cortados; as imagens continuam legíveis.

### CT-30 — AppImage

1. Baixe o AppImage e marque **Permitir execução**.
2. Dê duplo clique.
3. **Esperado:** o programa abre sem pedir instalação de Python e sem terminal.
4. Rode `SisAvalia --verificar-instalacao` (ou abra o programa): **esperado** “Todos os componentes estão presentes.”.

### CT-31 — Verificação de dependências

1. Abra o programa empacotado.
2. **Esperado:** nenhuma mensagem de instalação incompleta.
3. Se um pacote for montado sem uma biblioteca, o programa mostra “Instalação incompleta” e orienta a reinstalar.

### CT-32 — Fonte e teclado

1. Troque o tamanho da fonte para Grande e Muito Grande.
2. **Esperado:** as telas, gráficos e textos aumentam; o seletor continua visível.
3. Use Tab para andar, Enter para confirmar e Espaço para marcar caixas.
4. **Esperado:** todos funcionam sem mouse.
5. Pressione F1.
6. **Esperado:** a Ajuda Rápida abre sem bloquear a janela principal.

## Critério de pronto (teste de aceitação)

Um usuário que só usa o mouse consegue:

- abrir o exemplo;
- desligar um imóvel;
- sugerir equação;
- usar a primeira da lista;
- lançar dois avaliandos;
- ler o grau de fundamentação e o de precisão;
- adotar um valor dentro do intervalo com justificativa;
- exportar PDF;
- abrir o arquivo gerado.

Nenhum número na tela fica em formato com ponto decimal americano.
