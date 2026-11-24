# Guia de Testes de Aceitação — SisAvalia

**Público:** avaliador, engenheiro ou técnico que conhece avaliação de imóveis, mas não precisa saber programar.  
**Objetivo:** verificar se o SisAvalia entrega o fluxo de trabalho de uma avaliação — importar, explorar, modelar, avaliar e exportar — com resultados coerentes e em linguagem compreensível.  
**Versão:** 1.0.2
**Data de referência:** novembro de 2026

> **Dados de exemplo. Não use em laudo.** A amostra que acompanha o programa é fictícia e serve apenas para este roteiro.

---

## 1. Como usar este guia

Este guia foi escrito para ser seguido **pelo mouse**, sem terminal, sem instalação de Python e sem conhecimento de programação.

Cada cenário tem:

- **Objetivo de negócio:** por que aquela verificação importa na avaliação.
- **Como testar:** o caminho na interface.
- **Resultado esperado:** o que deve aparecer.
- **Critério de aceite:** a condição objetiva para considerar aprovado.
- **Criticidade:** Alta, Média ou Baixa.

Marque cada cenário como **Aprovado**, **Reprovado** ou **Não aplicável**. Se reprovar, registre uma evidência (captura de tela, arquivo `.sisproj` e descrição do ocorrido).

### Materiais necessários

- Computador com Linux Mint, Fedora ou outra distribuição compatível.
- SisAvalia instalado pelo `.deb` ou aberto como AppImage.
- A amostra **Abrir exemplo** (20 apartamentos fictícios).
- Uma pasta para guardar os arquivos de teste e os relatórios gerados.
- Opcional: uma planilha real, preferencialmente `.xlsx`, com pelo menos 20 imóveis e uma coluna de valor.

### Dados de teste sugeridos

Para os cenários que pedem imóveis avaliandos, use:

| Nome do avaliando | Área_m2 | Padrao | Idade_anos |
|---|---:|---:|---:|
| Apartamento A — dentro da amostra | 80 | 2 | 5 |
| Apartamento B — dentro da amostra | 120 | 3 | 2 |
| Apartamento C — extrapolação controlada | 300 | 2 | 5 |

Para o teste de extrapolação inválida, use Área_m2 = 500.  
Para o teste de mínimo não positivo, use Idade_anos = -1.

---

## 2. Critério geral de aceite

O sistema será considerado aceito para uso assistido se **todos** os itens abaixo forem verdadeiros:

- [ ] O programa abre e o exemplo carrega sem mensagem de erro técnica.
- [ ] É possível desligar e religar imóveis sem perder os dados.
- [ ] É possível obter uma equação por cálculo dirigido e por sugestão.
- [ ] A equação escolhida pode ser aplicada à aba de dados e recalculada.
- [ ] Dois imóveis avaliandos podem ser lançados e projetados.
- [ ] A estimativa, o IC 80%, o campo de arbítrio e o valor adotado são coerentes.
- [ ] O enquadramento nos graus de fundamentação e precisão é legível e explicado.
- [ ] A extrapolação é sinalizada e altera o item 4 conforme a regra.
- [ ] Os diagnósticos e pontos influentes são compreensíveis.
- [ ] O relatório completo e o resumo de uma página são gerados e abrem.
- [ ] A planilha exportada contém dados, resíduos, Cook, Mahalanobis e avaliandos.
- [ ] Números e datas aparecem no padrão brasileiro.
- [ ] O programa continua legível no tema escuro do sistema.
- [ ] O trabalho é salvo, reaberto e recuperado após fechamento abrupto.

---

## 3. Cenários de aceitação

### T01 — Instalação e primeiro acesso

**Objetivo de negócio:** garantir que o avaliador consiga abrir o programa sem depender de suporte técnico.

**Como testar**
1. Instale o `.deb` pelo Instalador de Pacotes ou abra o AppImage após marcar “Permitir execução”.
2. Abra o SisAvalia pelo menu ou pelo duplo clique.
3. Observe a tela inicial.

**Resultado esperado**
- A janela abre em português do Brasil.
- A tela inicial oferece **Novo**, **Abrir planilha**, **Abrir projeto** e **Abrir exemplo**.
- Não aparece janela de terminal, “traceback” ou pedido para instalar Python.
- O aviso “Dados de exemplo. Não use em laudo.” está visível na opção de exemplo.

**Critério de aceite:** o programa abre e mostra a tela inicial em até 30 segundos, sem erro técnico.  
**Criticidade:** Alta.

---

### T02 — Importação da amostra e integridade dos dados

**Objetivo de negócio:** garantir que a amostra que o avaliador usa no laudo é a mesma que foi importada.

**Como testar**
1. Clique em **Abrir planilha** e importe uma planilha `.xlsx`, `.xls` ou `.csv`.
2. Confira o número de linhas e a ordem das colunas.
3. Verifique se valores com vírgula decimal foram reconhecidos.
4. Confira a coluna de rótulo e as colunas de texto (endereço, fonte, observação).
5. Se quiser, use **Colar do Calc** com uma tabela copiada do LibreOffice.

**Resultado esperado**
- A tabela mostra todos os imóveis importados.
- Colunas de texto não aparecem como variáveis do modelo.
- A coluna de rótulo identifica os imóveis nos gráficos e tabelas.
- O aviso de vazios aparece quando houver células vazias.

**Critério de aceite:** o número de imóveis e os valores conferem com a planilha de origem.  
**Criticidade:** Alta.

---

### T03 — Controle de imóveis ativos

**Objetivo de negócio:** permitir retirar um imóvel atípico ou com informação duvidosa sem apagar os dados.

**Como testar**
1. Abra o exemplo.
2. Desmarque o primeiro imóvel na coluna **Ativo**.
3. Observe a barra de status e o modelo.
4. Clique em **Reativar todos**.
5. Clique em **Desfazer** após uma desativação em lote na aba de resíduos, se aplicável.

**Resultado esperado**
- O imóvel continua na tabela, apenas desligado.
- A contagem “Na conta” diminui e “Desligados” aumenta.
- O modelo é recalculado com o novo número de imóveis.
- Reativar todos volta ao número original.
- **Desfazer** restaura a última desativação em lote.

**Critério de aceite:** o número de imóveis usados no modelo corresponde exatamente aos ativos.  
**Criticidade:** Alta.

---

### T04 — Exploração e consistência da amostra

**Objetivo de negócio:** identificar erros de digitação, vazios e imóveis muito diferentes antes de modelar.

**Como testar**
1. Vá à aba **2. Explorar**.
2. Confira mínimo, máximo, média, mediana, desvio padrão e vazios de cada variável.
3. Veja a dispersão de Área_m2 × Valor_unitario.
4. Veja o histograma de Área_m2.
5. Apague um valor de área na aba de dados e volte à exploração.

**Resultado esperado**
- A faixa de alerta informa vazios e colunas de texto.
- Os gráficos têm eixos legíveis e números no padrão brasileiro.
- O avaliando selecionado aparece destacado na dispersão quando já houver projeção.
- **Copiar Imagem** e **Salvar Imagem** funcionam.

**Critério de aceite:** o avaliador consegue identificar a faixa dos dados e um ponto fora do padrão sem consultar outra ferramenta.  
**Criticidade:** Média.

---

### T05 — Modelagem dirigida

**Objetivo de negócio:** obter uma equação de regressão linear que represente o mercado e seja estatisticamente defensável.

**Como testar**
1. Na aba 1, confira Y = Valor_unitario, transformação ln(x).
2. Confira X = Área_m2 (ln), Padrao (x) e Idade_anos (x).
3. Vá à aba **3. Regressão & ANOVA** e clique em **Calcular este modelo**.
4. Leia a equação, R², R² ajustado, ANOVA e coeficientes.
5. Verifique a matriz de correlação e os avisos de sinal invertido.

**Resultado esperado**
- A equação aparece escrita com coeficientes no padrão brasileiro.
- O número de imóveis usados e os que saíram por vazio são informados.
- A ANOVA tem SQ, GL, QM, F e p-valor.
- Os coeficientes têm estimativa, erro padrão, t e p-valor.
- Se R² < 0,75, aparece o aviso de que a equação explica pouco.

**Critério de aceite:** o modelo é calculado sem erro e o avaliador consegue explicar o sentido dos coeficientes.  
**Criticidade:** Alta.

---

### T06 — Sugestão de equações e julgamento profissional

**Objetivo de negócio:** usar a busca automática como apoio, sem transformar a sugestão em decisão automática.

**Como testar**
1. Na aba 3, clique em **Sugerir equações**.
2. Observe a barra de progresso e o texto de aviso.
3. Selecione a primeira equação e clique em **Usar este modelo**.
4. Confira se a aba 1 foi preenchida e se o modelo foi recalculado.
5. Volte à lista e confira as colunas: R², R² ajustado, p do F, pior p, sinais, n e grau estimado.

**Resultado esperado**
- A busca termina ou pode ser cancelada sem travar o programa.
- As sugestões ficam guardadas no projeto.
- O texto “A sugestão não substitui o seu julgamento” permanece visível.
- **Usar este modelo** atualiza a aba 1 e recalcula a equação.

**Critério de aceite:** a equação sugerida pode ser aplicada e o avaliador continua sendo o responsável pela escolha.  
**Criticidade:** Alta.

---

### T07 — Dois imóveis avaliandos

**Objetivo de negócio:** projetar mais de um imóvel no mesmo trabalho, como em uma avaliação em massa ou em um laudo com imóveis comparáveis.

**Como testar**
1. Na aba **4. Avaliando & NBR 14653**, clique em **Incluir avaliando**.
2. Cadastre o Apartamento A com Área_m2 80, Padrao 2 e Idade_anos 5.
3. Cadastre o Apartamento B com Área_m2 120, Padrao 3 e Idade_anos 2.
4. Selecione cada linha e observe os painéis e gráficos.

**Resultado esperado**
- Os dois avaliandos aparecem na tabela com nome e valores por X.
- Cada um tem estimativa, IC 80%, intervalo de predição, campo de arbítrio, grau de precisão e grau de fundamentação.
- A seleção de um avaliando atualiza os gráficos e a análise de sensibilidade.
- Os campos de cada avaliando ficam guardados no projeto.

**Critério de aceite:** os dois imóveis têm projeções independentes e coerentes com seus dados.  
**Criticidade:** Alta.

---

### T08 — Intervalo, arbítrio e valor adotado

**Objetivo de negócio:** escolher o valor final com transparência e dentro dos limites técnicos.

**Como testar**
1. Selecione o Apartamento A.
2. Leia a estimativa e o IC 80%.
3. Use **Arredondar 1%**.
4. Digite um valor dentro do IC e diferente da estimativa.
5. Deixe a justificativa vazia e tente exportar o relatório.
6. Preencha a justificativa e exporte.
7. Marque **Usar campo de arbítrio** e teste um valor fora de ±15%.

**Resultado esperado**
- O valor dentro do IC é aceito.
- Um valor fora do IC deixa o campo vermelho e explica o motivo.
- Sem justificativa, o relatório é bloqueado.
- Com justificativa, o relatório é gerado.
- Com “Usar campo de arbítrio”, um valor fora de ±15% é bloqueado com aviso.

**Critério de aceite:** o sistema nunca exporta um valor adotado fora do IC ou sem justificativa quando o valor difere da estimativa.  
**Criticidade:** Alta.

---

### T09 — Extrapolação e enquadramento NBR

**Objetivo de negócio:** reconhecer quando o imóvel está fora da faixa de mercado da amostra e refletir isso no grau de fundamentação.

**Como testar**
1. Cadastre o Apartamento C com Área_m2 300, Padrao 2, Idade_anos 5.
2. Confira a tabela de extrapolação e o item 4.
3. Repita com Área_m2 500.
4. Repita com Idade_anos -1.
5. Em um caso dentro da amostra, leia os seis itens e a pontuação final.

**Resultado esperado**
- Área 300: situação “acima”, aceitável, afastamento informado, item 4 Grau II.
- Área 500: fora da faixa tolerada, item 4 sem grau.
- Idade -1: a regra da metade não se aplica porque o mínimo é zero; item 4 sem grau, com aviso.
- O grau de fundamentação e o grau de precisão aparecem separados.
- Se houver código alocado no modelo, o grau final fica limitado a II e uma frase explica o teto.

**Critério de aceite:** o item 4 e o grau final são coerentes com a posição do avaliando em relação à amostra.  
**Criticidade:** Alta.

---

### T10 — Diagnóstico e pontos influentes

**Objetivo de negócio:** identificar se um único imóvel está puxando o resultado ou se as premissas do modelo estão frágeis.

**Como testar**
1. Vá à aba **5. Resíduos & Cook**.
2. Leia o semáforo das premissas: normalidade, dispersão, multicolinearidade e Durbin-Watson.
3. Confira a tabela de resíduos: relativo, padronizado, studentizado, Cook e Mahalanobis.
4. Clique em **Desativar pontos influentes (Cook)** e confirme.
5. Observe a contagem de imóveis desligados na aba 1 e o recálculo.
6. Reative pela aba 1 se quiser repetir.

**Resultado esperado**
- A confirmação diz quantos imóveis serão desmarcados.
- O ponto desligado não é apagado.
- A análise e o modelo são atualizados.
- O resíduo relativo ≥ 40% fica amarelo e ≥ 70% fica vermelho.
- |z| > 2 aparece destacado.
- Os gráficos de Cook e Mahalanobis mostram os cortes.

**Critério de aceite:** o avaliador consegue explicar quais pontos foram retirados e por quê.  
**Criticidade:** Alta.

---

### T11 — Relatório completo, resumo e planilha

**Objetivo de negócio:** entregar o laudo e os dados de apoio no formato esperado pelo cliente ou pelo setor técnico.

**Como testar**
1. Com dois avaliandos, clique em **Exportar Relatório**.
2. Gere um PDF completo.
3. Gere um PDF com **Modo resumo (1 página)**.
4. Gere um DOCX.
5. Clique em **Exportar Planilha** e abra o `.xlsx` no LibreOffice Calc.
6. Abra os arquivos gerados.

**Resultado esperado**
- O PDF completo contém metadados, amostra, equação, ANOVA, coeficientes, projeções, fundamentação, precisão, extrapolação, premissas, resíduos e gráficos.
- O resumo tem **uma página**.
- O DOCX pode ser editado.
- A planilha tem dados, Ativo, rótulo, estimado, resíduos, Cook, Mahalanobis e a aba de avaliandos.
- Ao terminar, o programa oferece **Abrir arquivo agora**.

**Critério de aceite:** os três formatos abrem e os valores conferem com a tela.  
**Criticidade:** Alta.

---

### T12 — Salvamento, reabertura e recuperação

**Objetivo de negócio:** não perder o trabalho técnico em caso de fechamento, queda de energia ou erro do computador.

**Como testar**
1. Salve o projeto em `.sisproj`.
2. Feche o programa.
3. Abra o projeto pelo menu, por **Recentes** ou por duplo clique no arquivo.
4. Confira metadados, avaliandos, valores adotados, justificativa, itens manuais e sugestões.
5. Faça uma alteração, aguarde o backup automático e simule um fechamento abrupto.
6. Abra novamente e aceite recuperar o trabalho.

**Resultado esperado**
- O projeto volta com o estado completo.
- O programa pergunta antes de fechar com alteração não salva.
- A mensagem “Encontramos um trabalho não salvo da última vez. Deseja recuperá-lo?” aparece quando há backup.
- Recusar a recuperação descarta o backup; aceitar restaura o trabalho.

**Critério de aceite:** nenhum avaliando, valor adotado ou justificativa é perdido ao reabrir.  
**Criticidade:** Alta.

---

### T13 — Legibilidade, tema escuro e padrão brasileiro

**Objetivo de negócio:** garantir que o laudo e a leitura em tela sejam confortáveis e sem ambiguidade de números.

**Como testar**
1. Coloque o Linux no tema escuro e abra o programa.
2. Abra o seletor de arquivos e selecione uma pasta.
3. Troque o tamanho da fonte para Grande e Muito Grande.
4. Percorra as abas e confira números, datas e tabelas.
5. Use Tab, Enter e Espaço para navegar em um formulário.

**Resultado esperado**
- A interface permanece clara e os ícones ficam visíveis.
- A linha selecionada no seletor de arquivos tem fundo azul e texto escuro.
- Todos os números usam vírgula decimal e ponto de milhar.
- As datas usam dd/mm/aaaa.
- Os gráficos se ajustam ao cartão sem cortar rótulos.
- Em 1024 × 600 e 1366 × 768, a aba Dados rola e os campos de Y, transformação e rótulo ficam legíveis, sem sobreposição.
- A navegação por teclado funciona.

**Critério de aceite:** não há número em formato americano e nenhum texto/ícone ilegível no tema escuro.  
**Criticidade:** Média.

---

### T14 — Aceite final de ponta a ponta

**Objetivo de negócio:** reproduzir a rotina completa de um avaliador usando apenas o mouse.

**Como testar**
1. Abra o exemplo.
2. Desligue um imóvel.
3. Sugira equações.
4. Use a primeira equação da lista.
5. Cadastre dois avaliandos.
6. Leia os graus de fundamentação e precisão.
7. Adote um valor dentro do intervalo e escreva a justificativa.
8. Exporte o PDF.
9. Clique em **Abrir arquivo agora**.

**Resultado esperado**
- Todo o fluxo termina sem terminal, sem erro técnico e sem perda de dados.
- O PDF abre no leitor do sistema.
- O laudo contém os dois avaliandos e os graus correspondentes.

**Critério de aceite:** um usuário que só usa o mouse conclui o roteiro inteiro em uma única sessão.  
**Criticidade:** Alta.

---

## 4. Matriz-resumo

| Código | Cenário | Criticidade | Resultado |
|---|---|---|---|
| T01 | Instalação e primeiro acesso | Alta |  |
| T02 | Importação e integridade | Alta |  |
| T03 | Imóveis ativos | Alta |  |
| T04 | Exploração | Média |  |
| T05 | Modelagem dirigida | Alta |  |
| T06 | Sugestão de equações | Alta |  |
| T07 | Dois avaliandos | Alta |  |
| T08 | IC, arbítrio e valor adotado | Alta |  |
| T09 | Extrapolação e NBR | Alta |  |
| T10 | Resíduos e Cook | Alta |  |
| T11 | Relatórios e planilha | Alta |  |
| T12 | Salvamento e recuperação | Alta |  |
| T13 | Legibilidade e padrão brasileiro | Média |  |
| T14 | Aceite final | Alta |  |

**Conclusão:** se todos os cenários de criticidade Alta forem aprovados e o padrão brasileiro estiver correto, o SisAvalia está aceito para uso assistido. A aprovação não substitui a análise técnica do avaliador nem a aplicação da NBR 14653-2.

---

## 5. Como registrar um problema

Ao encontrar um comportamento inesperado, registre:

1. **Cenário:** T01, T02 etc.
2. **O que você fez:** passos seguidos.
3. **O que esperava:** resultado descrito neste guia.
4. **O que aconteceu:** texto da mensagem ou comportamento observado.
5. **Evidências:** captura de tela e, se possível, o arquivo `.sisproj`.
6. **Gravidade:** impede o laudo, atrapalha o trabalho ou é apenas visual.

Essas informações permitem corrigir o problema sem exigir conhecimento de programação do avaliador.

> Este guia é de aceitação funcional. Os testes automatizados do núcleo e os detalhes de compilação estão no [Guia técnico de testes](GUIA_DE_TESTES_TECNICO.md).
