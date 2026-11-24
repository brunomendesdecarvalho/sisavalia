"""Diagnóstico das premissas, resíduos, Cook e Mahalanobis."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.stattools import durbin_watson

from .formatting import format_number, format_pvalue
from .regression_engine import FitResult


@dataclass
class NormalityBand:
    label: str
    observed_pct: float
    expected_low: float
    expected_high: float
    status: str
    count: int
    total: int

    @property
    def text(self) -> str:
        return (
            f"{self.label}: {format_number(self.observed_pct, 1)}% dos resíduos "
            f"(faixa esperada {format_number(self.expected_low, 0)}–"
            f"{format_number(self.expected_high, 0)}%)."
        )


@dataclass
class Assumption:
    key: str
    title: str
    status: str
    text: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosticRow:
    position: int
    row_id: int
    label: str
    observed: float
    estimated: float
    residual: float
    relative_pct: float
    standardized: float
    studentized: float
    cook: float
    mahalanobis: float
    influential: bool
    atypical: bool
    z_highlight: bool


@dataclass
class DiagnosticsResult:
    normality_bands: list[NormalityBand]
    normality: Assumption
    homocedasticity: Assumption
    multicollinearity: Assumption
    independence: Assumption
    shapiro_w: float
    shapiro_p: float
    shapiro_text: str
    breusch_pagan_lm: float
    breusch_pagan_p: float
    vif: dict[str, float]
    high_vif: list[str]
    high_correlations: list[tuple[str, str, float]]
    durbin_watson: float
    table: list[DiagnosticRow]
    cooks_threshold: float
    cooks_flags: list[int]
    mahalanobis_cutoff: float
    mahalanobis_flags: list[int]
    mahalanobis_approximate: bool
    notes: list[str] = field(default_factory=list)

    @property
    def influential_positions(self) -> list[int]:
        return [r.position for r in self.table if r.influential]

    @property
    def atypical_positions(self) -> list[int]:
        return [r.position for r in self.table if r.atypical]

    def table_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "Rótulo": r.label,
            "Observado": r.observed,
            "Estimado": r.estimated,
            "Resíduo": r.residual,
            "Resíduo relativo (%)": r.relative_pct,
            "Padronizado": r.standardized,
            "Studentizado": r.studentized,
            "Cook": r.cook,
            "Mahalanobis": r.mahalanobis,
        } for r in self.table])


def band_status(observed: float, low: float, high: float) -> str:
    if low <= observed <= high:
        return "verde"
    if observed < low:
        distance = low - observed
    else:
        distance = observed - high
    return "amarelo" if distance <= 5.0 else "vermelho"


def worst_status(statuses: list[str]) -> str:
    order = {"verde": 0, "amarelo": 1, "vermelho": 2}
    return max(statuses, key=lambda s: order.get(s, 2)) if statuses else "vermelho"


def compute_diagnostics(fit: FitResult) -> DiagnosticsResult:
    n = fit.n_obs
    resid = np.asarray(fit.residuals, dtype=float)
    std = np.asarray(fit.standardized_residuals, dtype=float)
    total = len(std)
    bands: list[NormalityBand] = []
    specs = [("±1σ", 1.0, 66.0, 74.0), ("±1,64σ", 1.64, 85.0, 95.0), ("±1,96σ", 1.96, 95.0, 100.0)]
    for label, cutoff, low, high in specs:
        count = int(np.sum(np.abs(std) <= cutoff))
        pct = count / total * 100.0 if total else 0.0
        bands.append(NormalityBand(label, pct, low, high, band_status(pct, low, high), count, total))
    normality_status = worst_status([b.status for b in bands])
    normality_text = {
        "verde": "A distribuição dos resíduos está próxima do esperado. O sinal está verde.",
        "amarelo": "A distribuição dos resíduos está um pouco fora do esperado. Vale olhar os pontos atípicos.",
        "vermelho": "A distribuição dos resíduos está bem diferente do esperado. Reveja a forma do modelo e os pontos extremos.",
    }[normality_status]
    try:
        shapiro = stats.shapiro(resid) if n >= 3 and np.ptp(resid) > 0 else None
        shapiro_w = float(shapiro.statistic) if shapiro is not None else float("nan")
        shapiro_p = float(shapiro.pvalue) if shapiro is not None else float("nan")
        shapiro_text = (
            f"Teste de Shapiro-Wilk (linha extra, sem cor decisiva): "
            f"p = {format_pvalue(shapiro_p)}."
        )
    except Exception:
        shapiro_w = float("nan")
        shapiro_p = float("nan")
        shapiro_text = "Teste de Shapiro-Wilk não pôde ser calculado para esta amostra."
    # Breusch-Pagan
    try:
        bp = het_breuschpagan(resid, fit.design_matrix.to_numpy(dtype=float))
        bp_lm, bp_p = float(bp[0]), float(bp[1])
        if not math.isfinite(bp_p):
            raise ValueError
        if bp_p >= 0.05:
            bp_status = "verde"
            bp_text = (
                f"Breusch-Pagan: p = {format_pvalue(bp_p)}. Não há sinal forte de que "
                "a dispersão dos erros mude com o valor estimado. Sinal verde."
            )
        elif bp_p >= 0.01:
            bp_status = "amarelo"
            bp_text = (
                f"Breusch-Pagan: p = {format_pvalue(bp_p)}. Há alguma indicação de "
                "dispersão desigual. Sinal amarelo; vale conferir os gráficos de resíduos."
            )
        else:
            bp_status = "vermelho"
            bp_text = (
                f"Breusch-Pagan: p = {format_pvalue(bp_p)}. A dispersão dos erros parece "
                "mudar com o valor estimado. Sinal vermelho."
            )
    except Exception:
        bp_lm, bp_p = float("nan"), float("nan")
        bp_status = "amarelo"
        bp_text = "Breusch-Pagan não pôde ser calculado com esta amostra."
    # Multicolinearidade
    high_vif = [name for name, value in fit.vif.items() if math.isfinite(value) and value > 10.0]
    high_corr: list[tuple[str, str, float]] = []
    corr = fit.correlation
    for i, name_i in enumerate(corr.columns):
        for j in range(i + 1, len(corr.columns)):
            name_j = corr.columns[j]
            try:
                value = float(corr.iloc[i, j])
            except Exception:
                continue
            if math.isfinite(value) and abs(value) > 0.80:
                high_corr.append((str(name_i), str(name_j), value))
    if high_vif or high_corr:
        multi_status = "vermelho" if high_vif else "amarelo"
        pieces: list[str] = []
        if high_vif:
            pieces.append("VIF acima de 10 em " + ", ".join(high_vif) + ".")
        if high_corr:
            pieces.append(
                "Pares com |r| > 0,80: "
                + "; ".join(f"{a} × {b} (r = {format_number(r, 2)})" for a, b, r in high_corr)
                + "."
            )
        multi_text = " ".join(pieces)
    else:
        multi_status = "verde"
        multi_text = "Sem VIF acima de 10 e sem pares de X com |r| acima de 0,80. Sinal verde."
    # Durbin-Watson (informativo, nunca vermelho)
    try:
        dw = float(durbin_watson(resid))
    except Exception:
        dw = float("nan")
    if math.isfinite(dw):
        if 1.5 <= dw <= 2.5:
            dw_note = "está próximo de 2, como é comum em dados sem ordem temporal."
        elif dw < 1.5:
            dw_note = "está abaixo de 1,5; pode haver um padrão nos resíduos."
        else:
            dw_note = "está acima de 2,5; pode haver um padrão nos resíduos."
        dw_text = (
            f"Durbin-Watson = {format_number(dw, 2)} — {dw_note} "
            "Este número vale para dados ao longo do tempo. Em avaliação de imóveis ele não decide o grau."
        )
    else:
        dw_text = (
            "Durbin-Watson não pôde ser calculado. Este número vale para dados ao longo do tempo. "
            "Em avaliação de imóveis ele não decide o grau."
        )
    # Tabela
    rows: list[DiagnosticRow] = []
    cooks_threshold = 4.0 / n if n else float("inf")
    z_highlight_count = 0
    for idx, position in enumerate(fit.used_positions):
        observed = float(fit.observed_original[idx])
        estimated = float(fit.fitted_original[idx])
        residual = float(fit.residuals[idx])
        relative = abs(observed - estimated) / abs(observed) * 100.0 if abs(observed) > 0 else float("inf")
        standardized = float(fit.standardized_residuals[idx])
        studentized = float(fit.studentized_residuals[idx])
        cook = float(fit.cooks_distance[idx])
        mahal = float(fit.mahalanobis[idx])
        influential = math.isfinite(cook) and (cook > 4.0 / n or cook > 1.0)
        atypical = math.isfinite(mahal) and mahal > fit.mahalanobis_cutoff
        z_highlight = (math.isfinite(standardized) and abs(standardized) > 2.0) or (
            math.isfinite(studentized) and abs(studentized) > 2.0
        )
        if z_highlight:
            z_highlight_count += 1
        rows.append(DiagnosticRow(
            position=position,
            row_id=fit.used_row_ids[idx],
            label=fit.labels[idx],
            observed=observed,
            estimated=estimated,
            residual=residual,
            relative_pct=relative,
            standardized=standardized,
            studentized=studentized,
            cook=cook,
            mahalanobis=mahal,
            influential=bool(influential),
            atypical=bool(atypical),
            z_highlight=bool(z_highlight),
        ))
    notes: list[str] = []
    if fit.mahalanobis_approximate:
        notes.append(
            "A amostra é pequena para o corte exato pela distribuição Beta. "
            "O corte de Mahalanobis foi aproximado pela qui-quadrado."
        )
    if fit.dropped_positions:
        notes.append(
            f"{len(fit.dropped_positions)} imóvel(is) ligado(s) ficaram fora deste cálculo por vazio em Y ou X."
        )
    return DiagnosticsResult(
        normality_bands=bands,
        normality=Assumption("normalidade", "Normalidade dos resíduos", normality_status, normality_text),
        homocedasticity=Assumption("homocedasticidade", "Dispersão dos resíduos", bp_status, bp_text,
                                   {"lm": bp_lm, "p": bp_p}),
        multicollinearity=Assumption("multicolinearidade", "Variáveis repetidas", multi_status, multi_text,
                                     {"vif": fit.vif, "pairs": high_corr}),
        independence=Assumption("independencia", "Durbin-Watson (informativo)", "cinza", dw_text, {"dw": dw}),
        shapiro_w=shapiro_w,
        shapiro_p=shapiro_p,
        shapiro_text=shapiro_text,
        breusch_pagan_lm=bp_lm,
        breusch_pagan_p=bp_p,
        vif=dict(fit.vif),
        high_vif=high_vif,
        high_correlations=high_corr,
        durbin_watson=dw,
        table=rows,
        cooks_threshold=cooks_threshold,
        cooks_flags=[r.position for r in rows if r.influential],
        mahalanobis_cutoff=fit.mahalanobis_cutoff,
        mahalanobis_flags=[r.position for r in rows if r.atypical],
        mahalanobis_approximate=fit.mahalanobis_approximate,
        notes=notes,
    )
