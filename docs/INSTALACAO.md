# Instalação do SisAvalia no Linux Mint

## Para quem só quer usar o programa

### O que você precisa

- Linux Mint 21 ou 22, 64 bits.
- O arquivo `sisavalia_1.2.1_amd64.deb` (ou a versão mais nova).
- A senha do computador, caso o Instalador de Pacotes peça.

### Passo 1 — Baixar o arquivo

Baixe o `.deb` e deixe na pasta **Downloads**.

### Passo 2 — Abrir com o Instalador de Pacotes

1. Abra a pasta **Downloads**.
2. Clique **duas vezes** no arquivo `sisavalia_1.2.1_amd64.deb`.
3. O **Instalador de Pacotes** do Mint abre mostrando o nome **SisAvalia**.
4. Clique em **Instalar**.
5. Se aparecer um pedido de senha, digite a senha do seu computador e confirme.
6. Espere a mensagem de instalação concluída e feche o Instalador.

Não é preciso abrir o terminal nem digitar comandos.

### Passo 3 — Abrir pelo menu

1. Clique no **menu do Mint**.
2. Procure **SisAvalia**. Ele fica na categoria **Educação** e também aparece na busca.
3. Clique no ícone.

Na primeira vez, o programa abre a tela inicial. Use **Abrir exemplo** para aprender. O exemplo é fictício: **não use em laudo**.

## Windows

1. Baixe `SisAvalia-1.2.1-windows-x64.zip` na release.
2. Descompacte em uma pasta de sua escolha.
3. Clique duas vezes em `SisAvalia.exe`.

O ZIP inclui Python, Qt e as bibliotecas. Não é preciso instalar Python nem usar terminal. O build é produzido pelo workflow do GitHub Actions a partir do mesmo código.

## AppImage — Fedora e outras distribuições

**Compatibilidade:** o AppImage 1.2.1 exige **glibc 2.28 ou superior**. Isso inclui Linux Mint 20/21/22, Ubuntu 20.04+, Debian 10+ e Fedora moderno. Ubuntu 18.04 e Mint 19 (glibc 2.27) não são compatíveis.

1. Baixe `SisAvalia-1.2.1-x86_64.AppImage`.
2. Abra a pasta Downloads, clique com o botão direito no arquivo → **Propriedades** → **Permissões** → marque **Permitir execução**.
3. Clique duas vezes no arquivo.

O AppImage é um arquivo único e já leva o Python e as bibliotecas do programa. Não é preciso instalar Python no computador.

Em algumas distribuições é necessário ter o FUSE instalado (`libfuse2`). Se o duplo clique não abrir, instale o **AppImageLauncher** pelo centro de programas e integre o AppImage. O AppImageLauncher também cria o atalho no menu e permite associar os arquivos `.sisproj`.

### Abrir um projeto com duplo clique

Arquivos de projeto terminam em `.sisproj`. Depois da instalação, clique duas vezes em um deles. O SisAvalia abre o projeto automaticamente.

### Desinstalar

Menu do Mint → **Central de Programas** (ou Instalador de Pacotes) → procure **SisAvalia** → **Remover**. Os seus arquivos `.sisproj` e os backups em `~/.local/share/SisAvalia/` **não são apagados** por padrão.

---

## Para quem vai compilar o pacote

### Requisitos

- Python 3.11 ou superior.
- Dependências do projeto.
- PyInstaller.
- `dpkg-deb` (já existe no Mint/Ubuntu/Debian).

### Preparar o ambiente

Use **Python 3.11 ou 3.12** e as versões fixadas em `requirements-dev.txt`:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

O PySide6 está fixado em 6.9.3 porque a versão 6.10+ exige glibc 2.34. Para gerar o AppImage portátil, compile em um ambiente com glibc ≤ 2.28 (Debian 10, por exemplo) e use PySide6 6.9.3.

### Rodar sem instalar

```bash
python3 main.py
```

Para abrir um arquivo direto:

```bash
python3 main.py exemplos/apartamentos.csv
python3 main.py meu_projeto.sisproj
```

### Gerar o .deb

```bash
./packaging/build_deb.sh
```

### Gerar o AppImage

```bash
./packaging/build_appimage.sh
```

O AppImage final fica em `dist/SisAvalia-1.2.1-x86_64.AppImage`. O script compila com PyInstaller, monta o AppDir, gera o ícone PNG e usa o `appimagetool` (baixado automaticamente na primeira vez).

Antes de montar o AppImage, `packaging/check_glibc.py` verifica todos os binários do pacote. Se algum exigir glibc acima de 2.28 ou referenciar `GLIBC_ABI_GNU2_TLS`, a compilação é interrompida com instrução para usar um ambiente Debian 10/Ubuntu 20.04. Isso evita publicar um AppImage que só funciona no computador de quem compilou.

> **Importante:** gere o `.deb` na máquina Linux Mint/Ubuntu em que ele será usado. Para o AppImage portátil, use um ambiente com glibc ≤ 2.28 (Debian 10, por exemplo). O PyInstaller usa bibliotecas do sistema de compilação; um pacote feito em uma distribuição muito nova não abre em outra mais antiga.

O script:

- confere se o ambiente usa Python 3.11/3.12 e PySide6 6.9.3;
- compila com `PyInstaller --windowed --onedir`;
- inclui `ui/styles.qss`, ícones, plugins e a pasta `exemplos`;
- monta a árvore do pacote com `dpkg-deb`;
- instala o programa em `/opt/sisavalia`;
- cria o atalho `/usr/share/applications/sisavalia.desktop`;
- instala o ícone em `/usr/share/icons/hicolor/scalable/apps/sisavalia.svg`;
- registra o tipo de arquivo `application/x-sisavalia` para `.sisproj`;
- define o SisAvalia como aplicativo padrão para `.sisproj` em `/etc/xdg/mimeapps.list`;
- não abre janela de terminal (`Terminal=false`).

O arquivo final fica em:

```text
dist/sisavalia_1.2.1_amd64.deb
```

Para gerar com outra versão:

```bash
VERSION=1.2.1 ./packaging/build_deb.sh
```

### Gerar os PDFs da documentação

Requer `pandoc`, LibreOffice e o pacote Python `python-docx`:

```bash
python3 docs/gerar_pdfs.py
```

Os arquivos são gerados em:

```text
docs/Manual_do_Usuario_SisAvalia.pdf
docs/Guia_de_Testes_SisAvalia.pdf
```

### Testar o pacote

1. Abra o `.deb` no Instalador de Pacotes do Mint.
2. Instale.
3. Abra pelo menu.
4. Abra um `.sisproj` com duplo clique.

### Problemas comuns ao compilar

- **PyInstaller não encontrado**: ative o ambiente virtual e rode `pip install -r requirements-dev.txt`.
- **Falta uma biblioteca gráfica no Mint**: instale as dependências declaradas no pacote (`libxcb-cursor0`, `libxkbcommon-x11-0` etc.). O Instalador de Pacotes cuida disso automaticamente na instalação normal.
- **O ícone não aparece no menu na hora**: saia e entre na sessão, ou aguarde alguns segundos; o pacote atualiza os caches no pós-instalação.

### Sobre as dependências Python

Não é necessário instalar Python, pandas, PySide6 ou qualquer biblioteca no computador de destino. O `.deb` e o AppImage são **autocontidos**: o PyInstaller coloca o interpretador e as bibliotecas dentro do pacote.

O programa não instala pacotes sozinho. Instalação automática via `pip` poderia:
- pedir senha de administrador;
- depender de internet no computador do avaliador;
- alterar o Python do sistema.

Em vez disso, a instalação já leva tudo e o programa faz uma verificação de integridade ao abrir. Se faltar algo, ele avisa em linguagem simples.

### Verificar a instalação

O programa verifica os componentes ao abrir. Também é possível conferir sem abrir a janela:

```bash
/opt/sisavalia/SisAvalia --verificar-instalacao
```

Saída esperada: `Todos os componentes estão presentes.`

### Onde ficam as preferências e backups

```text
~/.local/share/SisAvalia/config.json
~/.local/share/SisAvalia/backups/
~/.local/share/SisAvalia/erros.log
```
