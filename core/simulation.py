"""Geração de números aleatórios para a aba Simulação."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .formatting import format_number, parse_number


class SimulationError(ValueError):
    """Erro de parâmetros da simulação, com mensagem para o usuário."""


DISTRIBUTIONS = {
    "Normal": ("normal", "Média", "Desvio padrão"),
    "Uniforme": ("uniform", "Mínimo", "Máximo"),
    "Triangular": ("triangular", "Mínimo", "Modo (mais provável)", "Máximo"),
    "Exponencial": ("exponential", "Média"),
    "Poisson": ("poisson", "Média"),
}


def simulate(distribution: str, params: dict[str, Any], n: int, seed: int | None = None) -> np.ndarray:
    if n < 1:
        raise SimulationError("O tamanho N precisa ser pelo menos 1.")
    if n > 1_000_000:
        raise SimulationError("Use N de até 1.000.000 para não travar o computador.")
    key = distribution.strip().lower()
    rng = np.random.default_rng(seed)
    try:
        if key == "normal":
            mean = parse_number(params.get("mean"))
            std = parse_number(params.get("std"))
            if std <= 0:
                raise SimulationError("O desvio padrão precisa ser maior que zero.")
            return rng.normal(mean, std, size=n)
        if key == "uniforme" or key == "uniform":
            low = parse_number(params.get("low"))
            high = parse_number(params.get("high"))
            if high <= low:
                raise SimulationError("O máximo precisa ser maior que o mínimo.")
            return rng.uniform(low, high, size=n)
        if key == "triangular":
            low = parse_number(params.get("low"))
            mode = parse_number(params.get("mode"))
            high = parse_number(params.get("high"))
            if not (low <= mode <= high) or high <= low:
                raise SimulationError("No triangular, use mínimo ≤ modo ≤ máximo, com mínimo < máximo.")
            return rng.triangular(low, mode, high, size=n)
        if key == "exponencial" or key == "exponential":
            mean = parse_number(params.get("mean"))
            if mean <= 0:
                raise SimulationError("A média precisa ser maior que zero.")
            return rng.exponential(mean, size=n)
        if key == "poisson":
            mean = parse_number(params.get("mean"))
            if mean <= 0:
                raise SimulationError("A média precisa ser maior que zero.")
            return rng.poisson(mean, size=n).astype(float)
    except ValueError as exc:
        if isinstance(exc, SimulationError):
            raise
        raise SimulationError("Confira os parâmetros digitados.") from exc
    raise SimulationError("Escolha uma distribuição.")


def descriptive(values: np.ndarray) -> dict[str, float]:
    values = np.asarray(values, dtype=float)
    return {
        "n": float(len(values)),
        "min": float(np.min(values)) if len(values) else float("nan"),
        "max": float(np.max(values)) if len(values) else float("nan"),
        "mean": float(np.mean(values)) if len(values) else float("nan"),
        "median": float(np.median(values)) if len(values) else float("nan"),
        "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
    }


def export_csv(path: str | Path, values: np.ndarray) -> None:
    path = Path(path)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(["Valor simulado"])
        for value in np.asarray(values, dtype=float):
            writer.writerow([format_number(value, 4, thousands=False)])


def export_xlsx(path: str | Path, values: np.ndarray) -> None:
    frame = pd.DataFrame({"Valor simulado": np.asarray(values, dtype=float)})
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Simulacao")
        worksheet = writer.sheets["Simulacao"]
        worksheet.column_dimensions["A"].width = 20
        for cell in worksheet["A"][1:]:
            cell.number_format = "0.0000"
