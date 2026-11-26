#!/usr/bin/env bash
# Gera o pacote .deb do SisAvalia usando PyInstaller --windowed --onedir.
# Uso: ./packaging/build_deb.sh
set -euo pipefail

APP_NAME="SisAvalia"
PKG_NAME="sisavalia"
VERSION="${VERSION:-1.3.1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERRO: Python 3 não encontrado." >&2
    exit 1
fi
if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "ERRO: dpkg-deb não encontrado. Este script é para Linux Mint/Ubuntu/Debian." >&2
    exit 1
fi

echo "==> Compilando o programa"
"$ROOT/packaging/build_pyinstaller.sh"

ARCH="$(dpkg --print-architecture)"
PKG_ROOT="$ROOT/build/${PKG_NAME}_${VERSION}_${ARCH}"
mkdir -p "$PKG_ROOT/DEBIAN"
mkdir -p "$PKG_ROOT/opt/sisavalia"
mkdir -p "$PKG_ROOT/usr/share/applications"
mkdir -p "$PKG_ROOT/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$PKG_ROOT/usr/share/mime/packages"
mkdir -p "$PKG_ROOT/etc/xdg"
mkdir -p "$PKG_ROOT/usr/share/doc/sisavalia"

echo "==> Copiando arquivos"
cp -a "$ROOT/dist/$APP_NAME/." "$PKG_ROOT/opt/sisavalia/"
cp "$ROOT/packaging/sisavalia.desktop" "$PKG_ROOT/usr/share/applications/sisavalia.desktop"
cp "$ROOT/ui/assets/sisavalia.svg" "$PKG_ROOT/usr/share/icons/hicolor/scalable/apps/sisavalia.svg"
cp "$ROOT/packaging/sisavalia.mime.xml" "$PKG_ROOT/usr/share/mime/packages/sisavalia.xml"
cp "$ROOT/packaging/mimeapps.list" "$PKG_ROOT/etc/xdg/mimeapps.list"
cp "$ROOT/README.md" "$PKG_ROOT/usr/share/doc/sisavalia/README.md"
cp "$ROOT/LICENSE" "$PKG_ROOT/usr/share/doc/sisavalia/copyright"
chmod +x "$PKG_ROOT/opt/sisavalia/$APP_NAME"

SIZE_KB="$(du -sk "$PKG_ROOT/opt/sisavalia" | cut -f1)"
cat > "$PKG_ROOT/DEBIAN/control" <<CONTROL
Package: $PKG_NAME
Version: $VERSION
Section: education
Priority: optional
Architecture: $ARCH
Installed-Size: $SIZE_KB
Maintainer: SisAvalia <sisavalia@exemplo.local>
Depends: libc6, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0, libxcb-xkb1, libxkbcommon-x11-0, libgl1, libegl1, libfontconfig1, libdbus-1-3, fonts-dejavu-core
Description: Análise estatística e avaliação de imóveis
 O SisAvalia é um programa desktop em português para análise estatística,
 regressão linear múltipla e engenharia de avaliações. Importa planilhas,
 sugere equações, projeta imóveis avaliandos, calcula os graus da NBR 14653-2
 e exporta relatórios em PDF ou DOCX e planilhas em XLSX.
CONTROL

cat > "$PKG_ROOT/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if command -v update-mime-database >/dev/null 2>&1; then
    update-mime-database /usr/share/mime >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
POSTINST
cat > "$PKG_ROOT/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
if command -v update-mime-database >/dev/null 2>&1; then
    update-mime-database /usr/share/mime >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
exit 0
POSTRM
chmod 755 "$PKG_ROOT/DEBIAN/postinst" "$PKG_ROOT/DEBIAN/postrm"

echo "==> Montando o .deb"
mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$PKG_ROOT" "$ROOT/dist/${PKG_NAME}_${VERSION}_${ARCH}.deb"

echo
echo "Pacote criado: dist/${PKG_NAME}_${VERSION}_${ARCH}.deb"
echo "Para instalar sem terminal, abra esse arquivo com o Instalador de Pacotes do Mint."
