"""Projeção dos avaliandos e validação do valor adotado."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from .data_manager import DataManager
from .formatting import format_number, is_missing, parse_number
from .nbr14653 import NBRResult, compute_nbr
from .regression_engine import FitResult, ModelError, Prediction


@dataclass
class EvaluationResult:
    item: dict[str, Any]
    values: dict[str, float]
    prediction: Prediction
    nbr: NBRResult
    adopted: float
    use_arbitrio: bool
    justification: str
    arbitrio_low: float
    arbitrio_high: float
    adopted_inside_ci: bool
    adopted_inside_arbitrio: bool
    justification_required: bool
    blocking_messages: list[str]
    warnings: list[str]
    adopted_is_estimate: bool

    @property
    def can_export(self) -> bool:
        return not self.blocking_messages

    @property
    def name(self) -> str:
        return str(self.item.get("name", "Avaliando"))

    @property
    def fundamental_degree(self) -> str:
        return self.nbr.final_degree

    @property
    def precision_degree(self) -> str:
        return self.prediction.precision_degree


def arbitrio_range(estimate: float) -> tuple[float, float]:
    return estimate * 0.85, estimate * 1.15


def round_to_one_percent(estimate: float) -> float:
    """Arredonda para o incremento de 1% do próprio valor estimado."""
    if not math.isfinite(estimate) or estimate == 0:
        return estimate
    step = abs(estimate) * 0.01
    return round(estimate / step) * step


def evaluate_item(manager: DataManager, fit: FitResult, item: dict[str, Any]) -> EvaluationResult:
    values: dict[str, float] = {}
    for spec in manager.x_specs(True):
        name = spec["name"]
        raw = item.get("values", {}).get(name)
        if is_missing(raw):
            raise ModelError(f"O avaliando “{item.get('name', '')}” está sem o campo “{name}”.")
        values[name] = parse_number(raw)
    prediction = fit.predict_at(values)
    nbr = compute_nbr(manager, fit, prediction, values)
    adopted_raw = item.get("adopted")
    adopted_is_estimate = adopted_raw is None or is_missing(adopted_raw)
    if adopted_is_estimate:
        adopted = prediction.point
    else:
        adopted = parse_number(adopted_raw)
    use_arbitrio = bool(item.get("use_arbitrio", False))
    justification = str(item.get("justification", "") or "").strip()
    low, high = arbitrio_range(prediction.point)
    inside_ci = prediction.ci_low <= adopted <= prediction.ci_high
    inside_arbitrio = low <= adopted <= high
    blocking: list[str] = []
    warnings: list[str] = []
    if not inside_ci:
        msg = (
            "O valor adotado está fora do intervalo de confiança de 80%. "
            "Ele precisa caber entre "
            f"{format_number(prediction.ci_low, 2)} e {format_number(prediction.ci_high, 2)}."
        )
        blocking.append(msg)
        warnings.append(msg)
    if use_arbitrio and not inside_arbitrio:
        msg = (
            "O valor adotado está fora do campo de arbítrio de ±15%. "
            f"Ele precisa ficar entre {format_number(low, 2)} e {format_number(high, 2)}."
        )
        blocking.append(msg)
        warnings.append(msg)
    justification_required = abs(adopted - prediction.point) > max(0.005, abs(prediction.point) * 1e-12)
    if justification_required and not justification:
        msg = (
            "Você adotou um valor diferente da estimativa. Escreva uma justificativa "
            "curta antes de exportar o relatório."
        )
        blocking.append(msg)
        warnings.append(msg)
    if not prediction.ci_low <= prediction.point <= prediction.ci_high:
        warnings.append("A estimativa não ficou dentro do próprio intervalo. Confira o modelo.")
    return EvaluationResult(
        item=item,
        values=values,
        prediction=prediction,
        nbr=nbr,
        adopted=float(adopted),
        use_arbitrio=use_arbitrio,
        justification=justification,
        arbitrio_low=low,
        arbitrio_high=high,
        adopted_inside_ci=inside_ci,
        adopted_inside_arbitrio=inside_arbitrio,
        justification_required=justification_required,
        blocking_messages=blocking,
        warnings=warnings,
        adopted_is_estimate=adopted_is_estimate,
    )


def evaluate_all(manager: DataManager, fit: FitResult) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for item in manager.evaluated:
        try:
            results.append(evaluate_item(manager, fit, item))
        except (ModelError, ValueError):
            continue
    return results


def report_blockers(results: list[EvaluationResult], manager: DataManager) -> list[str]:
    blockers: list[str] = []
    for result in results:
        for msg in result.blocking_messages:
            text = f"{result.name}: {msg}"
            if text not in blockers:
                blockers.append(text)
    for item in manager.evaluated:
        if not any(result.item.get("id") == item.get("id") for result in results):
            blockers.append(
                f"O avaliando “{item.get('name', '')}” não pôde ser projetado. Confira os campos."
            )
    return blockers
