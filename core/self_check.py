"""Verificação de integridade dos componentes do SisAvalia.

O programa empacotado já leva o Python e as bibliotecas dentro dele. Esta
verificação serve para avisar caso um pacote tenha sido montado incompleto.
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field

from .app_paths import resource_path

REQUIRED_MODULES = (
    ("PySide6", "PySide6"),
    ("PySide6.QtGui", "PySide6/QtGui"),
    ("PySide6.QtWidgets", "PySide6/QtWidgets"),
    ("PySide6.QtPrintSupport", "PySide6/QtPrintSupport"),
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("scipy", "scipy"),
    ("statsmodels", "statsmodels"),
    ("sklearn", "scikit-learn"),
    ("matplotlib", "matplotlib"),
    ("openpyxl", "openpyxl"),
    ("docx", "python-docx"),
    ("xlrd", "xlrd"),
)

REQUIRED_ASSETS = (
    "ui/styles.qss",
    "plugins/resumo_estatistico.py",
    "exemplos/apartamentos.csv",
)


@dataclass
class InstallationReport:
    missing_modules: list[str] = field(default_factory=list)
    missing_assets: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_modules and not self.missing_assets

    @property
    def frozen(self) -> bool:
        return bool(getattr(sys, "frozen", False))

    def message(self) -> str:
        if self.ok:
            return "Todos os componentes estão presentes."
        parts: list[str] = []
        if self.missing_modules:
            parts.append("Bibliotecas que faltam: " + ", ".join(self.missing_modules) + ".")
        if self.missing_assets:
            parts.append("Arquivos que faltam: " + ", ".join(self.missing_assets) + ".")
        if self.frozen:
            parts.append(
                "Este é o programa empacotado. O pacote está incompleto; "
                "baixe ou instale novamente o arquivo do SisAvalia."
            )
        else:
            parts.append(
                "Como você está rodando a partir do código-fonte, instale os componentes "
                "com o arquivo requirements.txt. O programa não altera o Python do sistema sozinho."
            )
        return " ".join(parts)


def check_installation() -> InstallationReport:
    report = InstallationReport()
    for module_name, package_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception:
            report.missing_modules.append(package_name)
    for asset in REQUIRED_ASSETS:
        if not resource_path(asset).exists():
            report.missing_assets.append(asset)
    return report
