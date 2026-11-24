"""Pastas de dados, logs e recursos do SisAvalia."""
from __future__ import annotations

import logging
import os
import sys
import tempfile
import traceback

LOGGER = logging.getLogger(__name__)
from datetime import datetime
from pathlib import Path

APP_NAME = "SisAvalia"


def app_data_dir() -> Path:
    override = os.environ.get("SISAVALIA_DATA_DIR")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        root = Path(base)
    else:
        root = Path.home() / ".local" / "share"
    path = root / APP_NAME
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        path = None
    for fallback in (Path.home() / f".{APP_NAME.lower()}", Path(tempfile.gettempdir()) / APP_NAME):
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback
        except OSError:
            continue
    raise OSError("Não foi possível criar a pasta de dados do SisAvalia.")


def backups_dir() -> Path:
    path = app_data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def error_log_path() -> Path:
    return app_data_dir() / "erros.log"


def config_path() -> Path:
    return app_data_dir() / "config.json"


def resource_path(relative: str) -> Path:
    """Resolve recurso tanto no código-fonte quanto no PyInstaller."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent
    return base / relative


def log_exception(context: str = "") -> None:
    try:
        path = error_log_path()
        with path.open("a", encoding="utf-8") as fh:
            fh.write("\n" + "=" * 72 + "\n")
            fh.write(datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
            if context:
                fh.write(f" — {context}")
            fh.write("\n")
            traceback.print_exc(file=fh)
    except OSError:
        return


def setup_logging() -> None:
    try:
        logging.basicConfig(
            filename=str(error_log_path()),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            encoding="utf-8",
        )
    except OSError:
        LOGGER.warning("Não foi possível iniciar o log em arquivo.")
