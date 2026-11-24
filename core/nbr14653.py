"""Enquadramento simplificado na NBR 14653-2.

As contas seguem a regra pedida pelo projeto: itens 2, 4, 5 e 6 automáticos,
itens 1 e 3 manuais, pontuação III=3, II=2, I=1 e teto II quando há código
alocado entre as independentes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from .data_manager import DataManager
from .formatting import format_number, format_pvalue, is_missing, parse_number
from .regression_engine import FitResult

GRADES = ("III", "II", "I")
GRADE_POINTS = {"III": 3, "II": 2, "I": 1, "0": 0}
GRADE_RANK = {"0": 0, "I": 1, "II": 2, "III": 3}
CHOICES = ("I", "II", "III")


def points_for(grade: str) -> int:
    return GRADE_POINTS.get(grade, 0)


def rank(grade: str) -> int:
    return GRADE_RANK.get(grade, 0)


def minimum_grade(value: str, minimum: str) -> bool:
    return rank(value) >= rank(minimum)


def lower_grade(a: str, b: str) -> str:
    return a if rank(a) <= rank(b) else b


@dataclass
class NBRItem:
    number: int
    title: str
    grade: str
    automatic: bool
    detail: str
    color: str
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def points(self) -> int:
        return points_for(self.grade)

    @property
    def grade_label(self) -> str:
        return "Não atinge" if self.grade == "0" else f"Grau {self.grade}"


@dataclass
class ExtrapolationRow:
    variable: str
    value: float
    minimum: float
    maximum: float
    situation: str
    acceptable: bool
    limit_text: str
    pulled_value: Optional[float] = None
    estimate: Optional[float] = None
    estimate_pulled: Optional[float] = None
    distance_pct: Optional[float] = None
    rule_unavailable: bool = False


@dataclass
class NBRResult:
    items: list[NBRItem]
    total_points: int
    final_degree: str
    precision_degree: str
    cap_applied: bool
    cap_explanation: str
    extrapolation: list[ExtrapolationRow]
    simultaneous_distance_pct: Optional[float]
    item4_grade: str
    item4_detail: str
    has_allocated_code: bool
    notes: list[str] = field(default_factory=list)

    @property
    def fundamentals(self) -> dict[str, str]:
        return {f"item{i.number}": i.grade for i in self.items}

    def item(self, number: int) -> NBRItem:
        for item in self.items:
            if item.number == number:
                return item
        raise KeyError(number)


def item2(n: int, k: int) -> NBRItem:
    if n >= 6 * (k + 1):
        grade, detail = "III", f"{n} imóveis efetivos ≥ 6 × ({k}+1) = {6 * (k + 1)}."
    elif n >= 4 * (k + 1):
        grade, detail = "II", f"{n} imóveis efetivos ≥ 4 × ({k}+1) = {4 * (k + 1)}."
    elif n >= 3 * (k + 1):
        grade, detail = "I", f"{n} imóveis efetivos ≥ 3 × ({k}+1) = {3 * (k + 1)}."
    else:
        grade = "0"
        detail = (
            f"{n} imóveis efetivos. O mínimo para o Grau I é 3 × ({k}+1) = "
            f"{3 * (k + 1)}. Amostra pequena para a quantidade de variáveis."
        )
    return NBRItem(
        number=2,
        title="Amostra efetiva",
        grade=grade,
        automatic=True,
        detail=detail,
        color={"III": "verde", "II": "amarelo", "I": "vermelho", "0": "vermelho"}[grade],
        extra={"n": n, "k": k},
    )


def item4_from_extrapolation(rows: list[ExtrapolationRow], simultaneous_pct: Optional[float]) -> tuple[str, str]:
    outside = [r for r in rows if r.situation != "dentro"]
    if not outside:
        return "III", "Nenhuma variável do avaliando está fora da faixa da amostra ativa."
    unavailable = [r for r in outside if r.rule_unavailable]
    if unavailable:
        names = ", ".join(r.variable for r in unavailable)
        return "0", (
            f"Não foi possível aplicar a regra da metade em {names}, porque o mínimo "
            "da amostra é menor ou igual a zero. Este item fica sem grau."
        )
    unacceptable = [r for r in outside if not r.acceptable]
    if unacceptable:
        names = ", ".join(r.variable for r in unacceptable)
        return "0", (
            f"{names} está fora até da faixa tolerada (metade do mínimo a dobro do máximo). "
            "O item 4 não atinge nenhum grau."
        )
    distances = [r.distance_pct if r.distance_pct is not None else float("inf") for r in outside]
    if len(outside) == 1 and max(distances) <= 15.0:
        return "II", (
            f"Uma variável fora da amostra, dentro da faixa tolerada, com afastamento de "
            f"{format_number(distances[0], 1)}% (limite de 15% para o Grau II)."
        )
    if all(d <= 20.0 for d in distances) and simultaneous_pct is not None and simultaneous_pct <= 20.0:
        return "I", (
            "Todas as variáveis fora estão na faixa tolerada; afastamentos de até "
            f"{format_number(max(distances), 1)}% e afastamento simultâneo de "
            f"{format_number(simultaneous_pct, 1)}% (limites de 20% para o Grau I)."
        )
    worst = max(distances)
    return "0", (
        f"Os afastamentos chegam a {format_number(worst, 1)}% e o simultâneo a "
        f"{format_number(simultaneous_pct, 1) if simultaneous_pct is not None else '—'}%. "
        "O item 4 não atinge o Grau I."
    )


def _p_relation(value: float) -> str:
    text = format_pvalue(value)
    return f"< {text[2:]}" if text.startswith("< ") else f"= {text}"


def item5(worst_p: float) -> NBRItem:
    if math.isfinite(worst_p) and worst_p <= 0.10:
        grade, detail = "III", f"Pior p-valor dos regressores {_p_relation(worst_p)} ≤ 10%."
    elif math.isfinite(worst_p) and worst_p <= 0.20:
        grade, detail = "II", f"Pior p-valor dos regressores {_p_relation(worst_p)} ≤ 20%."
    elif math.isfinite(worst_p) and worst_p <= 0.30:
        grade, detail = "I", f"Pior p-valor dos regressores {_p_relation(worst_p)} ≤ 30%."
    else:
        grade, detail = "0", (
            f"Pior p-valor dos regressores {_p_relation(worst_p)}; acima de 30%. "
            "Alguma variável pode não estar ajudando a explicar o valor."
        )
    return NBRItem(
        number=5,
        title="Significância das variáveis",
        grade=grade,
        automatic=True,
        detail=detail,
        color={"III": "verde", "II": "amarelo", "I": "vermelho", "0": "vermelho"}[grade],
        extra={"worst_p": worst_p},
    )


def item6(f_p: float) -> NBRItem:
    if math.isfinite(f_p) and f_p <= 0.01:
        grade, detail = "III", f"p-valor do teste F {_p_relation(f_p)} ≤ 1%."
    elif math.isfinite(f_p) and f_p <= 0.02:
        grade, detail = "II", f"p-valor do teste F {_p_relation(f_p)} ≤ 2%."
    elif math.isfinite(f_p) and f_p <= 0.05:
        grade, detail = "I", f"p-valor do teste F {_p_relation(f_p)} ≤ 5%."
    else:
        grade, detail = "0", (
            f"p-valor do teste F {_p_relation(f_p)}; acima de 5%. "
            "O modelo como um todo não se mostrou confiável."
        )
    return NBRItem(
        number=6,
        title="Significância do modelo",
        grade=grade,
        automatic=True,
        detail=detail,
        color={"III": "verde", "II": "amarelo", "I": "vermelho", "0": "vermelho"}[grade],
        extra={"f_p": f_p},
    )


def manual_items(manager: DataManager) -> list[NBRItem]:
    item1_grade = manager.manual_grades.get("item1", "II")
    item3_grade = manager.manual_grades.get("item3", "II")
    if item1_grade not in CHOICES:
        item1_grade = "II"
    if item3_grade not in CHOICES:
        item3_grade = "II"
    return [
        NBRItem(
            number=1,
            title="Caracterização do avaliando",
            grade=item1_grade,
            automatic=False,
            detail=(
                "Grau escolhido por você. O Grau III pede descrição completa do imóvel; "
                "o II, descrição razoável; o I, descrição mínima."
            ),
            color={"III": "verde", "II": "amarelo", "I": "vermelho"}[item1_grade],
        ),
        NBRItem(
            number=3,
            title="Identificação dos dados de mercado",
            grade=item3_grade,
            automatic=False,
            detail=(
                "Grau escolhido por você. O Grau III pede dados bem identificados e "
                "verificados; o II, dados identificados; o I, dados mínimos."
            ),
            color={"III": "verde", "II": "amarelo", "I": "vermelho"}[item3_grade],
        ),
    ]


def final_grade(items: list[NBRItem]) -> tuple[int, str]:
    total = sum(i.points for i in items)
    grades = {i.number: i.grade for i in items}
    auto = [grades.get(n, "0") for n in (2, 4, 5, 6)]
    all_grades = list(grades.values())
    if (
        total >= 16
        and all(rank(g) >= 3 for g in auto)
        and all(rank(grades.get(n, "0")) >= 2 for n in (1, 3))
    ):
        return total, "III"
    if (
        total >= 10
        and all(rank(g) >= 2 for g in auto)
        and all(rank(g) >= 1 for g in all_grades)
    ):
        return total, "II"
    if total >= 6 and all(rank(g) >= 1 for g in all_grades):
        return total, "I"
    return total, "Não enquadrado"


def provisional_degree(n: int, k: int, worst_p: float, f_p: float,
                       has_allocated_code: bool = False) -> str:
    """Grau estimado usado na tabela de sugestões, sem avaliando."""
    items = [
        NBRItem(1, "Caracterização", "II", False, "", "amarelo"),
        item2(n, k),
        NBRItem(3, "Dados de mercado", "II", False, "", "amarelo"),
        NBRItem(4, "Extrapolação", "III", False, "Sem avaliando, presume-se nenhuma extrapolação.", "verde"),
        item5(worst_p),
        item6(f_p),
    ]
    _, grade = final_grade(items)
    if has_allocated_code and grade in ("III",):
        grade = "II"
    return grade


def _safe_min_max(series: pd.Series) -> tuple[float, float]:
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) == 0:
        return float("nan"), float("nan")
    return float(np.min(values)), float(np.max(values))


def compute_extrapolation(manager: DataManager, fit: FitResult,
                          values: dict[str, Any]) -> tuple[list[ExtrapolationRow], Optional[float], list[str]]:
    rows: list[ExtrapolationRow] = []
    notes: list[str] = []
    active_mask = manager.active_mask()
    base_values = {name: parse_number(values[name]) for name in fit.x_names}
    base_estimate = fit.estimate_at(base_values)
    for name in fit.x_names:
        series = pd.to_numeric(manager.df[name], errors="coerce")[active_mask]
        minimum, maximum = _safe_min_max(series)
        raw_value = base_values[name]
        situation = "dentro"
        if raw_value > maximum:
            situation = "acima"
        elif raw_value < minimum:
            situation = "abaixo"
        acceptable = True
        rule_unavailable = False
        if situation == "acima":
            if maximum > 0:
                acceptable = raw_value <= 2.0 * maximum
                limit_text = f"até o dobro do máximo ({format_number(2.0 * maximum, 2)})"
            else:
                acceptable = False
                limit_text = "não há regra segura para máximo menor ou igual a zero"
        elif situation == "abaixo":
            if minimum > 0:
                acceptable = raw_value >= 0.5 * minimum
                limit_text = f"até a metade do mínimo ({format_number(0.5 * minimum, 2)})"
            else:
                rule_unavailable = True
                acceptable = False
                limit_text = "regra da metade indisponível: mínimo menor ou igual a zero"
                notes.append(
                    f"“{name}” está abaixo da amostra e o mínimo é menor ou igual a zero; "
                    "não é possível aplicar a regra da metade e o item 4 fica sem grau."
                )
        else:
            limit_text = "dentro da faixa da amostra ativa"
        pulled = None
        estimate_pulled = None
        distance = None
        if situation != "dentro":
            pulled = minimum if situation == "abaixo" else maximum
            pulled_values = dict(base_values)
            pulled_values[name] = pulled
            try:
                estimate_pulled = fit.estimate_at(pulled_values)
                if abs(estimate_pulled) > 0:
                    distance = abs(base_estimate - estimate_pulled) / abs(estimate_pulled) * 100.0
                else:
                    distance = float("inf")
            except Exception:
                distance = float("inf")
        rows.append(ExtrapolationRow(
            variable=name,
            value=raw_value,
            minimum=minimum,
            maximum=maximum,
            situation=situation,
            acceptable=acceptable,
            limit_text=limit_text,
            pulled_value=pulled,
            estimate=base_estimate,
            estimate_pulled=estimate_pulled,
            distance_pct=distance,
            rule_unavailable=rule_unavailable,
        ))
    outside = [r for r in rows if r.situation != "dentro"]
    simultaneous: Optional[float] = None
    if outside:
        simultaneous_values = dict(base_values)
        for row in outside:
            simultaneous_values[row.variable] = row.pulled_value
        try:
            estimate_simultaneous = fit.estimate_at(simultaneous_values)
            if abs(estimate_simultaneous) > 0:
                simultaneous = abs(base_estimate - estimate_simultaneous) / abs(estimate_simultaneous) * 100.0
        except Exception:
            simultaneous = float("inf")
    return rows, simultaneous, notes


def compute_nbr(manager: DataManager, fit: FitResult, prediction: Any,
                values: dict[str, Any]) -> NBRResult:
    rows, simultaneous, notes = compute_extrapolation(manager, fit, values)
    grade4, detail4 = item4_from_extrapolation(rows, simultaneous)
    item4 = NBRItem(
        number=4,
        title="Extrapolação",
        grade=grade4,
        automatic=True,
        detail=detail4,
        color={"III": "verde", "II": "amarelo", "I": "vermelho", "0": "vermelho"}[grade4],
        extra={"simultaneous_pct": simultaneous},
    )
    items = manual_items(manager)
    items.insert(1, item2(fit.n_obs, fit.k))
    items.insert(3, item4)
    items.append(item5(fit.worst_regressor_p))
    items.append(item6(fit.f_pvalue))
    items.sort(key=lambda i: i.number)
    total, final = final_grade(items)
    allocated = [s for s in manager.x_specs(True) if s["type"] == "Código alocado"]
    cap_applied = False
    cap_explanation = ""
    if allocated:
        names = ", ".join(s["name"] for s in allocated)
        if rank(final) > 2:
            cap_applied = True
            final = "II"
            cap_explanation = (
                f"O grau ficou limitado ao II porque o modelo usa código alocado ({names}). "
                "Código alocado não mede distância real entre categorias."
            )
        else:
            cap_explanation = (
                f"O modelo usa código alocado ({names}); por isso o grau final não pode passar de II. "
                "Código alocado não mede distância real entre categorias."
            )
    precision = prediction.precision_degree
    return NBRResult(
        items=items,
        total_points=total,
        final_degree=final,
        precision_degree=precision,
        cap_applied=cap_applied,
        cap_explanation=cap_explanation,
        extrapolation=rows,
        simultaneous_distance_pct=simultaneous,
        item4_grade=grade4,
        item4_detail=detail4,
        has_allocated_code=bool(allocated),
        notes=notes,
    )


def item_phrase(number: int) -> str:
    phrases = {
        1: "O quanto você conhece e descreveu o imóvel avaliando.",
        2: "Quantos imóveis completos entram na conta para cada variável explicativa.",
        3: "Qualidade da identificação e da verificação dos dados de mercado.",
        4: "Se o imóvel avaliando está dentro da faixa dos dados usados.",
        5: "Se cada variável do modelo realmente influencia o valor.",
        6: "Se o modelo inteiro explica o valor de forma confiável.",
    }
    return phrases.get(number, "")


def grade_phrase(grade: str) -> str:
    if grade == "III":
        return "Grau III: atende com folga."
    if grade == "II":
        return "Grau II: atende de forma razoável."
    if grade == "I":
        return "Grau I: atende no mínimo."
    return "Não atinge: precisa melhorar."
