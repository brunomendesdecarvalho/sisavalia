"""Descoberta e execução dos plugins."""
from __future__ import annotations

import importlib.util
import inspect
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .app_paths import app_data_dir, log_exception, resource_path
from .plugin_base import BasePlugin


@dataclass
class PluginInfo:
    plugin: BasePlugin
    path: Path
    module_name: str


class PluginManager:
    CONFIG_KEY = "plugin_directories"

    def __init__(self) -> None:
        self.plugins: list[PluginInfo] = []
        self.errors: list[str] = []
        self.extra_dirs: list[Path] = self._load_extra_dirs()

    @staticmethod
    def _config_file() -> Path:
        return app_data_dir() / "config.json"

    def _load_extra_dirs(self) -> list[Path]:
        try:
            raw = json.loads(self._config_file().read_text(encoding="utf-8"))
            values = raw.get(self.CONFIG_KEY, [])
            if not isinstance(values, list):
                return []
            result: list[Path] = []
            for value in values:
                path = Path(str(value)).expanduser()
                if path.is_dir() and path not in result:
                    result.append(path)
            return result
        except Exception:
            return []

    def _save_extra_dirs(self) -> None:
        config_file = self._config_file()
        try:
            config: dict[str, Any] = {}
            if config_file.exists():
                loaded = json.loads(config_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    config = loaded
            config[self.CONFIG_KEY] = [str(path) for path in self.extra_dirs]
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_text(json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            return

    def plugin_directories(self) -> list[Path]:
        dirs: list[Path] = [resource_path("plugins")]
        user = app_data_dir() / "plugins"
        if user not in dirs:
            dirs.append(user)
        for extra in self.extra_dirs:
            if extra.is_dir() and extra not in dirs:
                dirs.append(extra)
        return dirs

    def user_plugin_dir(self) -> Path:
        if self.extra_dirs:
            folder = self.extra_dirs[0]
        else:
            folder = app_data_dir() / "plugins"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def add_plugin_directory(self, path: str | Path) -> Path:
        folder = Path(path).expanduser().resolve()
        if not folder.is_dir():
            raise ValueError("A pasta escolhida não existe.")
        if folder not in self.extra_dirs:
            self.extra_dirs.append(folder)
            self._save_extra_dirs()
        return folder

    def create_plugin_template(self, display_name: str) -> Path:
        name = str(display_name).strip() or "Meu plugin"
        ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
        stem = re.sub(r"[^a-z0-9_]+", "_", ascii_name.lower()).strip("_") or "meu_plugin"
        if stem[0].isdigit():
            stem = "plugin_" + stem
        class_name = "".join(part.capitalize() for part in stem.split("_")) + "Plugin"
        folder = self.user_plugin_dir()
        target = folder / f"{stem}.py"
        counter = 2
        while target.exists():
            target = folder / f"{stem}_{counter}.py"
            counter += 1
        description = f"Plugin criado pelo SisAvalia: {name}."
        template = f"""# Plugin {name} — esqueleto criado pelo SisAvalia.
# Edite este arquivo. O PluginManager procura classes que herdem de BasePlugin.

from __future__ import annotations

from typing import Any

import pandas as pd
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from core.plugin_base import BasePlugin
from ui.widgets import button


class {class_name}(BasePlugin):
    name = {name!r}
    description = {description!r}

    def run(self, dataframe: pd.DataFrame, parent_widget: Any) -> Any:
        dialog = QDialog(parent_widget)
        dialog.setWindowTitle(self.name)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Plugin {name} em execução. Linhas: {{len(dataframe)}}."))
        close = button("Fechar", "close")
        close.clicked.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()
        return {{"linhas": len(dataframe)}}
"""
        target.write_text(template, encoding="utf-8")
        return target

    def discover(self) -> list[PluginInfo]:
        self.plugins = []
        self.errors = []
        seen_names: set[str] = set()
        for directory in self.plugin_directories():
            if not directory.exists() or not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.py")):
                if path.name.startswith("_"):
                    continue
                try:
                    info = self._load_file(path)
                except Exception:
                    log_exception(f"plugin {path.name}")
                    self.errors.append(f"Não foi possível carregar o plugin {path.name}.")
                    continue
                if info is None:
                    continue
                if info.plugin.name in seen_names:
                    continue
                seen_names.add(info.plugin.name)
                self.plugins.append(info)
        return self.plugins

    def _load_file(self, path: Path) -> PluginInfo | None:
        module_name = f"sisavalia_plugin_{path.stem}_{abs(hash(path.resolve())) & 0xFFFFFF:x}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            if str(path.parent) not in sys.path:
                sys.path.insert(0, str(path.parent))
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        plugin_class = None
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if obj is BasePlugin:
                continue
            if issubclass(obj, BasePlugin) and obj.__module__ == module.__name__:
                plugin_class = obj
                break
        if plugin_class is None:
            return None
        instance = plugin_class()
        if not getattr(instance, "name", "") or not getattr(instance, "description", ""):
            instance.name = instance.name or path.stem.replace("_", " ").title()
            instance.description = instance.description or "Plugin instalado no SisAvalia."
        return PluginInfo(plugin=instance, path=path, module_name=module_name)

    def run(self, info: PluginInfo, dataframe: pd.DataFrame, parent_widget: Any) -> Any:
        if not isinstance(dataframe, pd.DataFrame):
            raise ValueError("Os dados do plugin não estão disponíveis.")
        return info.plugin.run(dataframe.copy(), parent_widget)
