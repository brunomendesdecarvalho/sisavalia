# Arquitetura técnica do SisAvalia

## Visão geral

O SisAvalia é um aplicativo desktop em Python/PySide6. A interface fica em `ui/`, o núcleo de cálculo em `core/` e os plugins em `plugins/`. O núcleo não depende de telas, o que permite testar as contas sem abrir janela.

```text
main.py
core/
  data_manager.py       dados, tipos, transformações, ativos, undo
  regression_engine.py  OLS, ANOVA, intervalos, elasticidade, curva
  model_search.py       busca exaustiva e simplificada
  nbr14653.py           itens, pontuação, extrapolação e teto
  diagnostics.py        premissas, resíduos, Cook, Mahalanobis
  multivariate.py       K-médias e PCA
  simulation.py         distribuições e exportação
  project_io.py         .sisproj, autosave, recentes, config
  report_generator.py   PDF, DOCX e XLSX
  plugin_base.py        contrato de plugin
  plugin_manager.py     descoberta de plugins
ui/
  theme.py, styles.qss  tema, fontes mínimas e locale
  main_window.py        barra, abas, status, integração
  data_tab.py ... plugins_tab.py
  plots.py              FigureCanvasQTAgg + NavigationToolbar2QT
  dialogs.py, export_dialog.py, help_dialog.py, initial_dialog.py
  widgets.py, clipboard.py, tooltips.py
plugins/resumo_estatistico.py
packaging/build_deb.sh
exemplos/apartamentos.csv
tests/
```

## Decisões principais

### Dados

`DataManager` mantém um `DataFrame`, uma lista de ativos e uma configuração de modelo. A coluna visual “Ativo” não é apagada nem convertida em dado de modelo. Alterações estruturais e desativação em lote guardam um snapshot para desfazer.

Textos não entram na matriz de regressão. A coluna de rótulo é usada apenas para identificação em gráficos e tabelas.

### Regressão

`RegressionEngine.fit` monta a matriz com intercepto, aplica transformações e faz exclusão pela lista completa. Usa `statsmodels.OLS`. O intervalo de confiança de 80% da média usa:

```text
estimativa ± t(0,90; n−k−1) · s · sqrt(x0' (X'X)^−1 x0)
```

O intervalo de predição usa `s · sqrt(1 + h)`. Em Y logarítmico, os limites são exponenciados sem correção de smearing. O teste t do grau usa apenas os regressores.

### NBR 14653-2

`nbr14653.py` aplica os limites e as regras descritas no manual do usuário. A extrapolação é calculada recolocando a variável no limite amostral mais próximo e medindo a diferença percentual na estimativa original. Para o Grau I, o recolhimento é simultâneo.

O teto de código alocado é aplicado depois da soma dos itens.

### Diagnósticos

- Resíduos padronizados = resíduo / erro padrão dos resíduos.
- Cook e studentizado vêm de `get_influence()`.
- Mahalanobis é calculado nas independentes transformadas, com corte Beta a 5%; em amostras pequenas, qui-quadrado.
- O Durbin-Watson é sempre informativo.

### Busca de equações

O número de especificações é o produto de (1 + transformações válidas) por variável, menos o conjunto vazio. Até 1.500, enumera tudo. Acima, usa forward por significância do termo adicionado e depois transformações das variáveis mantidas, com teto de 400 ajustes. As 30 melhores por R² ajustado são guardadas.

### Projeto e backup

`.sisproj` é um ZIP com `project.json` em UTF-8. O JSON tem dados, ativos, metadados, configuração, avaliandos, NBR manual, última equação e sugestões. O autosave usa o mesmo formato em `backups/trabalho_autosave.sisproj` a cada 5 minutos. O arquivo é removido no fechamento normal; se permanecer, é oferecido na próxima abertura.

### Tema, ícones e seleção de arquivos

A aplicação usa a paleta clara fixa (`light_palette`) e o estilo Fusion. Isso evita que o tema escuro do sistema forneça ícones brancos para cartões brancos. Os ícones dos botões são desenhados pelo próprio SisAvalia em `ui/widgets.py`, com cor explícita. O seletor de arquivos é não nativo (`ui/file_dialogs.py`) e usa o mesmo tema, garantindo seleção azul com texto escuro.

### Empacotamento

`packaging/build_pyinstaller.sh` concentra a compilação PyInstaller. `build_deb.sh` monta o `.deb` para Mint/Ubuntu e `build_appimage.sh` monta um AppImage para Fedora e outras distribuições. Os dois pacotes incluem Python, bibliotecas e recursos. O aplicativo verifica a integridade dos módulos e dos recursos ao iniciar (`core/self_check.py`) e aceita `--verificar-instalacao`.

O build Windows fica em `.github/workflows/build-windows.yml`: usa Python 3.12, executa os testes, compila com PyInstaller `--windowed --onedir`, verifica o executável e publica o ZIP como artefato. Os plugins nativos em `plugins/` são copiados como dados; `_engenharia.py` começa com `_` e não é descoberto como plugin.

Para o AppImage ser portátil, o PySide6 está fixado em 6.9.3 (glibc 2.28) e o build precisa ocorrer em ambiente com glibc ≤ 2.28. `packaging/check_glibc.py` varre todos os ELF do pacote e interrompe a compilação se encontrar `GLIBC_ABI_GNU2_TLS` ou versão superior à meta. O AppImage 1.2.3 foi compilado no Debian 10 e verificado nessa mesma base.

### Relatórios

Os gráficos são figuras Matplotlib em memória, salvas em PNG a 220 dpi. O PDF é montado com `QTextDocument` e impresso com `QPrinter`; imagens entram como recursos em memória. O DOCX usa `python-docx`. O resumo tenta larguras/fontes progressivamente menores até caber em uma página no PDF.

## Segurança e privacidade

- Nada é enviado pela internet.
- O arquivo não tem senha.
- O log técnico fica em `~/.local/share/SisAvalia/erros.log`.
- Ao carregar JSON, só o `project.json` do ZIP é lido; não há extração de arquivos arbitrários.

## Limitações

- Só OLS; sem regressão não linear, DEA, redes neurais, Box-Cox, PRESS, coeficiente forçado, homogeneização por fatores ou máxima verossimilhança separada.
- A avaliação NBR é uma conta de apoio, não substitui o julgamento do avaliador.
- O programa foi desenhado para Linux Mint; o pacote é gerado para a arquitetura da máquina de build.
