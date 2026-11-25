#!/usr/bin/env bash
# Gera um AppImage portátil do SisAvalia.
# Para compatibilidade ampla, compile em ambiente com glibc <= 2.28
# (por exemplo, Debian 10) e Python 3.11/3.12. O script verifica a glibc.
set -euo pipefail

APP_NAME="SisAvalia"
VERSION="${VERSION:-1.2.0}"
ARCH="${ARCH:-x86_64}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ "${SISAVALIA_SKIP_BUILD:-0}" = "1" ]; then
    if [ ! -x "$ROOT/dist/$APP_NAME/$APP_NAME" ]; then
        echo "ERRO: SISAVALIA_SKIP_BUILD=1, mas dist/$APP_NAME/$APP_NAME não existe." >&2
        exit 1
    fi
    echo "==> Usando o pacote PyInstaller já compilado em dist/$APP_NAME"
else
    echo "==> Compilando o programa"
    "$ROOT/packaging/build_pyinstaller.sh"
fi

echo "==> Verificando compatibilidade de glibc para AppImage portátil"
python3 "$ROOT/packaging/check_glibc.py" "$ROOT/dist/$APP_NAME" --target "${SISAVALIA_GLIBC_TARGET:-2.28}"

APPDIR="$ROOT/build/SisAvalia.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
         "$APPDIR/usr/share/mime/packages" "$APPDIR/usr/share/doc/sisavalia"
cp -a "$ROOT/dist/$APP_NAME/." "$APPDIR/usr/bin/"
cp "$ROOT/README.md" "$APPDIR/usr/share/doc/sisavalia/README.md"
cp "$ROOT/LICENSE" "$APPDIR/usr/share/doc/sisavalia/copyright"

echo "==> Gerando ícone PNG"
python3 - "$ROOT/ui/assets/sisavalia.svg" "$APPDIR/sisavalia.png" <<'PYICON'
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

source, target = sys.argv[1], sys.argv[2]
renderer = QSvgRenderer(source)
image = QImage(256, 256, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
renderer.render(painter)
painter.end()
if not image.save(target, "PNG"):
    raise SystemExit("não foi possível gerar o ícone PNG")
PYICON
cp "$APPDIR/sisavalia.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/sisavalia.png"
ln -sf sisavalia.png "$APPDIR/.DirIcon"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export PATH="$HERE/usr/bin:$PATH"
exec "$HERE/usr/bin/SisAvalia" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

cat > "$APPDIR/sisavalia.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Version=1.0
Name=SisAvalia
GenericName=Avaliação de imóveis
Comment=Análise estatística, regressão e avaliação de imóveis
Exec=SisAvalia %f
Icon=sisavalia
Terminal=false
StartupNotify=true
Categories=Education;
MimeType=application/x-sisavalia;
DESKTOP
cp "$APPDIR/sisavalia.desktop" "$APPDIR/usr/share/applications/sisavalia.desktop"
cp "$ROOT/packaging/sisavalia.mime.xml" "$APPDIR/usr/share/mime/packages/sisavalia.xml"

TOOL="${APPIMAGETOOL:-}"
if [ -z "$TOOL" ]; then
    if command -v appimagetool >/dev/null 2>&1; then
        TOOL="$(command -v appimagetool)"
    else
        TOOL="$ROOT/packaging/tools/appimagetool-x86_64.AppImage"
        if [ ! -x "$TOOL" ]; then
            echo "==> Baixando o appimagetool"
            mkdir -p "$ROOT/packaging/tools"
            curl -L --fail --retry 2 \
                -o "$TOOL" \
                https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
            chmod +x "$TOOL"
        fi
    fi
fi

if ! "$TOOL" --version >/dev/null 2>&1; then
    export APPIMAGE_EXTRACT_AND_RUN=1
fi

OUTPUT="$ROOT/dist/SisAvalia-${VERSION}-${ARCH}.AppImage"
echo "==> Montando o AppImage"
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$ARCH" "$TOOL" "$APPDIR" "$OUTPUT"
chmod +x "$OUTPUT"

echo
echo "AppImage criado: $OUTPUT"
echo "Dê permissão de execução e clique duas vezes, ou abra pelo menu depois de integrar."
