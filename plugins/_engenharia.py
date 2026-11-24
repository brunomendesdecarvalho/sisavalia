"""Cálculos puros usados pelos plugins de engenharia de avaliações.

O arquivo começa com "_" e não é descoberto como plugin. As funções não
dependem de Qt para poderem ser testadas e reaproveitadas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, median, pstdev, stdev
from typing import Iterable, Sequence

import numpy as np
from scipy import stats

# Coeficiente C de Heidecke (estado de conservação). Valores usuais da
# literatura; a calculadora também aceita um percentual manual.
HEIDECKE_C = {
    "Novo": 0.000,
    "Bom": 0.032,
    "Regular": 0.072,
    "Reparos simples": 0.152,
    "Reparos importantes": 0.352,
    "Ruim": 0.552,
    "Demolição": 0.800,
}


@dataclass
class FactorResult:
    unit_values: list[float]
    kept: list[int]
    removed: list[int]
    factor_product: float
    factor_min: float
    factor_max: float
    cv_before: float
    cv_after: float
    mean: float
    median: float
    std: float
    ci_low: float
    ci_high: float
    amplitude_pct: float
    n: int


def coefficient_of_variation(values: Sequence[float]) -> float:
    vals = [float(v) for v in values if math.isfinite(float(v))]
    if len(vals) < 2:
        return float("nan")
    m = mean(vals)
    return stdev(vals) / m * 100.0 if m else float("nan")


def sanitize(values: Sequence[float], *, criterion: str = "±30%",
             labels: Sequence[str] | None = None) -> tuple[list[float], list[int], list[int]]:
    """Remove discrepantes um a um, devolvendo valores, mantidos e removidos."""
    kept = [i for i, v in enumerate(values) if math.isfinite(float(v))]
    removed: list[int] = []
    while len(kept) >= 3:
        vals = np.asarray([values[i] for i in kept], dtype=float)
        center = float(np.mean(vals))
        if criterion.startswith("Chauvenet"):
            std = float(np.std(vals, ddof=1))
            if std <= 0:
                break
            zcrit = float(stats.norm.ppf(1.0 - 1.0 / (2.0 * len(vals))))
            deviations = np.abs(vals - center) / std
        else:
            if center == 0:
                break
            zcrit = 0.30
            deviations = np.abs(vals - center) / abs(center)
        worst = int(np.argmax(deviations))
        if deviations[worst] <= zcrit:
            break
        removed.append(kept.pop(worst))
    return [values[i] for i in kept], kept, removed


def factor_values(values: Sequence[float], factors: Sequence[float], *, area: Sequence[float] | None = None,
                  criterion: str = "±30%") -> FactorResult:
    if area is not None and len(area) != len(values):
        raise ValueError("A coluna de área precisa ter o mesmo tamanho dos valores.")
    product = 1.0
    for factor in factors:
        product *= float(factor)
    raw: list[float] = []
    for i, value in enumerate(values):
        if not math.isfinite(float(value)):
            raw.append(float("nan"))
            continue
        unit = float(value) / float(area[i]) if area is not None else float(value)
        raw.append(unit * product)
    cv_before = coefficient_of_variation([v for v in raw if math.isfinite(v)])
    cleaned, kept, removed = sanitize(raw, criterion=criterion)
    if len(cleaned) < 1:
        raise ValueError("Não sobraram valores válidos para o cálculo.")
    arr = np.asarray(cleaned, dtype=float)
    n = len(arr)
    m = float(np.mean(arr))
    sd = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    if n > 1:
        tcrit = float(stats.t.ppf(0.90, n - 1))
        half = tcrit * sd / math.sqrt(n)
    else:
        half = 0.0
    amplitude = (2 * half / m * 100.0) if m else float("nan")
    return FactorResult(
        unit_values=cleaned,
        kept=kept,
        removed=removed,
        factor_product=product,
        factor_min=min(float(f) for f in factors) if factors else 1.0,
        factor_max=max(float(f) for f in factors) if factors else 1.0,
        cv_before=cv_before,
        cv_after=coefficient_of_variation(cleaned),
        mean=m,
        median=float(np.median(arr)),
        std=sd,
        ci_low=m - half,
        ci_high=m + half,
        amplitude_pct=amplitude,
        n=n,
    )


def factor_grades(n: int, item1: str, item3: str, factor_interval_ok: bool,
                  cv_before: float, cv_after: float) -> dict[str, str]:
    """Enquadramento orientativo nas Tabelas 3, 4 e 5 da NBR 14653-2."""
    if n >= 12:
        item2 = "III"
    elif n >= 5:
        item2 = "II"
    elif n >= 3:
        item2 = "I"
    else:
        item2 = "0"
    item4 = "III" if factor_interval_ok else "0"
    points = {"III": 3, "II": 2, "I": 1, "0": 0}
    total = points[item1] + points[item2] + points[item3] + points[item4]
    mandatory_iii = points[item2] >= 3 and points[item4] >= 3 and points[item1] >= 2 and points[item3] >= 2
    mandatory_ii = points[item2] >= 2 and points[item4] >= 2
    if total >= 10 and mandatory_iii:
        final = "III"
    elif total >= 6 and mandatory_ii:
        final = "II"
    elif total >= 4 and all(points[g] >= 1 for g in (item1, item2, item3, item4)):
        final = "I"
    else:
        final = "Não enquadrado"
    amplitude = factor_interval_ok
    # A precisão usa a amplitude do IC 80% da Tabela 5.
    return {
        "item1": item1, "item2": item2, "item3": item3, "item4": item4,
        "total": str(total), "final": final,
        "heterogeneizou": "Sim" if (math.isfinite(cv_before) and math.isfinite(cv_after)
                                    and cv_after > cv_before) else "Não",
    }


def precision_grade(amplitude_pct: float) -> str:
    if not math.isfinite(amplitude_pct):
        return "Não calculado"
    if amplitude_pct <= 30:
        return "III"
    if amplitude_pct <= 40:
        return "II"
    if amplitude_pct <= 50:
        return "I"
    return "Fora de norma"


def ross_heidecke(age: float, life: float, state: str,
                  manual_c: float | None = None) -> tuple[float, float]:
    """Devolve (coeficiente de depreciação Kd, fator residual 1-Kd)."""
    life = max(float(life), 1.0)
    ratio = max(0.0, min(1.0, float(age) / life))
    base = 0.5 * (ratio + ratio * ratio)
    c = HEIDECKE_C.get(state, 0.072) if manual_c is None else float(manual_c)
    kd = base + c * (1.0 - base)
    kd = max(0.0, min(1.0, kd))
    return kd, 1.0 - kd


def equivalent_area(private_area: float, additions: Iterable[tuple[float, float]]) -> float:
    total = max(0.0, float(private_area))
    for area, price in additions:
        total += max(0.0, float(area)) * max(0.0, float(price))
    return total


def cub_reproduction(cub: float, equivalent: float, oe: float = 0.0, oi: float = 0.0,
                     ofe: float = 0.0, ofd: float = 0.0, a: float = 0.0,
                     f: float = 0.0, l: float = 0.0) -> float:
    if equivalent <= 0:
        raise ValueError("A área equivalente precisa ser maior que zero.")
    unit = float(cub) + (float(oe) + float(oi) + float(ofe) - float(ofd)) / equivalent
    return unit * equivalent * (1 + float(a) / 100.0) * (1 + float(f) / 100.0) * (1 + float(l) / 100.0)


def evolutionary_value(land_value: float, construction_value: float, fc: float = 1.0) -> float:
    return (float(land_value) + float(construction_value)) * float(fc)


def liquidation_vpl(market_value: float, months: float, monthly_expenses: float,
                    sale_expenses_pct: float, annual_rate_pct: float) -> dict[str, float]:
    months = max(0.0, float(months))
    i = (1.0 + float(annual_rate_pct) / 100.0) ** (1.0 / 12.0) - 1.0
    net_sale = float(market_value) * (1.0 - float(sale_expenses_pct) / 100.0)
    future = net_sale - float(monthly_expenses) * months
    vpl = future / ((1.0 + i) ** months) if months else future
    return {"vpl": vpl, "net_sale": net_sale, "monthly_rate_pct": i * 100.0, "months": months}


def expropriation_value(original: float, remaining: float, adaptation: float = 0.0,
                        loss: float = 0.0) -> float:
    return max(0.0, float(original) - float(remaining) + float(adaptation) + float(loss))


def rent_by_capital(value: float, annual_rate_pct: float, vacancy_pct: float = 0.0,
                    admin_pct: float = 0.0) -> dict[str, float]:
    gross = float(value) * float(annual_rate_pct) / 100.0 / 12.0
    net = gross * (1.0 - float(vacancy_pct) / 100.0) * (1.0 - float(admin_pct) / 100.0)
    return {"monthly": net, "gross": gross, "annual": net * 12.0}
