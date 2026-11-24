#!/usr/bin/env python3
"""Verifica a compatibilidade mínima de glibc de um pacote PyInstaller.

Uso:
    python3 packaging/check_glibc.py dist/SisAvalia --target 2.28

Falha se algum binário exigir uma versão de glibc maior que a meta ou se
referenciar GLIBC_ABI_GNU2_TLS (introduzido no glibc 2.34).
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ELF_MAGIC = b"\x7fELF"
VERSION_RE = re.compile(r"GLIBC_(\d+)\.(\d+)")


def elf_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            with path.open("rb") as fh:
                if fh.read(4) == ELF_MAGIC:
                    found.append(path)
        except OSError:
            continue
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--target", default="2.28")
    args = parser.parse_args()
    target = tuple(int(part) for part in args.target.split(".")[:2])
    objdump = shutil.which("objdump")
    if not objdump:
        print("ERRO: objdump não encontrado; não é possível verificar a glibc.", file=sys.stderr)
        return 2
    if not args.bundle.is_dir():
        print(f"ERRO: pasta não encontrada: {args.bundle}", file=sys.stderr)
        return 2
    worst = (0, 0)
    worst_file = ""
    tls_files: list[str] = []
    for path in elf_files(args.bundle):
        try:
            symbols = subprocess.check_output(
                [objdump, "-T", str(path)], stderr=subprocess.DEVNULL, text=True, timeout=30
            )
        except Exception:
            continue
        if "GLIBC_ABI_GNU2_TLS" in symbols:
            tls_files.append(str(path.relative_to(args.bundle)))
        for major, minor in VERSION_RE.findall(symbols):
            version = (int(major), int(minor))
            if version > worst:
                worst = version
                worst_file = str(path.relative_to(args.bundle))
    print(f"Maior exigência de glibc: {worst[0]}.{worst[1]:02d} ({worst_file or 'nenhum ELF'})")
    print(f"Meta: glibc {target[0]}.{target[1]:02d}")
    if tls_files:
        print("ERRO: GLIBC_ABI_GNU2_TLS encontrado em:", file=sys.stderr)
        for item in tls_files[:10]:
            print(f"  - {item}", file=sys.stderr)
        return 1
    if worst > target:
        print(
            "ERRO: o pacote foi compilado em um sistema mais novo que a meta.\n"
            "Compile em uma distribuição com glibc <= "
            f"{target[0]}.{target[1]:02d} (por exemplo, Debian 10 ou Ubuntu 20.04).",
            file=sys.stderr,
        )
        return 1
    print("Compatibilidade de glibc aprovada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
