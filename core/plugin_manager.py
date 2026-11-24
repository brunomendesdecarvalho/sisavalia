"""Descoberta e execução dos plugins."""
from __future__ import annotations

import importlib.util
import inspect
import sys
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
    def __init__(self) -> None:
        self.plugins: list[PluginInfo] = []
        self.errors: list[str] = []

    def plugin_directories(self) -> list[Path]:
        dirs: list[Path] = [resource_path("plugins")]
        extra = app_data_dir() / "plugins"
        if extra not in dirs:
            dirs.append(extra)
        return dirs

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
