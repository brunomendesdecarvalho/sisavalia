"""Geração de relatório PDF/DOCX e planilha XLSX."""
from __future__ import annotations

import html
import io
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import charting
from .data_manager import DataManager, transformation_label
from .diagnostics import DiagnosticsResult, compute_diagnostics
from .evaluation import EvaluationResult, report_blockers
from .formatting import format_coefficient, format_date_br, format_number, format_pvalue
from .nbr14653 import NBRResult
from .regression_engine import FitResult

LOGGER = logging.getLogger(__name__)


class ReportError(ValueError):
    """Erro de relatório com mensagem para o usuário."""


@dataclass
class ReportContext:
    title: str
    manager: DataManager
    fit: Optional[FitResult]
    diagnostics: Optional[DiagnosticsResult]
    evaluations: list[EvaluationResult]
    generated_at: str = field(default_factory=lambda: datetime.now().strftime("%d/%m/%Y às %H:%M"))

    def ensure_ready(self) -> None:
        if self.fit is None or self.diagnostics is None:
            raise ReportError("Calcule o modelo antes de exportar. Use o botão Calcular este modelo.")
        blockers = report_blockers(self.evaluations, self.manager)
        if blockers:
            raise ReportError("\n".join(blockers[:5]))
        if not self.evaluations:
            raise ReportError(
                "Inclua pelo menos um imóvel avaliando na aba 4 para o relatório ter uma projeção."
            )


def make_context(title: str, manager: DataManager, fit: Optional[FitResult],
                 evaluations: Sequence[EvaluationResult]) -> ReportContext:
    diagnostics = compute_diagnostics(fit) if fit is not None else None
    return ReportContext(title=title.strip() or "Relatório de avaliação", manager=manager,
                         fit=fit, diagnostics=diagnostics, evaluations=list(evaluations))


def _h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _n(value: Any, decimals: int = 2) -> str:
    return format_number(value, decimals)


def _p(value: Any) -> str:
    return format_pvalue(value)


def _percent(value: Any, decimals: int = 1) -> str:
    return format_number(value, decimals) + "%"


def _table_html(headers: Sequence[str], rows: Sequence[Sequence[Any]], *,
                css_class: str = "data", aligns: Optional[Sequence[str]] = None,
                widths: Optional[Sequence[str]] = None) -> str:
    parts = [f'<table class="{css_class}" width="100%"><thead><tr>']
    for i, h in enumerate(headers):
        width_attr = f' width="{_h(widths[i])}"' if widths and i < len(widths) else ""
        parts.append(f"<th{width_attr}>{_h(h)}</th>")
    parts.append("</tr></thead><tbody>")
    for row in rows:
        parts.append("<tr>")
        for i, cell in enumerate(row):
            align = aligns[i] if aligns and i < len(aligns) else ""
            style = f' style="text-align:{align}"' if align else ""
            parts.append(f"<td{style}>{_h(cell)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def _metadata_rows(manager: DataManager) -> list[tuple[str, str]]:
    meta = manager.metadata
    return [
        ("Autor", str(meta.get("author", "") or "Não informado")),
        ("Responsável técnico", str(meta.get("technical_name", "") or "Não informado")),
        ("CREA/CAU", str(meta.get("technical_registry", "") or "Não informado")),
        ("Solicitante", str(meta.get("requester", "") or "Não informado")),
        ("Trabalho", str(meta.get("work_name", "") or "Sem nome")),
        ("Finalidade", str(meta.get("purpose", "") or "Não informada")),
        ("Objetivo", str(meta.get("objective", "") or "Não informado")),
        ("Data do trabalho", format_date_br(meta.get("date", ""))),
        ("Data de referência", format_date_br(meta.get("reference_date", ""))),
        ("Município", str(meta.get("city", "") or "Não informado")),
        ("Tipologia", str(meta.get("tipologia", "") or "Não informada")),
        ("Identificação / diagnóstico", str(meta.get("description", "") or "—")),
        ("Pressupostos e ressalvas", str(meta.get("assumptions", "") or "—")),
        ("Condições limitantes", str(meta.get("limitations", "") or "—")),
        ("Vistoria", str(meta.get("inspection", "") or "Não informada")),
    ]


def _sample_rows(manager: DataManager, fit: FitResult) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = [
        ("Y", manager.y_column or "—", manager.column_types.get(manager.y_column or "", "—"),
         manager.y_transform, ""),
    ]
    for spec in manager.x_specs(True):
        sign = {1: "Subir", -1: "Descer", 0: "Tanto faz"}.get(int(spec.get("expected_sign", 0)), "Tanto faz")
        rows.append((
            "X", spec["name"], spec.get("type", "—"),
            f"{spec['transformation']} (sinal: {sign})",
            str(spec.get("description", "") or "—"),
        ))
    return rows


def _log_note(manager: DataManager) -> str:
    if manager.y_transform == "ln(x)":
        return (
            "Y está em logaritmo: a estimativa é o exponencial do valor ajustado, "
            "sem correção de retransformação (smearing)."
        )
    return ""


def _assumption_rows(diag: DiagnosticsResult) -> list[tuple[str, str, str]]:
    rows = []
    for item in (diag.normality, diag.homocedasticity, diag.multicollinearity, diag.independence):
        rows.append((item.title, item.status.capitalize(), item.text))
    return rows


def _extrapolation_rows(result: EvaluationResult) -> list[tuple[str, ...]]:
    rows = []
    for row in result.nbr.extrapolation:
        rows.append((
            row.variable,
            _n(row.value, 2),
            f"{_n(row.minimum, 2)} a {_n(row.maximum, 2)}",
            row.situation.capitalize(),
            "Sim" if row.acceptable else "Não",
            _n(row.distance_pct, 1) + "%" if row.distance_pct is not None else "—",
        ))
    return rows


def _nbr_item_rows(nbr: NBRResult) -> list[tuple[str, ...]]:
    rows = []
    for item in nbr.items:
        rows.append((str(item.number), item.title, item.grade_label, str(item.points), item.detail))
    return rows


def _build_images(context: ReportContext, *, summary: bool = False) -> dict[str, bytes]:
    if context.fit is None:
        return {}
    fit = context.fit
    images: dict[str, bytes] = {}
    charting.configure_matplotlib(12)
    fig, _ = charting.fit_scatter(fit.observed_original, fit.fitted_original, fit.labels)
    images["aderencia"] = charting.figure_to_bytes(fig, dpi=220)
    plt.close(fig)
    if summary:
        return images
    fig, _ = charting.residual_fitted(fit.fitted_original, fit.residuals, fit.labels)
    images["residuos_ajustados"] = charting.figure_to_bytes(fig, dpi=220)
    plt.close(fig)
    fig, _ = charting.qq_plot(fit.residuals)
    images["qq"] = charting.figure_to_bytes(fig, dpi=220)
    plt.close(fig)
    fig, _ = charting.histogram(fit.residuals, title="Histograma dos resíduos",
                               xlabel="Resíduo", color=charting.PRIMARY)
    images["hist_residuos"] = charting.figure_to_bytes(fig, dpi=220)
    plt.close(fig)
    fig, _ = charting.stem_plot(fit.cooks_distance, fit.labels, min(4.0 / max(fit.n_obs, 1), 1.0),
                                title="Distância de Cook", ylabel="Cook")
    images["cook"] = charting.figure_to_bytes(fig, dpi=220)
    plt.close(fig)
    fig, _ = charting.stem_plot(fit.mahalanobis, fit.labels, fit.mahalanobis_cutoff,
                                title="Distância de Mahalanobis", ylabel="Mahalanobis")
    images["mahalanobis"] = charting.figure_to_bytes(fig, dpi=220)
    plt.close(fig)
    return images


def _shared_head(context: ReportContext) -> str:
    manager = context.manager
    meta_rows = _metadata_rows(manager)
    sample_parts = [
        f"<p><b>Imóveis na conta:</b> {manager.n_active} &nbsp; "
        f"<b>Desligados:</b> {manager.n_inactive} &nbsp; "
        f"<b>Gerado em:</b> {_h(context.generated_at)}</p>"
    ]
    note = str(manager.metadata.get("sample_note", "") or "")
    if note:
        sample_parts.append(f'<p class="note">{_h(note)}</p>')
    return (
        f'<h1>{_h(context.title)}</h1>'
        '<p class="subtitle">SisAvalia — análise estatística, regressão linear múltipla e engenharia de avaliações</p>'
        + _table_html(["Campo", "Conteúdo"], meta_rows, aligns=["left", "left"])
        + "".join(sample_parts)
    )


def _summary_html(context: ReportContext, images: dict[str, bytes], *, image_width: int = 520,
                  font_pt: float = 9.5) -> str:
    manager = context.manager
    fit = context.fit
    assert fit is not None
    meta = manager.metadata
    meta_line_1 = (
        f"<b>Autor:</b> {_h(meta.get('author', '') or 'Não informado')} &nbsp;•&nbsp; "
        f"<b>Data:</b> {_h(format_date_br(meta.get('date', '')))}"
    )
    meta_line_2 = (
        f"<b>Município:</b> {_h(meta.get('city', '') or 'Não informado')} &nbsp;•&nbsp; "
        f"<b>Tipologia:</b> {_h(meta.get('tipologia', '') or 'Não informada')}"
    )
    eval_rows = []
    for result in context.evaluations:
        eval_rows.append((
            result.name,
            _n(result.prediction.point, 2),
            f"{_n(result.prediction.ci_low, 2)} a {_n(result.prediction.ci_high, 2)}",
            _n(result.adopted, 2),
            result.fundamental_degree,
            result.precision_degree,
        ))
    log_note = _log_note(manager)
    note = f'<p class="note">{_h(log_note)}</p>' if log_note else ""
    image = (f'<div class="chart"><img src="aderencia" width="{image_width}"></div>'
             if "aderencia" in images else "")
    sample_note = str(meta.get("sample_note", "") or "")
    sample_html = f'<p class="note">{_h(sample_note)}</p>' if sample_note else ""
    first = context.evaluations[0] if context.evaluations else None
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    body {{ font-family: 'DejaVu Sans', sans-serif; font-size: {font_pt:.1f}pt; color: #0f172a; }}
    h1 {{ font-size: 16pt; margin: 0 0 1mm 0; color: #1e3a8a; }}
    h2 {{ font-size: 11.5pt; color: #1e3a8a; margin: 3mm 0 1mm 0; border-bottom: 1px solid #cbd5e1; }}
    p {{ margin: 1mm 0; }}
    .subtitle {{ color: #475569; font-size: 8pt; margin-top: 0; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1.5mm 0; }}
    th {{ background: #e2e8f0; text-align: left; padding: 2px 4px; font-size: 8pt; }}
    td {{ border: 1px solid #cbd5e1; padding: 2px 4px; font-size: 8pt; }}
    .note {{ background: #fff7ed; border-left: 3px solid #f59e0b; padding: 1.5mm; font-size: 8pt; }}
    .equation {{ background: #eff6ff; border: 1px solid #bfdbfe; padding: 2mm; font-size: 10pt; }}
    .chart {{ margin: 2mm 0; }}
    .chart img {{ width: {image_width}px; }}
    .small {{ font-size: 8pt; color: #475569; }}
    </style></head><body>
    <h1>{_h(context.title)}</h1>
    <p class="subtitle">SisAvalia — análise estatística, regressão linear múltipla e engenharia de avaliações</p>
    <p class="small">{meta_line_1}</p>
    <p class="small">{meta_line_2}</p>
    <p class="small"><b>Imóveis na conta:</b> {manager.n_active} &nbsp; <b>Desligados:</b> {manager.n_inactive} &nbsp; <b>Gerado em:</b> {_h(context.generated_at)}</p>
    {sample_html}
    <h2>Equação</h2><div class="equation">{_h(fit.equation)}</div>
    <p class="small"><b>Na escala original de Y:</b> {_h(fit.equation_original)}</p>
    <p><b>R²:</b> {_n(fit.rsquared, 4)} &nbsp; <b>R² ajustado:</b> {_n(fit.rsquared_adj, 4)} &nbsp;
    <b>Erro padrão:</b> {_n(fit.scale, 4)}</p>
    <h2>Resultado da avaliação</h2>
    {_table_html(["Avaliando", "Estimativa", "IC 80%", "Adotado", "Fund.", "Precisão"], eval_rows, aligns=["left", "right", "center", "right", "center", "center"], widths=["180px", "110px", "175px", "105px", "80px", "90px"])}
    <p><b>Grau de fundamentação:</b> {_h(first.fundamental_degree) if first else '—'} &nbsp;
    <b>Grau de precisão:</b> {_h(first.precision_degree) if first else '—'}</p>
    {note}
    <h2>Aderência</h2>{image}
    <p class="small">A sugestão de equação não substitui o julgamento do avaliador. Confira os dados antes de usar em laudo.</p>
    </body></html>"""


def _full_html(context: ReportContext, images: dict[str, bytes]) -> str:
    manager = context.manager
    meta = manager.metadata
    fit = context.fit
    diag = context.diagnostics
    assert fit is not None and diag is not None
    equation = _h(fit.equation)
    equation_original = _h(fit.equation_original)
    log_note = _log_note(manager)
    note_html = f'<p class="note">{_h(log_note)}</p>' if log_note else ""
    sample_rows = _sample_rows(manager, fit)
    sample_table = _table_html(
        ["Papel", "Variável", "Tipo", "Transformação / sinal", "Descrição / critério"],
        sample_rows, aligns=["center", "left", "left", "left", "left"],
    )
    anova_rows = [(
        row["Fonte"], _n(row["SQ"], 4), str(row["GL"]), _n(row["QM"], 4),
        _n(row["F"], 3), _p(row["p-valor"]),
    ) for row in fit.anova_rows]
    anova_table = _table_html(["Fonte", "SQ", "GL", "QM", "F", "p-valor"], anova_rows,
                              aligns=["left", "right", "center", "right", "right", "right"])
    coeff_rows = []
    for name in ["const"] + fit.design_names:
        display = "Intercepto" if name == "const" else name
        coeff_rows.append((display, format_coefficient(fit.params[name]), _n(fit.bse[name], 4),
                           _n(fit.tvalues[name], 3), _p(fit.pvalues[name])))
    coeff_table = _table_html(["Variável", "Estimativa", "Erro padrão", "t", "p-valor"], coeff_rows,
                              aligns=["left", "right", "right", "right", "right"])
    eval_html: list[str] = []
    for idx, result in enumerate(context.evaluations, start=1):
        values_rows = [(name, _n(value, 4)) for name, value in result.values.items()]
        proj_rows = [
            ("Estimativa pontual", _n(result.prediction.point, 2)),
            ("IC 80% da média", f"{_n(result.prediction.ci_low, 2)} a {_n(result.prediction.ci_high, 2)}"),
            ("IP 80% (preço)", f"{_n(result.prediction.pi_low, 2)} a {_n(result.prediction.pi_high, 2)}"),
            ("Amplitude do IC", _percent(result.prediction.amplitude_pct, 1)),
            ("Grau de precisão", result.prediction.precision_degree),
            ("Intervalo usado no valor adotado", result.interval_label),
            ("Intervalo admissível (IC/IP ∩ arbítrio)",
             f"{_n(result.display_admissible_low, 2)} a {_n(result.display_admissible_high, 2)}"),
            ("Campo de arbítrio (±15%)",
             f"{_n(result.arbitrio_low, 2)} a {_n(result.arbitrio_high, 2)}"),
            ("Valor adotado", _n(result.adopted, 2)),
            ("Justificativa", result.justification or "Não informada"),
        ]
        nbr_rows = _nbr_item_rows(result.nbr)
        nbr_table = _table_html(["Item", "O que verifica", "Grau", "Pontos", "Explicação"], nbr_rows,
                                aligns=["center", "left", "center", "center", "left"])
        elast_rows = []
        try:
            for row in fit.elasticity_rows(result.values):
                elast_rows.append((row.get("display", ""), row.get("kind", ""), row.get("text", "")))
        except Exception:
            elast_rows = []
        elasticity_table = _table_html(
            ["Variável", "Tipo", "Elasticidade / efeito no ponto"],
            elast_rows, aligns=["left", "center", "left"],
        ) if elast_rows else "<p>Não foi possível calcular as elasticidades.</p>"
        extra_rows = _extrapolation_rows(result)
        extra_table = _table_html(
            ["Variável", "Avaliando", "Amostra ativa", "Situação", "Aceitável?", "Afastamento"],
            extra_rows, aligns=["left", "right", "center", "center", "center", "right"],
        )
        extra_rules = " ".join(
            f"{row.variable}: {row.limit_text}; estimativa na fronteira "
            f"{_n(row.estimate_pulled, 2) if row.estimate_pulled is not None else '—'}"
            + (f"; afastamento {_n(row.distance_pct, 1)}%." if row.distance_pct is not None else ".")
            for row in result.nbr.extrapolation if row.situation != "dentro"
        )
        if not extra_rules:
            extra_rules = "Nenhuma variável fora da faixa da amostra ativa."
        cap = ""
        if result.nbr.cap_explanation:
            cap = f'<p class="warning">{_h(result.nbr.cap_explanation)}</p>'
        eval_html.append(f"""
        <div class="section">
        <h2>Avaliando {idx}: {_h(result.name)}</h2>
        {_table_html(["Variável", "Valor informado"], values_rows, aligns=["left", "right"])}
        {_table_html(["Resultado", "Valor"], proj_rows, aligns=["left", "right"])}
        <p><b>Grau de fundamentação:</b> {_h(result.nbr.final_degree)} &nbsp;
        <b>Pontuação:</b> {result.nbr.total_points} &nbsp;
        <b>Grau de precisão:</b> {_h(result.nbr.precision_degree)}</p>
        {cap}
        <h3>Fundamentação</h3>{nbr_table}
        <h3>Elasticidades no ponto de estimação</h3>{elasticity_table}
        <h3>Extrapolação por variável</h3>{extra_table}
        <p class="small">{_h(extra_rules)}</p>
        </div>""")
    assumptions = _table_html(["Premissa", "Semáforo", "O que os números dizem"],
                              [(a[0], a[1], a[2]) for a in _assumption_rows(diag)],
                              aligns=["left", "center", "left"])
    vif_rows = [(name, _n(value, 3) if math.isfinite(value) else "muito alto") for name, value in diag.vif.items()]
    corr_pairs = [(a, b, _n(r, 3)) for a, b, r in diag.high_correlations] or [("Nenhum par acima de 0,80", "—", "—")]
    residual_values = []
    residual_influence = []
    for row in diag.table:
        residual_values.append((
            row.label, _n(row.observed, 2), _n(row.estimated, 2), _n(row.residual, 2),
            _percent(row.relative_pct, 1),
        ))
        residual_influence.append((
            row.label, _n(row.standardized, 3), _n(row.studentized, 3),
            _n(row.cook, 4), _n(row.mahalanobis, 3),
        ))
    residual_table = (
        "<h3>Valores observados, estimados e resíduos</h3>"
        + _table_html(["Imóvel", "Observado", "Estimado", "Resíduo", "Relativo"],
                      residual_values, aligns=["left", "right", "right", "right", "right"],
                      widths=["250px", "135px", "135px", "120px", "110px"], css_class="data small")
        + '<div style="page-break-before: always;"></div>'
        + "<h3>Padronizado, studentizado, Cook e Mahalanobis</h3>"
        + _table_html(["Imóvel", "Padronizado", "Studentizado", "Cook", "Mahalanobis"],
                      residual_influence, aligns=["left", "right", "right", "right", "right"],
                      widths=["240px", "145px", "145px", "110px", "130px"], css_class="data small")
    )
    image_html = "".join(
        f'<div class="chart"><img src="{name}" width="480"></div>'
        for name in ("aderencia", "residuos_ajustados", "qq", "hist_residuos", "cook", "mahalanobis")
        if name in images
    )
    shapiro = _h(diag.shapiro_text)
    dw = _h(diag.independence.text)
    multi = _h(diag.multicollinearity.text)
    text_about_suggestion = (
        "A sugestão de equação não substitui o seu julgamento. "
        "Confira os dados e o enquadramento antes de usar em laudo."
    )
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    body {{ font-family: 'DejaVu Sans', sans-serif; font-size: 10pt; color: #0f172a; }}
    h1 {{ font-size: 19pt; margin: 0 0 2mm 0; color: #1e3a8a; }}
    h2 {{ font-size: 13pt; margin: 6mm 0 2mm 0; color: #1e3a8a; border-bottom: 1px solid #cbd5e1; }}
    h3 {{ font-size: 11pt; margin: 4mm 0 1.5mm 0; color: #334155; }}
    .subtitle {{ color: #475569; font-size: 9pt; margin-top: 0; }}
    table {{ border-collapse: collapse; width: 100%; margin: 2mm 0 3mm 0; }}
    th {{ background: #e2e8f0; text-align: left; padding: 2px 4px; font-size: 9pt; }}
    td {{ border: 1px solid #cbd5e1; padding: 2px 4px; font-size: 9pt; vertical-align: top; }}
    table.small td, table.small th {{ font-size: 8pt; }}
    .note {{ background: #fff7ed; border-left: 3px solid #f59e0b; padding: 2mm; }}
    .warning {{ background: #fef2f2; border-left: 3px solid #dc2626; padding: 2mm; }}
    .equation {{ background: #eff6ff; border: 1px solid #bfdbfe; padding: 3mm; font-size: 11pt; }}
    .chart {{ margin: 4mm 0; page-break-inside: avoid; }}
    .chart img {{ width: 90%; }}
    .section {{ page-break-inside: auto; }}
    .kpi {{ background: #f0fdf4; border: 1px solid #bbf7d0; padding: 3mm; font-size: 11pt; }}
    </style></head><body>
    {_shared_head(context)}
    <h2>1. Amostra e variáveis</h2>
    <p><b>Imóveis na conta:</b> {manager.n_active} &nbsp; <b>Desligados:</b> {manager.n_inactive} &nbsp;
    <b>Usados no modelo:</b> {fit.n_obs} &nbsp; <b>Fora por vazio:</b> {len(fit.dropped_positions)}</p>
    {sample_table}
    <h2>2. Equação ajustada</h2>
    <p><b>Forma estimada (Y transformado):</b></p>
    <div class="equation">{equation}</div>
    <p><b>Forma não transformada da variável dependente (para o laudo):</b></p>
    <div class="equation">{equation_original}</div>
    <p><b>R²:</b> {_n(fit.rsquared, 4)} &nbsp; <b>R² ajustado:</b> {_n(fit.rsquared_adj, 4)} &nbsp;
    <b>Erro padrão dos resíduos:</b> {_n(fit.scale, 4)}</p>
    {note_html}
    <h2>3. ANOVA</h2>{anova_table}
    <h2>4. Coeficientes</h2>{coeff_table}
    <p class="subtitle">O teste t dos itens de fundamentação usa somente os regressores, nunca o intercepto.</p>
    <h2>5. Projeções dos avaliandos</h2>
    {''.join(eval_html) if eval_html else '<p>Nenhum avaliando foi incluído.</p>'}
    <h2>6. Diagnóstico das premissas</h2>
    {assumptions}
    <p>{shapiro}</p>
    <p>{dw}</p>
    <p>{multi}</p>
    <h3>VIF</h3>{_table_html(["Variável", "VIF"], vif_rows, aligns=["left", "right"])}
    <h3>Pares de X com correlação alta</h3>{_table_html(["Variável A", "Variável B", "r"], corr_pairs, aligns=["left", "left", "right"])}
    <div style="page-break-before: always;"></div>
    <h2>7. Tabela de resíduos</h2>{residual_table}
    <div style="page-break-before: always;"></div>
    <h2>8. Gráficos</h2>{image_html}
    <p class="note">{_h(text_about_suggestion)}</p>
    <h2>9. Responsável técnico</h2>
    <p><b>Nome:</b> {_h(meta.get('technical_name', '') or 'Não informado')} &nbsp;
    <b>CREA/CAU:</b> {_h(meta.get('technical_registry', '') or 'Não informado')}</p>
    <p><b>{_h(meta.get('signature_city', '') or meta.get('city', '') or 'Local')}</b>,
    {_h(format_date_br(meta.get('reference_date', '') or meta.get('date', '')))}</p>
    <p>__________________________________________________________<br/>Assinatura do responsável técnico</p>
    <p class="subtitle">Relatório gerado pelo SisAvalia em {_h(context.generated_at)}.</p>
    </body></html>"""


def _register_images_pdf(doc: Any, images: dict[str, bytes]) -> None:
    from PySide6.QtGui import QImage, QTextDocument
    from PySide6.QtCore import QUrl
    for name, data in images.items():
        image = QImage()
        if image.loadFromData(data, "PNG"):
            doc.addResource(QTextDocument.ImageResource, QUrl(name), image)


def generate_pdf(context: ReportContext, path: str | Path, *, summary: bool = False) -> Path:
    context.ensure_ready()
    target = Path(path)
    images = _build_images(context, summary=summary)
    html_text = _summary_html(context, images) if summary else _full_html(context, images)
    try:
        from PySide6.QtCore import QMarginsF, QSizeF, QUrl
        from PySide6.QtGui import QImage, QPageLayout, QPageSize, QTextDocument
        from PySide6.QtPrintSupport import QPrinter
        from PySide6.QtWidgets import QApplication
    except Exception as exc:
        raise ReportError("Os componentes de PDF não estão disponíveis nesta instalação.") from exc
    app = QApplication.instance()
    if app is None:
        raise ReportError(
            "O PDF precisa do aplicativo aberto. Abra o SisAvalia e exporte novamente."
        )
    try:
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        _register_images_pdf(doc, images)
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(target))
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setPageOrientation(QPageLayout.Orientation.Portrait)
        printer.setPageMargins(QMarginsF(14, 14, 14, 14), QPageLayout.Unit.Millimeter)
        page_size = printer.pageRect(QPrinter.Unit.Point).size()
        if summary:
            for width, font_pt in ((580, 10.5), (540, 10.0), (500, 9.5), (460, 9.0), (420, 8.5)):
                html_summary = _summary_html(context, images, image_width=width, font_pt=font_pt)
                doc.setHtml(html_summary)
                doc.setPageSize(QSizeF(page_size))
                if doc.pageCount() <= 1:
                    break
        else:
            doc.setHtml(html_text)
            doc.setPageSize(QSizeF(page_size))
        if hasattr(doc, "print_"):
            doc.print_(printer)
        else:
            doc.print(printer)
    except Exception as exc:
        raise ReportError("Não foi possível gravar o PDF. Confira a pasta escolhida.") from exc
    if not target.exists() or target.stat().st_size == 0:
        raise ReportError("O PDF não foi gerado. Confira a pasta escolhida e tente de novo.")
    return target


def _set_cell_shading(cell: Any, color: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tcPr.append(shd)


def _docx_table(doc: Document, headers: Sequence[str], rows: Sequence[Sequence[Any]],
                widths: Optional[Sequence[float]] = None) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = table.rows[0].cells
    for i, text in enumerate(headers):
        hdr[i].text = str(text)
        _set_cell_shading(hdr[i], "E2E8F0")
        for p in hdr[i].paragraphs:
            for run in p.runs:
                run.bold = True
                run.font.size = Pt(9)
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = "" if value is None else str(value)
            for p in cells[i].paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9)
    if widths:
        for row in table.rows:
            for i, width in enumerate(widths):
                if i < len(row.cells):
                    row.cells[i].width = Cm(width)
    doc.add_paragraph()


def _docx_add_image(doc: Document, data: bytes, width_cm: float = 16.0) -> None:
    try:
        doc.add_picture(io.BytesIO(data), width=Cm(width_cm))
        last = doc.paragraphs[-1]
        last.alignment = WD_ALIGN_PARAGRAPH.CENTER
    except Exception as exc:
        LOGGER.warning("Figura não incluída no DOCX: %s", exc)


def generate_docx(context: ReportContext, path: str | Path, *, summary: bool = False) -> Path:
    context.ensure_ready()
    target = Path(path)
    images = _build_images(context, summary=summary)
    try:
        doc = Document()
        section = doc.sections[0]
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(1.6)
        section.bottom_margin = Cm(1.6)
        section.left_margin = Cm(1.8)
        section.right_margin = Cm(1.8)
        normal = doc.styles["Normal"]
        normal.font.name = "DejaVu Sans"
        normal.font.size = Pt(10)
        normal.paragraph_format.space_after = Pt(4)
        title = doc.add_heading(context.title, level=0)
        for run in title.runs:
            run.font.color.rgb = RGBColor(30, 58, 138)
        sub = doc.add_paragraph("SisAvalia — análise estatística, regressão linear múltipla e engenharia de avaliações")
        sub.runs[0].font.size = Pt(9)
        sub.runs[0].font.color.rgb = RGBColor(71, 85, 105)
        fit = context.fit
        diag = context.diagnostics
        assert fit is not None and diag is not None
        if summary:
            meta = context.manager.metadata
            compact = doc.add_paragraph(
                f"Autor: {meta.get('author', '') or 'Não informado'}    "
                f"Data: {format_date_br(meta.get('date', ''))}    "
                f"Município: {meta.get('city', '') or 'Não informado'}    "
                f"Tipologia: {meta.get('tipologia', '') or 'Não informada'}"
            )
            for run in compact.runs:
                run.font.size = Pt(8.5)
            doc.add_paragraph(
                f"Imóveis na conta: {context.manager.n_active}    Desligados: {context.manager.n_inactive}    "
                f"Gerado em {context.generated_at}"
            )
            note = str(context.manager.metadata.get("sample_note", "") or "")
            if note:
                p = doc.add_paragraph(note)
                p.runs[0].bold = True
                p.runs[0].font.size = Pt(8.5)
            doc.add_heading("Equação", level=1)
            p = doc.add_paragraph(fit.equation)
            for run in p.runs:
                run.font.size = Pt(9.5)
            p = doc.add_paragraph("Na escala original de Y: " + fit.equation_original)
            for run in p.runs:
                run.font.size = Pt(9)
            small = doc.add_paragraph(
                f"R²: {_n(fit.rsquared, 4)}    R² ajustado: {_n(fit.rsquared_adj, 4)}    "
                f"Erro padrão: {_n(fit.scale, 4)}"
            )
            for run in small.runs:
                run.font.size = Pt(9)
            rows = []
            for r in context.evaluations:
                rows.append((r.name, _n(r.prediction.point, 2),
                             f"{_n(r.prediction.ci_low, 2)} a {_n(r.prediction.ci_high, 2)}",
                             _n(r.adopted, 2), r.fundamental_degree, r.precision_degree))
            _docx_table(doc, ["Avaliando", "Estimativa", "IC 80%", "Adotado", "Fundamentação", "Precisão"], rows,
                        widths=[3.2, 2.8, 3.8, 2.8, 2.2, 1.8])
            if context.evaluations:
                doc.add_paragraph(
                    f"Grau de fundamentação: {context.evaluations[0].fundamental_degree}    "
                    f"Grau de precisão: {context.evaluations[0].precision_degree}"
                )
            log_note = _log_note(context.manager)
            if log_note:
                lp = doc.add_paragraph(log_note)
                for run in lp.runs:
                    run.font.size = Pt(8.5)
            if "aderencia" in images:
                _docx_add_image(doc, images["aderencia"], 12.0)
            dp = doc.add_paragraph(
                "A sugestão de equação não substitui o julgamento do avaliador. Confira os dados antes de usar em laudo."
            )
            for run in dp.runs:
                run.font.size = Pt(8.5)
            try:
                doc.save(str(target))
            except Exception as exc:
                raise ReportError("Não foi possível gravar o arquivo DOCX. Confira a pasta escolhida.") from exc
            return target
        doc.add_paragraph(f"Gerado em {context.generated_at}")
        doc.add_heading("Metadados do trabalho", level=1)
        _docx_table(doc, ["Campo", "Conteúdo"], _metadata_rows(context.manager), widths=[4.5, 12.5])
        note = str(context.manager.metadata.get("sample_note", "") or "")
        if note:
            p = doc.add_paragraph(note)
            p.runs[0].bold = True
        doc.add_heading("1. Amostra e variáveis", level=1)
        doc.add_paragraph(
            f"Imóveis na conta: {context.manager.n_active}    Desligados: {context.manager.n_inactive}    "
            f"Usados no modelo: {fit.n_obs}    Fora por vazio: {len(fit.dropped_positions)}"
        )
        _docx_table(
            doc,
            ["Papel", "Variável", "Tipo", "Transformação / sinal", "Descrição / critério"],
            _sample_rows(context.manager, fit),
            widths=[1.3, 3.3, 3.0, 4.2, 4.8],
        )
        doc.add_heading("2. Equação ajustada", level=1)
        doc.add_paragraph("Forma estimada (Y transformado):")
        p = doc.add_paragraph(fit.equation)
        for run in p.runs:
            run.font.size = Pt(10)
        doc.add_paragraph("Forma não transformada da variável dependente (para o laudo):")
        p = doc.add_paragraph(fit.equation_original)
        for run in p.runs:
            run.font.size = Pt(10)
        doc.add_paragraph(
            f"R²: {_n(fit.rsquared, 4)}    R² ajustado: {_n(fit.rsquared_adj, 4)}    "
            f"Erro padrão dos resíduos: {_n(fit.scale, 4)}"
        )
        if _log_note(context.manager):
            doc.add_paragraph(_log_note(context.manager))
        doc.add_heading("3. ANOVA", level=1)
        _docx_table(doc, ["Fonte", "SQ", "GL", "QM", "F", "p-valor"],
                    [(r["Fonte"], _n(r["SQ"], 4), str(r["GL"]), _n(r["QM"], 4),
                      _n(r["F"], 3), _p(r["p-valor"])) for r in fit.anova_rows],
                    widths=[3.0, 3.0, 2.0, 3.0, 2.5, 3.0])
        doc.add_heading("4. Coeficientes", level=1)
        coeff_rows = []
        for name in ["const"] + fit.design_names:
            display = "Intercepto" if name == "const" else name
            coeff_rows.append((display, format_coefficient(fit.params[name]), _n(fit.bse[name], 4),
                               _n(fit.tvalues[name], 3), _p(fit.pvalues[name])))
        _docx_table(doc, ["Variável", "Estimativa", "Erro padrão", "t", "p-valor"], coeff_rows,
                    widths=[5.5, 3.2, 3.2, 2.5, 3.0])
        doc.add_paragraph("O teste t dos itens de fundamentação usa somente os regressores, nunca o intercepto.")
        doc.add_heading("5. Projeções dos avaliandos", level=1)
        for idx, result in enumerate(context.evaluations, start=1):
            doc.add_heading(f"Avaliando {idx}: {result.name}", level=2)
            _docx_table(doc, ["Variável", "Valor informado"],
                        [(name, _n(value, 4)) for name, value in result.values.items()],
                        widths=[8.0, 8.0])
            proj_rows = [
                ("Estimativa pontual", _n(result.prediction.point, 2)),
                ("IC 80% da média", f"{_n(result.prediction.ci_low, 2)} a {_n(result.prediction.ci_high, 2)}"),
                ("IP 80% (preço)", f"{_n(result.prediction.pi_low, 2)} a {_n(result.prediction.pi_high, 2)}"),
                ("Amplitude do IC", _percent(result.prediction.amplitude_pct, 1)),
                ("Grau de precisão", result.prediction.precision_degree),
                ("Intervalo usado no valor adotado", result.interval_label),
                ("Intervalo admissível (IC/IP ∩ arbítrio)",
                 f"{_n(result.display_admissible_low, 2)} a {_n(result.display_admissible_high, 2)}"),
                ("Campo de arbítrio (±15%)",
                 f"{_n(result.arbitrio_low, 2)} a {_n(result.arbitrio_high, 2)}"),
                ("Valor adotado", _n(result.adopted, 2)),
                ("Justificativa", result.justification or "Não informada"),
            ]
            _docx_table(doc, ["Resultado", "Valor"], proj_rows, widths=[8.0, 8.0])
            doc.add_paragraph(
                f"Grau de fundamentação: {result.nbr.final_degree}    Pontuação: {result.nbr.total_points}    "
                f"Grau de precisão: {result.nbr.precision_degree}"
            )
            if result.nbr.cap_explanation:
                doc.add_paragraph(result.nbr.cap_explanation)
            _docx_table(doc, ["Item", "O que verifica", "Grau", "Pontos", "Explicação"],
                        _nbr_item_rows(result.nbr), widths=[1.2, 3.6, 1.5, 1.4, 8.3])
            try:
                elast = [(r.get("display", ""), r.get("kind", ""), r.get("text", ""))
                         for r in fit.elasticity_rows(result.values)]
            except Exception:
                elast = []
            if elast:
                doc.add_heading("Elasticidades no ponto", level=2)
                _docx_table(doc, ["Variável", "Tipo", "Elasticidade / efeito"],
                            elast, widths=[4.0, 3.0, 9.0])
            _docx_table(doc, ["Variável", "Avaliando", "Amostra ativa", "Situação", "Aceitável?", "Afastamento"],
                        _extrapolation_rows(result), widths=[3.2, 2.2, 3.4, 2.0, 2.0, 3.2])
            rules = " ".join(
                f"{r.variable}: {r.limit_text}; estimativa na fronteira "
                f"{_n(r.estimate_pulled, 2) if r.estimate_pulled is not None else '—'}"
                + (f"; afastamento {_n(r.distance_pct, 1)}%." if r.distance_pct is not None else ".")
                for r in result.nbr.extrapolation if r.situation != "dentro"
            )
            if rules:
                doc.add_paragraph(rules)
        doc.add_heading("6. Diagnóstico das premissas", level=1)
        _docx_table(doc, ["Premissa", "Semáforo", "O que os números dizem"], _assumption_rows(diag),
                    widths=[3.5, 2.0, 10.5])
        doc.add_paragraph(diag.shapiro_text)
        doc.add_paragraph(diag.independence.text)
        doc.add_paragraph(diag.multicollinearity.text)
        _docx_table(doc, ["Variável", "VIF"],
                    [(name, _n(value, 3) if math.isfinite(value) else "muito alto") for name, value in diag.vif.items()],
                    widths=[8.0, 8.0])
        corr_pairs = [(a, b, _n(r, 3)) for a, b, r in diag.high_correlations] or [("Nenhum par acima de 0,80", "—", "—")]
        _docx_table(doc, ["Variável A", "Variável B", "r"], corr_pairs, widths=[6.0, 6.0, 4.0])
        doc.add_page_break()
        doc.add_heading("7. Tabela de resíduos", level=1)
        residual_values = []
        residual_influence = []
        for row in diag.table:
            residual_values.append((
                row.label, _n(row.observed, 2), _n(row.estimated, 2), _n(row.residual, 2),
                _percent(row.relative_pct, 1),
            ))
            residual_influence.append((
                row.label, _n(row.standardized, 3), _n(row.studentized, 3),
                _n(row.cook, 4), _n(row.mahalanobis, 3),
            ))
        doc.add_heading("Valores observados, estimados e resíduos", level=2)
        _docx_table(doc, ["Imóvel", "Observado", "Estimado", "Resíduo", "Relativo"],
                    residual_values, widths=[5.2, 3.2, 3.2, 3.2, 2.6])
        doc.add_page_break()
        doc.add_heading("Padronizado, studentizado, Cook e Mahalanobis", level=2)
        _docx_table(doc, ["Imóvel", "Padronizado", "Studentizado", "Cook", "Mahalanobis"],
                    residual_influence, widths=[5.2, 3.2, 3.2, 3.2, 2.6])
        doc.add_page_break()
        doc.add_heading("8. Gráficos", level=1)
        for name, caption in (
            ("aderencia", "Aderência: observado × estimado"),
            ("residuos_ajustados", "Resíduos × valores ajustados"),
            ("qq", "Q-Q dos resíduos"),
            ("hist_residuos", "Histograma dos resíduos"),
            ("cook", "Distância de Cook"),
            ("mahalanobis", "Distância de Mahalanobis"),
        ):
            if name in images:
                doc.add_paragraph(caption)
                _docx_add_image(doc, images[name], 16.0)
        doc.add_paragraph(
            "A sugestão de equação não substitui o julgamento do avaliador. Confira os dados antes de usar em laudo."
        )
        doc.add_page_break()
        doc.add_heading("9. Responsável técnico", level=1)
        meta = context.manager.metadata
        doc.add_paragraph(
            f"Nome: {meta.get('technical_name', '') or 'Não informado'}    "
            f"CREA/CAU: {meta.get('technical_registry', '') or 'Não informado'}"
        )
        doc.add_paragraph(
            f"{meta.get('signature_city', '') or meta.get('city', '') or 'Local'}, "
            f"{format_date_br(meta.get('reference_date', '') or meta.get('date', ''))}"
        )
        doc.add_paragraph("__________________________________________________________")
        doc.add_paragraph("Assinatura do responsável técnico")
        try:
            doc.save(str(target))
        except Exception as exc:
            raise ReportError("Não foi possível gravar o arquivo DOCX. Confira a pasta escolhida.") from exc
    except ReportError:
        raise
    except Exception as exc:
        raise ReportError("Não foi possível montar o relatório. Confira os dados e tente de novo.") from exc
    return target


def generate_report(context: ReportContext, path: str | Path, fmt: str, *, summary: bool = False) -> Path:
    fmt = fmt.lower().strip()
    if fmt == "pdf":
        return generate_pdf(context, path, summary=summary)
    if fmt in ("docx", "doc"):
        return generate_docx(context, path, summary=summary)
    raise ReportError("Escolha o formato PDF ou DOCX.")


def _style_worksheet(ws: Any, freeze: str = "A2") -> None:
    ws.freeze_panes = freeze
    header_fill = PatternFill("solid", fgColor="1E3A8A")
    header_font = Font(color="FFFFFF", bold=True)
    thin = Side(style="thin", color="CBD5E1")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = Border(bottom=thin)
    for column in ws.columns:
        letter = get_column_letter(column[0].column)
        max_len = max((len(str(c.value)) if c.value is not None else 0) for c in column)
        ws.column_dimensions[letter].width = min(max(11, max_len + 2), 38)
    ws.auto_filter.ref = ws.dimensions


def export_spreadsheet(manager: DataManager, fit: Optional[FitResult],
                       diagnostics: Optional[DiagnosticsResult],
                       evaluations: Sequence[EvaluationResult], path: str | Path) -> Path:
    target = Path(path)
    if target.suffix.lower() != ".xlsx":
        target = target.with_suffix(".xlsx")
    frame = manager.df.copy()
    output = pd.DataFrame()
    output["Ativo"] = ["Sim" if active else "Não" for active in manager.active]
    output["Rótulo"] = [manager.label_for_row(i) for i in range(len(frame))]
    for col in frame.columns:
        output[col] = frame[col].tolist()
    est = np.full(len(frame), np.nan)
    residual = np.full(len(frame), np.nan)
    relative = np.full(len(frame), np.nan)
    cook = np.full(len(frame), np.nan)
    mahal = np.full(len(frame), np.nan)
    if fit is not None:
        for idx, position in enumerate(fit.used_positions):
            if 0 <= position < len(frame):
                est[position] = fit.fitted_original[idx]
                residual[position] = fit.observed_original[idx] - fit.fitted_original[idx]
                if abs(fit.observed_original[idx]) > 0:
                    relative[position] = abs(fit.observed_original[idx] - fit.fitted_original[idx]) / abs(fit.observed_original[idx]) * 100
                cook[position] = fit.cooks_distance[idx]
                mahal[position] = fit.mahalanobis[idx]
    output["Estimado"] = est
    output["Residuo"] = residual
    output["Residuo_relativo_%"] = relative
    output["Cook"] = cook
    output["Mahalanobis"] = mahal
    # Se existir coluna Cluster, ela já veio entre os dados originais; não duplica.
    eval_rows: list[dict[str, Any]] = []
    x_names = [s["name"] for s in manager.x_specs(True)]
    for result in evaluations:
        row = {"Nome": result.name}
        for name in x_names:
            row[name] = result.values.get(name)
        row.update({
            "Estimativa": result.prediction.point,
            "IC80_inferior": result.prediction.ci_low,
            "IC80_superior": result.prediction.ci_high,
            "Amplitude_%": result.prediction.amplitude_pct,
            "Grau_precisao": result.prediction.precision_degree,
            "Predicao_inferior": result.prediction.pi_low,
            "Predicao_superior": result.prediction.pi_high,
            "Arbitrio_inferior": result.arbitrio_low,
            "Arbitrio_superior": result.arbitrio_high,
            "Valor_adotado": result.adopted,
            "Justificativa": result.justification,
            "Grau_fundamentacao": result.nbr.final_degree,
            "Pontuacao": result.nbr.total_points,
        })
        eval_rows.append(row)
    for result in manager.evaluated:
        if not any(r.item.get("id") == result.get("id") for r in evaluations):
            row = {"Nome": result.get("name", "Avaliando")}
            for name in x_names:
                row[name] = result.get("values", {}).get(name)
            eval_rows.append(row)
    eval_frame = pd.DataFrame(eval_rows)
    meta_frame = pd.DataFrame([
        ("Autor", manager.metadata.get("author", "")),
        ("Trabalho", manager.metadata.get("work_name", "")),
        ("Data", manager.metadata.get("date", "")),
        ("Município", manager.metadata.get("city", "")),
        ("Tipologia", manager.metadata.get("tipologia", "")),
        ("Descrição", manager.metadata.get("description", "")),
        ("Observação da amostra", manager.metadata.get("sample_note", "")),
        ("Gerado em", datetime.now().strftime("%d/%m/%Y %H:%M")),
    ], columns=["Campo", "Conteúdo"])
    try:
        with pd.ExcelWriter(target, engine="openpyxl") as writer:
            output.to_excel(writer, sheet_name="Dados", index=False)
            _style_worksheet(writer.sheets["Dados"])
            eval_frame.to_excel(writer, sheet_name="Avaliandos", index=False)
            _style_worksheet(writer.sheets["Avaliandos"])
            meta_frame.to_excel(writer, sheet_name="Metadados", index=False)
            _style_worksheet(writer.sheets["Metadados"])
            ws = writer.sheets["Dados"]
            numeric_cols = {"Estimado", "Residuo", "Residuo_relativo_%", "Cook", "Mahalanobis"}
            for header in output.columns:
                if header in numeric_cols:
                    col_idx = list(output.columns).index(header) + 1
                    for cell in ws[get_column_letter(col_idx)][1:]:
                        cell.number_format = "#,##0.0000"
    except Exception as exc:
        raise ReportError("Não foi possível gravar a planilha. Confira a pasta escolhida.") from exc
    if not target.exists() or target.stat().st_size == 0:
        raise ReportError("A planilha não foi gerada. Confira a pasta escolhida.")
    return target
