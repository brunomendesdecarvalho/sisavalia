"""Contrato dos plugins do SisAvalia."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class BasePlugin(ABC):
    """Todo plugin precisa informar nome, descrição e implementar run()."""

    name: str = "Plugin sem nome"
    description: str = ""

    @abstractmethod
    def run(self, dataframe: pd.DataFrame, parent_widget: Any) -> Any:
        """Executa o plugin e devolve o que fizer sentido para ele.

        ``dataframe`` é uma cópia dos dados originais. ``parent_widget`` serve
        para abrir diálogos centralizados na janela principal.
        """
        raise NotImplementedError
