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


def test_janela_cabe_em_tela_pequena(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "dados3"))
    app = QApplication.instance() or QApplication([])
    apply_theme(app, "Normal")
    from PySide6.QtWidgets import QScrollArea
    from ui.main_window import MainWindow

    window = MainWindow()
    window._startup_done = True
    window.show()
    try:
        window.open_example()
        window.resize(1024, 600)
        for _ in range(20):
            app.processEvents()
            time.sleep(0.005)
        assert window.height() <= 620, window.size()
        assert window.data_tab.findChild(QScrollArea) is not None
        assert window.plugins_tab.findChild(QScrollArea) is not None
    finally:
        window.dirty = False
        window.close()
        app.processEvents()


def test_sem_dados_volta_para_tela_inicial(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "dados4"))
    app = QApplication.instance() or QApplication([])
    apply_theme(app, "Normal")
    from ui.main_window import MainWindow

    window = MainWindow()
    window._startup_done = True
    window.show()
    try:
        window.open_example()
        for _ in range(5):
            app.processEvents()
        window.manager.delete_rows(range(window.manager.n_rows))
        window._on_data_changed("structure")
        assert window.stack.currentWidget() is window.initial_page
        assert not window.manager.has_data()
    finally:
        window.dirty = False
        window.close()
        app.processEvents()


def test_dialogo_tabelas_nbr_abre(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "dados_nbr"))
    app = QApplication.instance() or QApplication([])
    from ui.nbr_tables import NBRTablesDialog

    dialog = NBRTablesDialog()
    try:
        assert dialog.list.count() >= 9
        assert dialog.table_widget is not None
        assert "Fundamentação" in dialog.current.title
    finally:
        dialog.close()
        app.processEvents()


def test_avaliando_selecao_sobrevive_a_troca_de_aba(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "dados5"))
    app = QApplication.instance() or QApplication([])
    apply_theme(app, "Normal")
    from ui.main_window import MainWindow

    window = MainWindow()
    window._startup_done = True
    window.show()
    try:
        window.open_example()
        for _ in range(5):
            app.processEvents()
        first = window.manager.add_evaluated(
            "Primeiro", {"Area_m2": 80, "Padrao": 2, "Idade_anos": 5}
        )
        second = window.manager.add_evaluated(
            "Segundo", {"Area_m2": 120, "Padrao": 3, "Idade_anos": 2}
        )
        window.evaluation_tab.refresh()
        window.evaluation_tab.select_evaluated_id(second["id"])
        assert window.evaluation_tab.selected_id == second["id"]
        window.workspace.setCurrentIndex(0)
        app.processEvents()
        window.workspace.setCurrentIndex(3)
        for _ in range(10):
            app.processEvents()
            time.sleep(0.005)
        assert window.evaluation_tab.selected_id == second["id"]
        assert window.evaluation_tab.edit_button.isEnabled()
    finally:
        window.dirty = False
        window.close()
        app.processEvents()


def test_avaliando_incompleto_continua_editavel(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "dados6"))
    app = QApplication.instance() or QApplication([])
    apply_theme(app, "Normal")
    from ui.main_window import MainWindow

    window = MainWindow()
    window._startup_done = True
    window.show()
    try:
        window.open_example()
        for _ in range(5):
            app.processEvents()
        item = window.manager.add_evaluated(
            "Incompleto", {"Area_m2": 80, "Padrao": 2, "Idade_anos": 5}
        )
        window.evaluation_tab.refresh()
        window.evaluation_tab.select_evaluated_id(item["id"])
        # Uma nova variável deixa o avaliando antigo sem valor para ela.
        window.manager.add_column("Nova_variavel", [1.0] * window.manager.n_rows)
        window.manager.x_config["Nova_variavel"] = {
            "selected": True, "transformation": "x", "expected_sign": 0, "description": "",
        }
        window.evaluation_tab.refresh()
        assert window.evaluation_tab.selected_id == item["id"]
        assert window.evaluation_tab.edit_button.isEnabled()
        assert window.evaluation_tab.detail_stack.currentIndex() == 0
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
