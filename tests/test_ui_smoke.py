"""Teste rápido da interface, sem abrir tela de verdade (offscreen)."""
from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLCONFIGDIR", str(Path(".pytest_mpl").resolve()))

from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox  # noqa: E402

from ui.theme import apply_theme  # noqa: E402


def test_janela_abre_exemplo_e_recalcula(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "dados"))
    app = QApplication.instance() or QApplication([])
    apply_theme(app, "Normal")
    from ui.main_window import MainWindow

    window = MainWindow()
    window._startup_done = True
    window.show()
    try:
        window.open_example()
        for _ in range(10):
            app.processEvents()
            time.sleep(0.005)
        assert window.manager.n_active == 20
        assert window.fit is not None
        assert window.workspace.count() == 8
        assert window.workspace.tabText(0).startswith("1. Dados")
        assert window.workspace.tabText(7).startswith("8. Plugins")
        assert app.palette().color(QPalette.ColorRole.Window).name() == "#f8fafc"
        assert app.palette().color(QPalette.ColorRole.WindowText).name() == "#0f172a"

        wrap = window.data_tab.table.cellWidget(0, 0)
        checkbox = wrap.findChild(QCheckBox)
        assert checkbox is not None and checkbox.isChecked()
        checkbox.setChecked(False)
        for _ in range(20):
            app.processEvents()
            time.sleep(0.005)
        assert window.manager.n_active == 19
        assert window.fit is not None and window.fit.n_obs == 19

        item = window.manager.add_evaluated(
            "Avaliando teste", {"Area_m2": 80, "Padrao": 2, "Idade_anos": 5}
        )
        window.evaluation_tab.refresh()
        window.evaluation_tab.select_evaluated_id(item["id"])
        assert window.current_evaluation is not None
        assert window.current_evaluation.prediction.point > 0
        assert window.current_evaluation.nbr.final_degree in ("I", "II", "III")
    finally:
        window.dirty = False
        window.close()
        app.processEvents()


def test_tema_troca_fonte(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "dados2"))
    app = QApplication.instance() or QApplication([])
    apply_theme(app, "Normal")
    from ui.main_window import MainWindow
    from ui import theme

    window = MainWindow()
    window._startup_done = True
    try:
        window.change_theme("Grande")
        app.processEvents()
        assert theme.current_mode() == "Grande"
        assert theme.current_font_pt() == 14
        window.change_theme("Muito Grande")
        app.processEvents()
        assert theme.current_font_pt() == 16
    finally:
        window.dirty = False
        window.close()
        apply_theme(app, "Normal")
        app.processEvents()
