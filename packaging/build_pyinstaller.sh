#!/usr/bin/env bash
# Compila o SisAvalia com PyInstaller --windowed --onedir.
# Este script é usado tanto pelo .deb quanto pelo AppImage.
set -euo pipefail

APP_NAME="SisAvalia"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERRO: Python 3 não encontrado." >&2
    exit 1
fi
if ! python3 -c "import PyInstaller" >/dev/null 2>&1; then
    echo "ERRO: PyInstaller não está instalado." >&2
    echo "Instale com: python3 -m pip install -r requirements-dev.txt" >&2
    exit 1
fi

if ! python3 - <<'PYCHECK'
import sys
if sys.version_info[:2] not in ((3, 11), (3, 12)):
    raise SystemExit(f"Python incompatível: {sys.version.split()[0]}. Use Python 3.11 ou 3.12.")
try:
    import PySide6
except Exception as exc:
    raise SystemExit(f"PySide6 não pôde ser importado: {exc}")
if not PySide6.__version__.startswith("6.9."):
    raise SystemExit(
        f"PySide6 {PySide6.__version__} não é compatível com o pacote portátil. "
        "Use PySide6 6.9.3, que exige glibc 2.28. PySide6 6.10+ exige glibc 2.34."
    )
PYCHECK
then
    echo "ERRO: ambiente de compilação incompatível." >&2
    echo "Use Python 3.11/3.12 e requirements-dev.txt (PySide6 6.9.3)." >&2
    exit 1
fi

echo "==> Limpando build antigo"
rm -rf build dist
mkdir -p build

echo "==> Compilando o programa com PyInstaller"
python3 -m PyInstaller \
    --noconfirm \
    --clean \
    --windowed \
    --onedir \
    --name "$APP_NAME" \
    --add-data "ui/styles.qss:ui" \
    --add-data "ui/assets:ui/assets" \
    --add-data "plugins:plugins" \
    --add-data "exemplos:exemplos" \
    --exclude-module PyQt5 \
    --exclude-module PyQt6 \
    --exclude-module PySide2 \
    --exclude-module tkinter \
    --exclude-module pytest \
    --exclude-module IPython \
    --exclude-module jedi \
    --exclude-module zmq \
    --exclude-module torch \
    --exclude-module torchvision \
    --exclude-module torchaudio \
    --exclude-module tensorflow \
    --exclude-module tensorboard \
    --exclude-module cv2 \
    --exclude-module numba \
    --exclude-module llvmlite \
    --exclude-module botocore \
    --exclude-module boto3 \
    --exclude-module s3fs \
    --exclude-module fsspec \
    --exclude-module pyarrow \
    --exclude-module gi \
    --exclude-module gi.repository.Gst \
    --exclude-module jupyter \
    --exclude-module notebook \
    --exclude-module nbformat \
    --exclude-module nbconvert \
    --hidden-import xlrd \
    --hidden-import pandas.io.excel._xlrd \
    --hidden-import pandas.io.excel._openpyxl \
    --hidden-import matplotlib.backends.backend_qtagg \
    --hidden-import matplotlib.backends.backend_agg \
    main.py

# Em algumas distribuições (por exemplo Fedora), o PyInstaller copia uma
# biblioteca FlexiBLAS sem os backends. O sistema já tem a biblioteca; deixar
# a versão do sistema evita o erro "Failed to load the BLAS fallback library".
find "$ROOT/dist/$APP_NAME" -maxdepth 2 -name 'libflexiblas*.so*' -delete 2>/dev/null || true

# O QtGui carrega libGL em tempo de importação. Em desktops ela existe, mas
# incluí-la deixa o AppImage utilizável também em ambientes mínimos.
for lib in libGL.so.1 libGLX.so.0 libGLdispatch.so.0 libEGL.so.1 libxcb.so.1; do
    for dir in /usr/lib/x86_64-linux-gnu /lib/x86_64-linux-gnu /usr/lib64 /lib64; do
        if [ -e "$dir/$lib" ]; then
            cp -L "$dir/$lib" "$ROOT/dist/$APP_NAME/_internal/"
            break
        fi
    done
done

echo "==> Verificando o programa empacotado"
if ! "$ROOT/dist/$APP_NAME/$APP_NAME" --verificar-instalacao; then
    echo "AVISO: a verificação de instalação do pacote falhou." >&2
    exit 1
fi

echo "==> Build concluído em dist/$APP_NAME"
