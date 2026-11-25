#!/usr/bin/env python3
"""Ponto de entrada do SisAvalia.

Uso: python3 main.py [arquivo.sisproj|planilha.xlsx|planilha.csv]
"""
from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path


def _prepare_environment() -> None:
    from core.app_paths import app_data_dir, log_exception, setup_logging
    try:
        cache = app_data_dir() / "matplotlib"
        cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(cache))
    except Exception:
        cache = None
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    setup_logging()


def main() -> int:
    _prepare_environment()
    from core.self_check import check_installation
    if "--verificar-instalacao" in sys.argv[1:]:
        report = check_installation()
        print(report.message())
        return 0 if report.ok else 1
    if "--testar-docx" in sys.argv[1:]:
        # Diagnóstico usado nos testes do pacote: gera um DOCX a partir de um projeto.
        index = sys.argv.index("--testar-docx")
        if index + 1 >= len(sys.argv):
            print("Uso: --testar-docx projeto.sisproj [saida.docx]")
            return 2
        project = sys.argv[index + 1]
        output = sys.argv[index + 2] if index + 2 < len(sys.argv) else "teste_laudo.docx"
        try:
            from core.project_io import ProjectIO
            from core.regression_engine import RegressionEngine
            from core.evaluation import evaluate_item
            from core.report_generator import generate_docx, make_context
            manager = ProjectIO().load_project(project)
            fit = RegressionEngine.fit(manager)
            evaluations = []
            for item in manager.evaluated:
                try:
                    evaluations.append(evaluate_item(manager, fit, item))
                except Exception:
                    continue
            context = make_context("Teste de laudo", manager, fit, evaluations)
            target = generate_docx(context, output)
            print(f"DOCX gerado: {target}")
            return 0
        except Exception as exc:
            traceback.print_exc()
            print(f"Falha ao gerar DOCX: {exc}")
            return 1
    import matplotlib
    matplotlib.use("QtAgg")
    from PySide6.QtCore import QLocale
    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from core.app_paths import log_exception, resource_path
    from ui.main_window import MainWindow
    from ui.theme import apply_theme
    from ui.widgets import install_exception_hook

    app = QApplication(sys.argv)
    app.setApplicationName("SisAvalia")
    app.setApplicationDisplayName("SisAvalia")
    app.setOrganizationName("SisAvalia")
    app.setOrganizationDomain("sisavalia.local")
    app.setDesktopFileName("sisavalia")
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(resource_path("ui/assets/sisavalia.svg"))))
    QLocale.setDefault(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil))
    app.setFont(QFont("DejaVu Sans", 12))
    install_exception_hook(app)
    check = check_installation()
    if not check.ok:
        logging.getLogger("SisAvalia").error("Verificação de instalação: %s", check.message())
        from ui.widgets import show_error
        show_error(None, check.message(), title="Instalação incompleta")
        if check.frozen:
            return 1
    try:
        window = MainWindow()
        paths = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
        if paths:
            window._initial_path = paths[0]
        window.showMaximized()
        return app.exec()
    except Exception:
        log_exception("inicialização")
        try:
            box = QMessageBox()
            box.setWindowTitle("SisAvalia não abriu")
            box.setIcon(QMessageBox.Icon.Critical)
            box.setText(
                "O SisAvalia encontrou um problema ao abrir. Feche esta janela e tente novamente. "
                "O detalhe técnico foi guardado em erros.log."
            )
            box.exec()
        except Exception:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
