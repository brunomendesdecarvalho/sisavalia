"""Aba 8 — plugins."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QInputDialog, QLabel, QProgressDialog,
    QScrollArea, QVBoxLayout, QWidget,
)

from core.data_manager import DataManager
from core.plugin_manager import PluginInfo, PluginManager
from .clipboard import copy_text
from .file_dialogs import choose_directory
from .widgets import (
    Banner, Card, button, make_table, readonly_item, report_unexpected_error,
    show_error, show_info, toast,
)


class PluginsTab(QWidget):
    def __init__(self, manager: DataManager, plugin_manager: PluginManager,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.plugin_manager = plugin_manager
        self.plugins: list[PluginInfo] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)
        title = QLabel("7. Plugins")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        subtitle = QLabel(
            "Plugins são complementos opcionais. O plugin de exemplo mostra um resumo estatístico da amostra. "
            "Os plugins ficam na pasta plugins do programa."
        )
        subtitle.setObjectName("Hint")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)
        self.alert = Banner("", "warning")
        self.alert.setVisible(False)
        root.addWidget(self.alert)
        card = Card(title="Plugins instalados")
        actions = QHBoxLayout()
        self.refresh_button = button("Atualizar Plugins", "refresh",
                                      tooltip="Procura de novo nas pastas de plugins, sem remover os existentes.")
        self.run_button = button("Executar plugin", "play", primary=True)
        self.copy_button = button("Copiar lista", "copy")
        self.create_button = button("Criar Plugin", "plugin",
                                    tooltip="Cria um arquivo Python com um esqueleto de plugin.")
        self.folder_button = button("Configurar pasta", "open",
                                    tooltip="Adiciona uma pasta de plugins, mantendo as pastas atuais.")
        self.refresh_button.clicked.connect(self.update_plugins)
        self.run_button.clicked.connect(self.run_selected)
        self.copy_button.clicked.connect(self.copy_list)
        self.create_button.clicked.connect(self.create_plugin)
        self.folder_button.clicked.connect(self.configure_folder)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.run_button)
        actions.addWidget(self.create_button)
        actions.addWidget(self.folder_button)
        actions.addWidget(self.copy_button)
        actions.addStretch(1)
        card.add_layout(actions)
        self.folder_label = QLabel("")
        self.folder_label.setObjectName("Hint")
        self.folder_label.setWordWrap(True)
        card.add(self.folder_label)
        self.table = make_table(["Plugin", "O que faz", "Arquivo"])
        self.table.setMinimumHeight(280)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.doubleClicked.connect(lambda _idx: self.run_selected())
        card.add(self.table)
        hint = QLabel(
            "Um plugin recebe uma cópia dos dados e não altera a amostra por conta própria. "
            "Se um plugin falhar, o detalhe técnico vai para erros.log."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        card.add(hint)
        root.addWidget(card, 1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self.run_button.setEnabled(False)
        self.copy_button.setEnabled(False)

    def set_manager(self, manager: DataManager) -> None:
        self.manager = manager

    def _update_folder_label(self) -> None:
        folders = [str(path) for path in self.plugin_manager.plugin_directories()]
        self.folder_label.setText("Pastas procuradas:\n" + "\n".join(f"• {f}" for f in folders))

    def update_plugins(self) -> None:
        busy = QProgressDialog("Buscando plugins nas pastas configuradas...", "", 0, 0, self)
        busy.setWindowTitle("Atualizando plugins")
        busy.setCancelButton(None)
        busy.setWindowModality(Qt.WindowModality.WindowModal)
        busy.setMinimumDuration(0)
        busy.show()
        QApplication.processEvents()
        try:
            self.refresh()
        finally:
            busy.close()
            busy.deleteLater()
        if self.plugins:
            toast(self, f"{len(self.plugins)} plugin(s) encontrado(s).")
        else:
            toast(self, "Nenhum plugin encontrado.")

    def create_plugin(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Criar Plugin", "Nome do novo plugin:",
            text="Meu plugin",
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            show_error(self, "Digite um nome para o plugin.")
            return
        try:
            target = self.plugin_manager.create_plugin_template(name)
        except Exception as exc:
            show_error(self, f"Não foi possível criar o plugin: {exc}")
            return
        self._update_folder_label()
        self.refresh()
        show_info(
            self,
            f"Plugin criado em:\n{target}\n\n"
            "Abra o arquivo em um editor de texto para implementar o seu cálculo. "
            "Use Atualizar Plugins para carregá-lo.",
            title="Plugin criado",
        )

    def configure_folder(self) -> None:
        start = str(self.plugin_manager.user_plugin_dir())
        folder = choose_directory(self, "Escolher pasta de plugins", start)
        if not folder:
            return
        try:
            chosen = self.plugin_manager.add_plugin_directory(folder)
        except Exception as exc:
            show_error(self, f"Não foi possível configurar a pasta: {exc}")
            return
        self._update_folder_label()
        self.refresh()
        show_info(
            self,
            f"Pasta adicionada:\n{chosen}\n\n"
            "As pastas anteriores e os plugins existentes foram mantidos.",
            title="Pasta de plugins",
        )

    def refresh(self) -> None:
        self.plugins = self.plugin_manager.discover()
        self._update_folder_label()
        self.table.setRowCount(len(self.plugins))
        for row, info in enumerate(self.plugins):
            self.table.setItem(row, 0, readonly_item(info.plugin.name, bold=True))
            description = readonly_item(info.plugin.description)
            description.setToolTip(info.plugin.description)
            self.table.setItem(row, 1, description)
            self.table.setItem(row, 2, readonly_item(info.path.name))
            self.table.setRowHeight(row, 42)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(1, 420)
        if self.plugins:
            self.alert.setVisible(False)
            self.run_button.setEnabled(False)
            self.copy_button.setEnabled(True)
        else:
            self.alert.setText(
                "Nenhum plugin foi encontrado. O SisAvalia já vem com o plugin Resumo estatístico; "
                "confira se a pasta plugins está na instalação."
            )
            self.alert.set_role("warning")
            self.alert.setVisible(True)
            self.run_button.setEnabled(False)
            self.copy_button.setEnabled(False)
        if self.plugin_manager.errors:
            self.alert.setText("\n".join("• " + e for e in self.plugin_manager.errors))
            self.alert.set_role("warning")
            self.alert.setVisible(True)

    def _selected_index(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _selection_changed(self) -> None:
        self.run_button.setEnabled(self._selected_index() >= 0)

    def run_selected(self) -> None:
        index = self._selected_index()
        if not (0 <= index < len(self.plugins)):
            show_info(self, "Selecione um plugin na lista.")
            return
        info = self.plugins[index]
        try:
            info.plugin.run(self.manager.df.copy(), self)
        except Exception as exc:
            report_unexpected_error(self, exc, f"plugin {info.plugin.name}")

    def copy_list(self) -> None:
        if self.table.rowCount() == 0:
            show_info(self, "Não há plugins para copiar.")
            return
        from .clipboard import table_to_tsv
        copy_text(table_to_tsv(self.table))
        toast(self, "Lista de plugins copiada.")

    def refresh_theme(self) -> None:
        self.table.resizeRowsToContents()
