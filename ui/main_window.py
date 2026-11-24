"""Janela principal do SisAvalia."""
from __future__ import annotations

import copy
import re
from datetime import date
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLabel, QMainWindow,
    QMenu, QMessageBox, QPushButton, QStackedWidget, QTabWidget, QToolButton,
    QVBoxLayout, QWidget,
)

from core.app_paths import error_log_path, log_exception, resource_path
from core.charting import configure_matplotlib
from core.data_manager import DataManager
from core.diagnostics import DiagnosticsResult, compute_diagnostics
from core.evaluation import EvaluationResult
from core.formatting import format_number
from core.plugin_manager import PluginManager
from core.project_io import PROJECT_EXTENSION, ProjectError, ProjectIO
from core.regression_engine import FitResult, ModelError, RegressionEngine
from core.report_generator import (
    ReportContext, ReportError, export_spreadsheet as export_xlsx_report,
    generate_report, make_context,
)
from .data_tab import DataTab
from .diagnostics_tab import DiagnosticsTab
from .evaluation_tab import EvaluationTab
from .explore_tab import ExploreTab
from .export_dialog import ExportDialog
from .file_dialogs import open_file_name, save_file_name
from .help_dialog import HelpDialog
from .initial_dialog import InitialPage
from .multivariate_tab import MultivariateTab
from .plugins_tab import PluginsTab
from .regression_tab import RegressionTab
from .simulation_tab import SimulationTab
from .theme import apply_theme, icon_size
from .tooltips import tip
from .widgets import (
    ask_save_changes, ask_yes_no, button, install_exception_hook, report_unexpected_error,
    set_row_height, show_error, show_info, show_warning, standard_icon, toast,
)

APP_TITLE = "SisAvalia"


class MainWindow(QMainWindow):
    AUTOSAVE_MS = 5 * 60 * 1000

    def __init__(self) -> None:
        super().__init__()
        self.project_io = ProjectIO()
        self.manager = DataManager()
        self.fit: Optional[FitResult] = None
        self.diagnostics: Optional[DiagnosticsResult] = None
        self.project_path: Optional[Path] = None
        self.dirty = False
        self._loading_theme = False
        self._recalculating = False
        self._help_dialog: Optional[HelpDialog] = None
        self._initial_path: Optional[str] = None
        self._startup_done = False
        theme = self.project_io.get_theme()
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, theme)
        self.plugin_manager = PluginManager()
        self.plugin_manager.discover()
        self._recalc_timer = QTimer(self)
        self._recalc_timer.setSingleShot(True)
        self._recalc_timer.setInterval(80)
        self._recalc_timer.timeout.connect(self._recalculate_scheduled)
        self._build_ui(theme)
        self._setup_shortcuts()
        self._update_status()
        self._update_title()
        self._update_action_states()
        self._refresh_recent()
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(self.AUTOSAVE_MS)
        self.autosave_timer.timeout.connect(self._autosave)
        self.autosave_timer.start()
        self.resize(1360, 840)
        QTimer.singleShot(250, self._startup)

    # ------------------------------------------------------------------ visual
    def _build_ui(self, theme: str) -> None:
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(QIcon(str(resource_path("ui/assets/sisavalia.svg"))))
        central = QWidget()
        central.setObjectName("Central")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar(theme))
        self.stack = QStackedWidget()
        self.initial_page = InitialPage()
        self.initial_page.new_requested.connect(self.new_project)
        self.initial_page.open_spreadsheet_requested.connect(self.open_spreadsheet)
        self.initial_page.open_project_requested.connect(self.open_project)
        self.initial_page.open_example_requested.connect(self.open_example)
        self.initial_page.open_recent_requested.connect(self.open_recent)
        self.workspace = QTabWidget()
        self.workspace.setDocumentMode(False)
        self.workspace.setMovable(False)
        self.workspace.setUsesScrollButtons(True)
        self.data_tab = DataTab(self.manager)
        self.explore_tab = ExploreTab(self.manager)
        self.regression_tab = RegressionTab(
            self.manager,
            get_evaluation=lambda: self.current_evaluation,
            apply_spec=self.apply_suggested_spec,
        )
        self.regression_tab.calculate_callback = lambda: self.recalculate_model(
            show_errors=True, mark_dirty=True
        )
        self.evaluation_tab = EvaluationTab(self.manager)
        self.diagnostics_tab = DiagnosticsTab(self.manager)
        self.multivariate_tab = MultivariateTab(self.manager)
        self.simulation_tab = SimulationTab(self.manager)
        self.plugins_tab = PluginsTab(self.manager, self.plugin_manager)
        for widget, label in (
            (self.data_tab, "1. Dados"),
            (self.explore_tab, "2. Explorar"),
            (self.regression_tab, "3. Regressão && ANOVA"),
            (self.evaluation_tab, "4. Avaliando && NBR 14653"),
            (self.diagnostics_tab, "5. Resíduos && Cook"),
            (self.multivariate_tab, "6. K-Médias && PCA"),
            (self.simulation_tab, "7. Simulação"),
            (self.plugins_tab, "8. Plugins"),
        ):
            self.workspace.addTab(widget, label)
        self.stack.addWidget(self.initial_page)
        self.stack.addWidget(self.workspace)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self._connect_tabs()
        self.workspace.currentChanged.connect(self._tab_changed)
        self.workspace.setCurrentIndex(0)
        bar = self.statusBar()
        self.count_label = QLabel("Imóveis na conta: 0    Desligados: 0")
        self.model_label = QLabel("Modelo: não calculado")
        for label in (self.count_label, self.model_label):
            label.setAccessibleName(label.text())
            label.setContentsMargins(10, 2, 10, 2)
        bar.addPermanentWidget(self.count_label)
        bar.addPermanentWidget(self.model_label)
        bar.setSizeGripEnabled(True)
        self.stack.setCurrentWidget(self.initial_page)

    def _build_topbar(self, theme: str) -> QWidget:
        top = QWidget()
        top.setObjectName("TopBar")
        layout = QVBoxLayout(top)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(5)
        row1 = QHBoxLayout()
        row1.setSpacing(7)
        brand = QLabel("SisAvalia")
        brand.setObjectName("SectionTitle")
        brand.setToolTip("SisAvalia — análise estatística e avaliação de imóveis.")
        row1.addWidget(brand)
        row1.addSpacing(10)
        self.new_button = button("Novo", "new", tooltip="Começa um trabalho novo.")
        self.open_sheet_button = button("Abrir Planilha", "spreadsheet",
                                        tooltip="Abre .xlsx, .xls ou .csv.")
        self.save_button = button("Salvar Projeto", "save",
                                  tooltip="Salva o trabalho no formato .sisproj.")
        self.open_project_button = button("Abrir Projeto", "open",
                                          tooltip="Abre um projeto .sisproj.")
        self.recent_button = QToolButton()
        self.recent_button.setText("Recentes")
        self.recent_button.setIcon(standard_icon("recent"))
        self.recent_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.recent_button.setIconSize(QSize(icon_size(), icon_size()))
        self.recent_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.recent_button.setToolTip("Abre um dos cinco projetos mais recentes.")
        self.recent_menu = QMenu(self.recent_button)
        self.recent_button.setMenu(self.recent_menu)
        self.new_button.clicked.connect(self.new_project)
        self.open_sheet_button.clicked.connect(self.open_spreadsheet)
        self.save_button.clicked.connect(self.save_project)
        self.open_project_button.clicked.connect(self.open_project)
        for widget in (self.new_button, self.open_sheet_button, self.save_button,
                       self.open_project_button, self.recent_button):
            row1.addWidget(widget)
        row1.addStretch(1)
        layout.addLayout(row1)
        row2 = QHBoxLayout()
        row2.setSpacing(7)
        self.report_button = button("Exportar Relatório", "report",
                                    tooltip="Gera PDF ou DOCX com o resultado, a NBR e os gráficos.")
        self.export_button = button("Exportar Planilha", "spreadsheet",
                                    tooltip="Gera um .xlsx com dados, resíduos, Cook, Mahalanobis e avaliandos.")
        self.report_button.clicked.connect(self.export_report)
        self.export_button.clicked.connect(self.export_spreadsheet)
        row2.addWidget(self.report_button)
        row2.addWidget(self.export_button)
        row2.addSpacing(12)
        font_label = QLabel("Tamanho da fonte:")
        row2.addWidget(font_label)
        self.font_combo = QComboBox()
        self.font_combo.addItems(["Normal", "Grande", "Muito Grande"])
        self.font_combo.setCurrentText(theme)
        self.font_combo.setMinimumWidth(180)
        self.font_combo.setToolTip("Aumenta a letra de todas as telas. A escolha fica guardada.")
        self.font_combo.currentTextChanged.connect(self.change_theme)
        row2.addWidget(self.font_combo)
        row2.addSpacing(12)
        self.help_button = button("Ajuda Rápida", "help", tooltip="Abre o passo a passo Importar → Explorar → Modelar → Avaliar → Exportar.")
        self.help_button.clicked.connect(self.show_help)
        row2.addWidget(self.help_button)
        row2.addStretch(1)
        layout.addLayout(row2)
        return top

    def _connect_tabs(self) -> None:
        self.data_tab.data_changed.connect(self._on_data_changed)
        self.data_tab.status_message.connect(lambda msg: self.statusBar().showMessage(msg, 5000))
        self.data_tab.open_spreadsheet_requested.connect(self.open_spreadsheet)
        self.evaluation_tab.selection_changed.connect(self._on_evaluation_selection)
        self.evaluation_tab.evaluation_changed.connect(self._on_evaluation_changed)
        self.diagnostics_tab.points_deactivated.connect(self._on_points_deactivated)
        self.multivariate_tab.cluster_saved.connect(self._on_cluster_saved)
        self.simulation_tab.data_loaded.connect(self._on_simulation_loaded)
        self.regression_tab.search_finished.connect(self._on_search_finished)

    def _setup_shortcuts(self) -> None:
        for key, slot in (
            (QKeySequence.StandardKey.New, self.new_project),
            (QKeySequence.StandardKey.Open, self.open_project),
            (QKeySequence.StandardKey.Save, self.save_project),
            (QKeySequence("F1"), self.show_help),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(slot)

    # ------------------------------------------------------------------ estado
    @property
    def current_evaluation(self) -> Optional[EvaluationResult]:
        return self.evaluation_tab.current_result()

    def _update_title(self) -> None:
        work = str(self.manager.metadata.get("work_name", "") or "Trabalho sem nome")
        marker = " *" if self.dirty else ""
        file_part = f" — {self.project_path.name}" if self.project_path else ""
        self.setWindowTitle(f"{APP_TITLE} — {work}{file_part}{marker}")

    def set_dirty(self, value: bool = True) -> None:
        if self.dirty != value:
            self.dirty = value
            self._update_title()
        self._update_action_states()

    def _update_status(self) -> None:
        count = self.manager.n_active if self.manager else 0
        off = self.manager.n_inactive if self.manager else 0
        self.count_label.setText(f"Na conta: {count}    Desligados: {off}")
        if self.fit is None:
            self.model_label.setText("Modelo: não calculado")
            self.model_label.setStyleSheet("color: #991B1B; font-weight: 700;")
        else:
            r2 = format_number(self.fit.rsquared_adj, 3)
            self.model_label.setText(
                "Modelo: calculado"
            )
            self.model_label.setStyleSheet("color: #166534; font-weight: 700;")

    def _update_action_states(self) -> None:
        has_data = self.manager.has_data()
        for widget in (self.save_button, self.report_button, self.export_button):
            widget.setEnabled(has_data)
        self.recent_button.setEnabled(bool(self.project_io.recent_files()))

    def _refresh_recent(self) -> None:
        self.recent_menu.clear()
        recent = self.project_io.recent_files()
        if not recent:
            action = self.recent_menu.addAction("Nenhum projeto recente")
            action.setEnabled(False)
            self.recent_button.setEnabled(False)
            self.initial_page.set_recent([])
            return
        self.recent_button.setEnabled(True)
        for path in recent[:5]:
            file_path = Path(path)
            label = file_path.stem + ("" if file_path.exists() else " (não encontrado)")
            action = QAction(standard_icon("open"), label, self)
            action.setToolTip(str(file_path))
            action.setEnabled(file_path.exists())
            action.triggered.connect(lambda _checked=False, p=path: self.open_recent(p))
            self.recent_menu.addAction(action)
        self.recent_menu.addSeparator()
        clear_action = QAction("Limpar lista de recentes", self)
        clear_action.triggered.connect(self._clear_recent)
        self.recent_menu.addAction(clear_action)
        self.initial_page.set_recent(recent)

    def _clear_recent(self) -> None:
        self.project_io.clear_recent()
        self._refresh_recent()

    def _tab_changed(self, index: int) -> None:
        widget = self.workspace.widget(index)
        if widget is self.explore_tab:
            self.explore_tab.set_evaluation(self.current_evaluation)
        elif widget is self.regression_tab:
            self.regression_tab.set_evaluation(self.current_evaluation)

    # ------------------------------------------------------------- gerenciador
    def _install_manager(self, manager: DataManager, *, project_path: Optional[Path],
                         dirty: bool, ui_state: Optional[dict[str, Any]] = None,
                         preserve_autosave: bool = False, tab_index: int = 0) -> None:
        self.regression_tab.shutdown()
        self.manager = manager
        self.project_path = Path(project_path) if project_path else None
        self.fit = None
        self.diagnostics = None
        self.data_tab.set_manager(manager)
        self.explore_tab.set_manager(manager)
        self.regression_tab.set_manager(manager)
        self.evaluation_tab.set_manager(manager)
        self.diagnostics_tab.set_manager(manager)
        self.multivariate_tab.set_manager(manager)
        self.simulation_tab.manager = manager
        self.plugins_tab.set_manager(manager)
        if not preserve_autosave:
            self.project_io.clear_autosave()
        self.stack.setCurrentWidget(self.workspace)
        self.workspace.setCurrentIndex(0)
        self.dirty = bool(dirty)
        self._update_status()
        self._update_title()
        self._update_action_states()
        if manager.has_data():
            self.recalculate_model(show_errors=False, mark_dirty=False)
        else:
            # Sem tabela/linhas não há o que editar: volta aos cartões de
            # importar planilha, abrir projeto ou abrir exemplo.
            self._clear_model()
            self.stack.setCurrentWidget(self.initial_page)
            self.dirty = False
        if ui_state:
            selected = ui_state.get("selected_evaluated_id")
            if selected:
                self.evaluation_tab.select_evaluated_id(selected)
            try:
                idx = int(ui_state.get("tab", 0))
            except (TypeError, ValueError):
                idx = 0
            if 0 <= idx < self.workspace.count():
                self.workspace.setCurrentIndex(idx)
        self._refresh_recent()
        self._update_status()
        if not preserve_autosave:
            self.autosave_timer.start()

    def _leave_current(self, action: str = "continuar") -> bool:
        if self.fit is not None or self.manager.has_data():
            try:
                self.evaluation_tab.commit_edits()
            except Exception:
                log_exception("salvar adoção antes de trocar de arquivo")
        if not self.dirty:
            return True
        choice = ask_save_changes(self, str(self.manager.metadata.get("work_name", "")))
        if choice == "save":
            return self.save_project()
        if choice == "discard":
            return True
        return False

    # ---------------------------------------------------------------- arquivos
    def _startup(self) -> None:
        if self._startup_done:
            return
        self._startup_done = True
        recovered = False
        if self.project_io.has_autosave():
            if ask_yes_no(
                self, "Recuperar trabalho",
                "Encontramos um trabalho não salvo da última vez. Deseja recuperá-lo?",
                yes_text="Recuperar", no_text="Descartar",
                default_yes=True,
            ):
                try:
                    manager = self.project_io.load_autosave()
                    state = self.project_io.read_state(self.project_io.autosave_file)
                    ui_state = state.get("ui", {})
                    self._install_manager(manager, project_path=None, dirty=True,
                                          ui_state=ui_state, preserve_autosave=True)
                    recovered = True
                    show_info(
                        self,
                        "O trabalho não salvo foi recuperado. Use Salvar Projeto para guardar em um arquivo definitivo.",
                        title="Trabalho recuperado",
                    )
                except Exception as exc:
                    self.project_io.clear_autosave()
                    show_error(self, "Não foi possível recuperar o trabalho não salvo. Ele foi descartado.")
            else:
                self.project_io.clear_autosave()
        if not recovered and self._initial_path:
            self.open_path(self._initial_path)
        self._refresh_recent()

    def open_path(self, path: str) -> None:
        target = Path(path)
        if target.suffix.lower() == PROJECT_EXTENSION:
            self._open_project_path(target)
        elif target.suffix.lower() in (".xlsx", ".xls", ".csv"):
            self._import_path(target)
        else:
            show_error(self, "Formato não reconhecido. Use .sisproj, .xlsx, .xls ou .csv.")

    def new_project(self) -> None:
        if not self._leave_current():
            return
        manager = DataManager()
        manager.metadata["date"] = date.today().strftime("%d/%m/%Y")
        self._install_manager(manager, project_path=None, dirty=False)
        self.workspace.setCurrentIndex(0)
        self.statusBar().showMessage("Trabalho novo. Importe uma planilha ou preencha a tabela.", 6000)
        self._refresh_recent()

    def open_spreadsheet(self) -> None:
        start = self.project_io.get_last_directory()
        filename = open_file_name(
            self, "Abrir planilha", start,
            "Planilhas (*.xlsx *.xls *.csv);;Excel (*.xlsx *.xls);;CSV (*.csv);;Todos os arquivos (*)",
        )
        if not filename:
            return
        self._import_path(Path(filename))

    def _import_path(self, path: Path) -> None:
        if not self._leave_current():
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            manager = DataManager()
            manager.import_file(path)
            manager.metadata["work_name"] = path.stem.replace("_", " ")
            manager.metadata["date"] = date.today().strftime("%d/%m/%Y")
            self.project_io.set_last_directory(path.parent)
            self._install_manager(manager, project_path=None, dirty=True)
            self.statusBar().showMessage(f"Planilha aberta: {len(manager.df)} imóvel(is).", 7000)
        except Exception as exc:
            report_unexpected_error(self, exc, "importar planilha")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._refresh_recent()

    def open_project(self) -> None:
        filename = open_file_name(
            self, "Abrir projeto", self.project_io.get_last_directory(),
            "Projeto SisAvalia (*.sisproj);;Todos os arquivos (*)",
        )
        if not filename:
            return
        self._open_project_path(Path(filename))

    def _open_project_path(self, path: Path) -> None:
        if not self._leave_current():
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            state = self.project_io.read_state(path)
            manager = self.project_io.load_project(path)
            ui_state = state.get("ui", {})
            self.project_io.set_last_directory(path.parent)
            self._install_manager(manager, project_path=path, dirty=False, ui_state=ui_state)
            self.statusBar().showMessage(f"Projeto aberto: {path.name}", 6000)
        except ProjectError as exc:
            show_error(self, str(exc), title="Não foi possível abrir o projeto")
        except Exception as exc:
            report_unexpected_error(self, exc, "abrir projeto")
        finally:
            QApplication.restoreOverrideCursor()
        self._refresh_recent()

    def open_recent(self, path: str) -> None:
        target = Path(path)
        if not target.exists():
            show_error(self, "O arquivo deste projeto recente não foi encontrado. Ele pode ter sido movido.")
            self._refresh_recent()
            return
        self._open_project_path(target)

    def open_example(self) -> None:
        if not self._leave_current():
            return
        try:
            manager = DataManager()
            manager.load_example()
            self._install_manager(manager, project_path=None, dirty=False)
            self.workspace.setCurrentIndex(0)
            self.statusBar().showMessage(
                "Exemplo aberto. Dados de exemplo. Não use em laudo.", 8000
            )
        except Exception as exc:
            report_unexpected_error(self, exc, "abrir exemplo")

    def save_project(self) -> bool:
        if not self.manager.has_data():
            show_warning(self, "Ainda não há dados para salvar. Importe uma planilha ou abra o exemplo.")
            return False
        try:
            self.evaluation_tab.commit_edits()
        except Exception:
            log_exception("salvar adoção antes de gravar o projeto")
        target = self.project_path
        if target is None:
            work = re.sub(r"[^A-Za-z0-9À-ÿ _-]+", "", str(self.manager.metadata.get("work_name", "trabalho"))).strip()
            work = (work or "trabalho").replace(" ", "_")
            suggested = str(Path(self.project_io.get_last_directory()) / f"{work}{PROJECT_EXTENSION}")
            filename = save_file_name(
                self, "Salvar projeto", suggested, "Projeto SisAvalia (*.sisproj)", "sisproj"
            )
            if not filename:
                return False
            target = Path(filename)
            if target.suffix.lower() != PROJECT_EXTENSION:
                target = target.with_suffix(PROJECT_EXTENSION)
        try:
            ui_state = {
                "selected_evaluated_id": self.evaluation_tab.selected_evaluated_id,
                "tab": self.workspace.currentIndex(),
            }
            saved = self.project_io.save_project(target, self.manager, ui_state)
        except Exception as exc:
            report_unexpected_error(self, exc, "salvar projeto")
            return False
        self.project_path = saved
        self.project_io.set_last_directory(saved.parent)
        self.set_dirty(False)
        self._refresh_recent()
        self.statusBar().showMessage(f"Projeto salvo: {saved.name}", 7000)
        return True

    # ----------------------------------------------------------------- modelo
    def recalculate_model(self, *, show_errors: bool = False, mark_dirty: bool = False) -> None:
        if self._recalculating:
            return
        self._recalc_timer.stop()
        if not self.manager.has_data():
            self._clear_model()
            return
        errors, _warnings = self.manager.validate()
        if errors:
            if show_errors:
                show_error(self, "\n".join("• " + e for e in errors[:5]), title="Confira o modelo")
            self._clear_model()
            return
        self._recalculating = True
        self.model_label.setText("Modelo: calculando...")
        self.model_label.setStyleSheet("color: #92400E; font-weight: 700;")
        QApplication.processEvents()
        try:
            fit = RegressionEngine.fit(self.manager)
            diagnostics = compute_diagnostics(fit)
        except ModelError as exc:
            if show_errors:
                show_error(self, str(exc), title="Não foi possível calcular o modelo")
            self._clear_model()
            return
        except Exception as exc:
            log_exception("calcular modelo")
            self._clear_model()
            if show_errors:
                show_error(self, "Não foi possível calcular o modelo. Confira os dados e tente de novo.")
            return
        finally:
            self._recalculating = False
        self.fit = fit
        self.diagnostics = diagnostics
        try:
            self.manager.last_model = fit.to_model_record()
        except Exception:
            log_exception("guardar a última equação")
        try:
            self.regression_tab.set_model(fit, diagnostics)
            self.evaluation_tab.set_model(fit)
            self.diagnostics_tab.set_model(fit, diagnostics)
            self.explore_tab.set_evaluation(self.current_evaluation)
            self.regression_tab.set_evaluation(self.current_evaluation)
        except Exception as exc:
            log_exception("atualizar telas após o cálculo do modelo",
                          (type(exc), exc, exc.__traceback__))
            if show_errors:
                show_error(
                    self,
                    "A equação foi calculada, mas uma parte da tela não pôde ser atualizada. "
                    "O detalhe técnico foi registrado em erros.log. Salve o projeto e abra novamente.",
                    title="Modelo calculado com aviso",
                )
        self._update_status()
        if mark_dirty:
            self.set_dirty(True)

    def _clear_model(self) -> None:
        self.fit = None
        self.diagnostics = None
        self.regression_tab.set_model(None, None)
        self.evaluation_tab.set_model(None)
        self.diagnostics_tab.set_model(None, None)
        self.explore_tab.set_evaluation(None)
        self.regression_tab.set_evaluation(None)
        self._update_status()

    def _schedule_recalculate(self) -> None:
        if self.fit is not None:
            self.model_label.setText("Modelo: atualizando...")
            self.model_label.setStyleSheet("color: #92400E; font-weight: 700;")
            self._recalc_timer.start()

    def _recalculate_scheduled(self) -> None:
        if self.manager.has_data():
            self.recalculate_model(show_errors=False)

    def _on_data_changed(self, reason: str) -> None:
        if not self.manager.has_data():
            self._clear_model()
            self.project_io.clear_autosave()
            self.dirty = False
            self.stack.setCurrentWidget(self.initial_page)
            self._update_status()
            self._update_title()
            self._update_action_states()
            return
        self.set_dirty(True)
        self._update_status()
        if reason == "metadata":
            self._update_title()
            return
        self.regression_tab.mark_stale()
        if reason == "replaced":
            self.project_path = None
            self.fit = None
            self.diagnostics = None
            self.project_io.clear_autosave()
            self.regression_tab.set_model(None, None)
            self.evaluation_tab.set_model(None)
            self.diagnostics_tab.set_model(None, None)
            self.explore_tab.set_manager(self.manager)
            self.multivariate_tab.set_manager(self.manager)
            self.simulation_tab.manager = self.manager
            self.plugins_tab.set_manager(self.manager)
            self._update_status()
            self._update_title()
            return
        self.explore_tab.refresh()
        if reason in ("structure", "active"):
            self.multivariate_tab.set_manager(self.manager)
            self.plugins_tab.set_manager(self.manager)
        if self.fit is not None:
            self._schedule_recalculate()
        else:
            self.evaluation_tab.refresh()
        self._update_action_states()

    def _on_evaluation_selection(self) -> None:
        result = self.current_evaluation
        self.explore_tab.set_evaluation(result)
        self.regression_tab.set_evaluation(result)
        self._update_status()

    def _on_evaluation_changed(self) -> None:
        self.set_dirty(True)
        self._on_evaluation_selection()

    def _on_points_deactivated(self) -> None:
        self.set_dirty(True)
        self.data_tab.refresh()
        self.explore_tab.set_manager(self.manager)
        self.multivariate_tab.set_manager(self.manager)
        self.recalculate_model(show_errors=False)
        self._update_status()

    def _on_cluster_saved(self) -> None:
        self.set_dirty(True)
        self.data_tab.refresh()
        self.explore_tab.refresh()
        self._update_status()

    def _on_simulation_loaded(self) -> None:
        self.project_path = None
        self.fit = None
        self.diagnostics = None
        self.data_tab.set_manager(self.manager)
        self.explore_tab.set_manager(self.manager)
        self.regression_tab.set_manager(self.manager)
        self.evaluation_tab.set_manager(self.manager)
        self.diagnostics_tab.set_manager(self.manager)
        self.multivariate_tab.set_manager(self.manager)
        self.plugins_tab.set_manager(self.manager)
        self.stack.setCurrentWidget(self.workspace)
        self.workspace.setCurrentIndex(0)
        self.set_dirty(True)
        self._update_status()
        self._refresh_recent()

    def _on_search_finished(self) -> None:
        self.set_dirty(True)
        self.statusBar().showMessage("Sugestões guardadas no projeto. Confira antes de usar.", 6000)

    def apply_suggested_spec(self, spec: dict[str, Any]) -> None:
        self._recalc_timer.stop()
        self.data_tab.apply_suggested_spec(spec)
        self.recalculate_model(show_errors=True, mark_dirty=True)

    # ------------------------------------------------------------------- tema
    def change_theme(self, mode: str) -> None:
        if self._loading_theme:
            return
        app = QApplication.instance()
        if app is None:
            return
        apply_theme(app, mode)
        self.project_io.set_theme(mode)
        self._loading_theme = True
        self.font_combo.setCurrentText(mode)
        self._loading_theme = False
        QApplication.processEvents()
        size = QSize(icon_size(), icon_size())
        for button_widget in self.findChildren(QPushButton):
            button_widget.setIconSize(size)
        for tool_button in self.findChildren(QToolButton):
            tool_button.setIconSize(size)
        for tab in (self.data_tab, self.explore_tab, self.regression_tab,
                    self.evaluation_tab, self.diagnostics_tab, self.multivariate_tab,
                    self.simulation_tab, self.plugins_tab):
            try:
                if hasattr(tab, "refresh_theme"):
                    tab.refresh_theme()
            except Exception:
                log_exception("atualizar tema")
        self._update_status()

    # ------------------------------------------------------------- relatórios
    def export_report(self) -> None:
        if not self.manager.has_data():
            show_warning(self, "Ainda não há dados para exportar.")
            return
        try:
            self.evaluation_tab.commit_edits()
        except Exception:
            log_exception("salvar adoção antes do relatório")
        self.recalculate_model(show_errors=False, mark_dirty=False)
        if self.fit is None:
            show_warning(self, "Calcule o modelo antes de exportar o relatório. Confira os avisos da aba 3.")
            return
        if not self.manager.evaluated:
            show_warning(self, "Inclua pelo menos um imóvel avaliando na aba 4 antes de exportar.")
            return
        default_title = str(self.manager.metadata.get("work_name", "") or "Relatório de avaliação")
        dialog = ExportDialog(default_title, self.project_io.get_last_directory(), self)
        if dialog.exec() != ExportDialog.DialogCode.Accepted or not dialog.result:
            return
        options = dialog.result
        context = make_context(options["title"], self.manager, self.fit, self.evaluation_tab.evaluations)
        try:
            context.ensure_ready()
        except ReportError as exc:
            show_error(self, str(exc), title="Confira antes de exportar")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            target = generate_report(context, options["path"], options["format"],
                                     summary=bool(options["summary"]))
        except ReportError as exc:
            QApplication.restoreOverrideCursor()
            show_error(self, str(exc), title="Não foi possível gerar o relatório")
            return
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            report_unexpected_error(self, exc, "gerar relatório")
            return
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
        self.project_io.set_last_directory(Path(options["path"]).parent)
        self._report_success(target)

    def _report_success(self, path: Path) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Relatório gerado")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(f"O relatório foi gerado em:\n{path}")
        open_button = box.addButton("Abrir arquivo agora", QMessageBox.ButtonRole.AcceptRole)
        close_button = box.addButton("Fechar", QMessageBox.ButtonRole.RejectRole)
        open_button.setIcon(standard_icon("open"))
        close_button.setIcon(standard_icon("close"))
        open_button.setMinimumHeight(44)
        close_button.setMinimumHeight(44)
        box.exec()
        if box.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def export_spreadsheet(self) -> None:
        if not self.manager.has_data():
            show_warning(self, "Ainda não há dados para exportar.")
            return
        try:
            self.evaluation_tab.commit_edits()
        except Exception:
            log_exception("salvar adoção antes da planilha")
        self.recalculate_model(show_errors=False, mark_dirty=False)
        work = re.sub(r"[^A-Za-z0-9À-ÿ _-]+", "", str(self.manager.metadata.get("work_name", "dados"))).strip()
        work = (work or "dados").replace(" ", "_")
        suggested = str(Path(self.project_io.get_last_directory()) / f"{work}.xlsx")
        filename = save_file_name(
            self, "Exportar planilha", suggested, "Planilha Excel (*.xlsx)", "xlsx"
        )
        if not filename:
            return
        target = Path(filename)
        if target.suffix.lower() != ".xlsx":
            target = target.with_suffix(".xlsx")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            export_xlsx_report(self.manager, self.fit, self.diagnostics,
                               self.evaluation_tab.evaluations, target)
        except ReportError as exc:
            QApplication.restoreOverrideCursor()
            show_error(self, str(exc), title="Não foi possível exportar a planilha")
            return
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            report_unexpected_error(self, exc, "exportar planilha")
            return
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
        self.project_io.set_last_directory(target.parent)
        show_info(self, f"Planilha salva em:\n{target}", title="Planilha exportada")

    # ------------------------------------------------------------------- ajuda
    def show_help(self) -> None:
        if self._help_dialog is None:
            self._help_dialog = HelpDialog(self)
        self._help_dialog.show()
        self._help_dialog.raise_()
        self._help_dialog.activateWindow()

    # ---------------------------------------------------------------- autosave
    def _autosave(self) -> None:
        if not self.manager.has_data() or not self.dirty:
            return
        ui_state = {
            "selected_evaluated_id": self.evaluation_tab.selected_evaluated_id,
            "tab": self.workspace.currentIndex(),
        }
        if self.project_io.autosave(self.manager, ui_state):
            from datetime import datetime
            self.statusBar().showMessage(
                f"Backup automático feito às {datetime.now().strftime('%H:%M')}.", 5000
            )

    # ----------------------------------------------------------------- fechar
    def closeEvent(self, event: Any) -> None:
        try:
            self.regression_tab.shutdown()
        except Exception:
            log_exception("encerrar a busca de equações")
        self.autosave_timer.stop()
        try:
            self.evaluation_tab.commit_edits()
        except Exception:
            log_exception("salvar adoção antes de fechar")
        if self.dirty:
            choice = ask_save_changes(self, str(self.manager.metadata.get("work_name", "")))
            if choice == "cancel":
                self.autosave_timer.start()
                event.ignore()
                return
            if choice == "save":
                if not self.save_project():
                    self.autosave_timer.start()
                    event.ignore()
                    return
        self.project_io.clear_autosave()
        self.project_io.set_theme(self.font_combo.currentText())
        event.accept()
