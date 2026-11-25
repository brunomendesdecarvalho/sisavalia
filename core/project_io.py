"""Leitura e gravação do projeto .sisproj, autosave e recentes."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .app_paths import app_data_dir
from .data_manager import DataManager

PROJECT_EXTENSION = ".sisproj"
PROJECT_MAGIC = "SisAvalia"
PROJECT_VERSION = 1
LOGGER = logging.getLogger(__name__)


class ProjectError(ValueError):
    """Erro de projeto com mensagem amigável."""


class ProjectIO:
    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else app_data_dir()
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.backups_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.data_dir = Path(tempfile.gettempdir()) / "SisAvalia"
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.data_dir / "config.json"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def autosave_file(self) -> Path:
        return self.backups_dir / "trabalho_autosave.sisproj"

    # --------------------------------------------------------------- projeto
    def save_project(self, path: str | Path, manager: DataManager,
                     extra_state: Optional[dict[str, Any]] = None, *,
                     add_to_recent: bool = True) -> Path:
        target = Path(path)
        if target.suffix.lower() != PROJECT_EXTENSION:
            target = target.with_suffix(PROJECT_EXTENSION)
        target.parent.mkdir(parents=True, exist_ok=True)
        state = manager.to_state()
        state["app"] = PROJECT_MAGIC
        state["app_version"] = "1.2.1"
        state["saved_at"] = datetime.now().isoformat(timespec="seconds")
        if extra_state:
            state["ui"] = extra_state
        payload = json.dumps(state, ensure_ascii=False, indent=1, allow_nan=False)
        tmp_fd, tmp_name = tempfile.mkstemp(prefix=".sisavalia_", suffix=".tmp", dir=str(target.parent))
        os.close(tmp_fd)
        tmp_path = Path(tmp_name)
        try:
            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("project.json", payload)
                zf.writestr("leia-me.txt", "Projeto do SisAvalia. Abra pelo programa, não descompacte.\n")
            os.replace(tmp_path, target)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError as exc:
                    LOGGER.debug("Temporário não removido: %s", exc)
        if add_to_recent:
            self.add_recent(target)
        return target

    def load_project(self, path: str | Path, *, add_to_recent: bool = True) -> DataManager:
        target = Path(path)
        if not target.exists():
            raise ProjectError("O arquivo do projeto não foi encontrado.")
        try:
            with zipfile.ZipFile(target, "r") as zf:
                try:
                    raw = zf.read("project.json")
                except KeyError as exc:
                    raise ProjectError(
                        "Este arquivo não parece ser um projeto do SisAvalia."
                    ) from exc
                state = json.loads(raw.decode("utf-8"))
        except zipfile.BadZipFile as exc:
            raise ProjectError(
                "Não foi possível abrir este projeto. O arquivo pode estar danificado."
            ) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProjectError("O conteúdo deste projeto está danificado.") from exc
        if state.get("app") != PROJECT_MAGIC:
            raise ProjectError("Este arquivo não é um projeto do SisAvalia.")
        try:
            manager = DataManager.from_state(state)
        except Exception as exc:
            raise ProjectError(
                "O projeto foi encontrado, mas os dados não puderam ser lidos."
            ) from exc
        if add_to_recent:
            self.add_recent(target)
        return manager

    def read_state(self, path: str | Path) -> dict[str, Any]:
        target = Path(path)
        try:
            with zipfile.ZipFile(target, "r") as zf:
                return json.loads(zf.read("project.json").decode("utf-8"))
        except Exception as exc:
            raise ProjectError("Não foi possível ler o estado do projeto.") from exc

    # --------------------------------------------------------------- autosave
    def autosave(self, manager: DataManager, extra_state: Optional[dict[str, Any]] = None) -> bool:
        try:
            self.save_project(self.autosave_file, manager, extra_state, add_to_recent=False)
            return True
        except Exception:
            # Autosave nunca deve interromper o trabalho.
            return False

    def has_autosave(self) -> bool:
        return self.autosave_file.exists() and self.autosave_file.stat().st_size > 0

    def load_autosave(self) -> DataManager:
        if not self.has_autosave():
            raise ProjectError("Não há trabalho não salvo para recuperar.")
        return self.load_project(self.autosave_file, add_to_recent=False)

    def clear_autosave(self) -> None:
        try:
            if self.autosave_file.exists():
                self.autosave_file.unlink()
        except OSError as exc:
            LOGGER.debug("Autosave não removido: %s", exc)

    def autosave_datetime(self) -> Optional[str]:
        if not self.has_autosave():
            return None
        try:
            with zipfile.ZipFile(self.autosave_file, "r") as zf:
                state = json.loads(zf.read("project.json").decode("utf-8"))
            return state.get("saved_at")
        except Exception:
            return None

    # ---------------------------------------------------------------- config
    def read_config(self) -> dict[str, Any]:
        default = {"recent_files": [], "theme": "Normal", "last_directory": str(Path.home())}
        if not self.config_file.exists():
            return default
        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return default
            default.update(data)
            recent = [str(p) for p in default.get("recent_files", []) if isinstance(p, str)]
            default["recent_files"] = recent[:5]
            return default
        except Exception:
            return default

    def write_config(self, config: dict[str, Any]) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".config_", suffix=".json", dir=str(self.data_dir))
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(config, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self.config_file)
        except OSError as exc:
            LOGGER.debug("Configuração não gravada: %s", exc)

    def recent_files(self, existing_only: bool = False) -> list[str]:
        values = self.read_config().get("recent_files", [])
        if existing_only:
            return [p for p in values if Path(p).exists()]
        return list(values[:5])

    def add_recent(self, path: str | Path) -> None:
        target = str(Path(path).resolve())
        config = self.read_config()
        recent = [p for p in config.get("recent_files", []) if p != target]
        recent.insert(0, target)
        config["recent_files"] = recent[:5]
        self.write_config(config)

    def clear_recent(self) -> None:
        config = self.read_config()
        config["recent_files"] = []
        self.write_config(config)

    def get_theme(self) -> str:
        return str(self.read_config().get("theme", "Normal"))

    def set_theme(self, theme: str) -> None:
        config = self.read_config()
        config["theme"] = theme
        self.write_config(config)

    def get_last_directory(self) -> str:
        value = self.read_config().get("last_directory")
        if value and Path(value).is_dir():
            return value
        return str(Path.home())

    def set_last_directory(self, path: str | Path) -> None:
        config = self.read_config()
        folder = Path(path)
        config["last_directory"] = str(folder if folder.is_dir() else folder.parent)
        self.write_config(config)
