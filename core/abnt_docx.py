"""Geração do laudo DOCX completo no esqueleto da NBR 14653-2, seção 10.1."""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .formatting import format_coefficient, format_date_br, format_number
from .report_generator import (
    ReportContext, ReportError, _assumption_rows, _docx_add_image, _docx_table,
    _extrapolation_rows, _n, _nbr_item_rows, _p, _percent, _sample_rows,
)


def _or(value: Any, fallback: str = "Não informado. Preencher no laudo.") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _heading(doc: Document, text: str, level: int = 1) -> None:
    heading = doc.add_heading(text, level=level)
    heading.paragraph_format.first_line_indent = Cm(0)
    heading.paragraph_format.keep_with_next = True


def _page_number(section: Any) -> None:
    header = section.header
    header.is_linked_to_previous = False
    paragraph = header.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)
    run.font.name = "Arial"
    run.font.size = Pt(9)


def write_abnt_docx(doc: Document, context: ReportContext, target: Path,
                    images: dict[str, bytes]) -> Path:
    # Remove o título/subtítulo provisórios criados por generate_docx.
    for paragraph in list(doc.paragraphs):
        element = paragraph._element
        if element.getparent() is not None:
            element.getparent().remove(element)
    manager = context.manager
    fit = context.fit
    diag = context.diagnostics
    assert fit is not None and diag is not None
    meta = manager.metadata
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(2.0)
    section.different_first_page_header_footer = True
    _page_number(section)

    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(12)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.first_line_indent = Cm(1.25)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for name in ("Heading 1", "Heading 2", "Heading 3"):
        style = doc.styles[name]
        style.font.name = "Arial"
        style.font.size = Pt(12)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.first_line_indent = Cm(0)
        style.paragraph_format.line_spacing = 1.5
        style.paragraph_format.space_before = Pt(12)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    def centred(text: str, size: int = 12, bold: bool = False) -> None:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.line_spacing = 1.5
        run = p.add_run(text)
        run.font.name = "Arial"
        run.font.size = Pt(size)
        run.bold = bold

    # Capa
    for _ in range(5):
        doc.add_paragraph("")
    centred("LAUDO TÉCNICO DE AVALIAÇÃO DE IMÓVEL", 16, True)
    centred(_or(meta.get("work_name"), "Trabalho de avaliação"), 12, True)
    for _ in range(6):
        doc.add_paragraph("")
    centred(f"Solicitante: {_or(meta.get('requester'))}")
    centred(f"Responsável técnico: {_or(meta.get('technical_name'))}")
    for _ in range(5):
        doc.add_paragraph("")
    centred(
        f"{_or(meta.get('signature_city') or meta.get('city'), 'Local')}, "
        f"{format_date_br(meta.get('reference_date') or meta.get('date', ''))}"
    )
    doc.add_page_break()

    # Resumo executivo
    _heading(doc, "RESUMO EXECUTIVO")
    for line in (
        f"Solicitante: {_or(meta.get('requester'))}",
        f"Finalidade: {_or(meta.get('purpose'))}",
        f"Objetivo: {_or(meta.get('objective'))}",
        f"Data de referência: {format_date_br(meta.get('reference_date') or meta.get('date', ''))}",
        f"Imóveis na conta: {manager.n_active}    Desligados: {manager.n_inactive}",
    ):
        p = doc.add_paragraph(line)
        p.paragraph_format.first_line_indent = Cm(0)
    if context.evaluations:
        _docx_table(
            doc,
            ["Avaliando", "Estimativa", "IC 80%", "Adotado", "Fundamentação", "Precisão"],
            [
                (r.name, _n(r.prediction.point, 2),
                 f"{_n(r.prediction.ci_low, 2)} a {_n(r.prediction.ci_high, 2)}",
                 _n(r.adopted, 2), r.fundamental_degree, r.precision_degree)
                for r in context.evaluations
            ],
            widths=[3.0, 2.2, 3.4, 2.2, 2.6, 2.6], font_size=8.0,
        )
    else:
        doc.add_paragraph("Nenhum avaliando incluído. Incluir na aba 4 para completar o resumo.")
    doc.add_page_break()

    chapters = [
        "1. IDENTIFICAÇÃO DO SOLICITANTE (10.1 a)",
        "2. FINALIDADE DO LAUDO (10.1 b)",
        "3. OBJETIVO DA AVALIAÇÃO (10.1 c)",
        "4. PRESSUPOSTOS, RESSALVAS E FATORES LIMITANTES (10.1 d)",
        "5. IDENTIFICAÇÃO E CARACTERIZAÇÃO DO IMÓVEL AVALIANDO (10.1 e)",
        "6. DIAGNÓSTICO DO MERCADO (10.1 f)",
        "7. MÉTODOS E PROCEDIMENTOS (10.1 g)",
        "8. ESPECIFICAÇÃO DA AVALIAÇÃO (10.1 h)",
        "9. PLANILHA DOS DADOS UTILIZADOS (10.1 i)",
        "10. VARIÁVEIS DO MODELO E CRITÉRIOS (10.1 j)",
        "11. TRATAMENTO DOS DADOS E RESULTADO (10.1 k)",
        "12. RESULTADO DA AVALIAÇÃO E DATA DE REFERÊNCIA (10.1 l)",
        "13. QUALIFICAÇÃO LEGAL E ASSINATURA (10.1 m)",
        "14. REFERÊNCIAS",
        "15. ANEXOS",
    ]
    _heading(doc, "SUMÁRIO")
    for chapter in chapters:
        p = doc.add_paragraph(chapter)
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.line_spacing = 1.5
    doc.add_page_break()

    _heading(doc, chapters[0])
    _docx_table(doc, ["Campo", "Conteúdo"], [
        ("Solicitante", _or(meta.get("requester"))),
        ("Contato / endereço", _or(meta.get("description"), "Não informado.")),
    ], widths=[5.0, 11.0])
    _heading(doc, chapters[1])
    doc.add_paragraph(_or(meta.get("purpose")))
    _heading(doc, chapters[2])
    doc.add_paragraph(_or(meta.get("objective")))
    _heading(doc, chapters[3])
    doc.add_paragraph(_or(meta.get("assumptions")))
    if meta.get("limitations"):
        doc.add_paragraph(str(meta["limitations"]))
    if meta.get("inspection"):
        doc.add_paragraph(f"Vistoria: {meta['inspection']}.")
    _heading(doc, chapters[4])
    for label, value in (
        ("Município", meta.get("city")),
        ("Tipologia", meta.get("tipologia")),
        ("Identificação e caracterização", meta.get("description")),
    ):
        doc.add_paragraph(f"{label}: {_or(value)}")
    _heading(doc, chapters[5])
    doc.add_paragraph(_or(meta.get("sample_note"), "Diagnóstico de mercado não informado."))
    _heading(doc, chapters[6])
    doc.add_paragraph(
        "Método comparativo direto de dados de mercado, com regressão linear múltipla "
        "pelo método dos mínimos quadrados ordinários (OLS), conforme NBR 14653-1 e NBR 14653-2."
    )
    xs = ", ".join(spec["name"] for spec in manager.x_specs(True)) or "nenhuma"
    doc.add_paragraph(f"Variável dependente: {manager.y_column or 'não definida'}. Variáveis independentes: {xs}.")

    _heading(doc, chapters[7])
    if not context.evaluations:
        doc.add_paragraph("Nenhum avaliando incluído. A especificação será calculada após a inclusão na aba 4.")
    for result in context.evaluations:
        _heading(doc, f"Avaliando: {result.name}", 2)
        _docx_table(doc, ["Item", "O que verifica", "Grau", "Pontos", "Explicação"],
                    _nbr_item_rows(result.nbr), widths=[1.1, 3.5, 1.4, 1.4, 8.6])
        doc.add_paragraph(
            f"Grau de fundamentação: {result.nbr.final_degree}. Pontuação: {result.nbr.total_points}. "
            f"Grau de precisão: {result.prediction.precision_degree}."
        )
        if result.nbr.cap_explanation:
            doc.add_paragraph(result.nbr.cap_explanation)

    doc.add_page_break()
    _heading(doc, chapters[8])
    headers = ["Imóvel"] + [str(c) for c in manager.df.columns] + ["Ativo"]
    data_rows = []
    for position in range(len(manager.df)):
        row = [manager.label_for_row(position)]
        for column in manager.df.columns:
            value = manager.df.iloc[position][column]
            row.append("" if pd.isna(value) else str(value))
        row.append("Sim" if manager.active[position] else "Não")
        data_rows.append(tuple(row))
    _docx_table(doc, headers, data_rows)

    doc.add_page_break()
    _heading(doc, chapters[9])
    _docx_table(doc, ["Papel", "Variável", "Tipo", "Transformação / sinal", "Descrição / critério"],
                _sample_rows(manager, fit), widths=[1.2, 3.1, 2.8, 4.0, 4.9])

    doc.add_page_break()
    _heading(doc, chapters[10])
    doc.add_paragraph("Equação estimada (variável dependente transformada):")
    p = doc.add_paragraph(fit.equation)
    for run in p.runs:
        run.font.name = "Arial"
        run.font.size = Pt(10)
    doc.add_paragraph("Equação na escala original de Y:")
    p = doc.add_paragraph(fit.equation_original)
    for run in p.runs:
        run.font.name = "Arial"
        run.font.size = Pt(10)
    doc.add_paragraph(f"R²: {_n(fit.rsquared, 4)}    R² ajustado: {_n(fit.rsquared_adj, 4)}    "
                      f"Erro padrão dos resíduos: {_n(fit.scale, 4)}")
    _heading(doc, "ANOVA", 2)
    _docx_table(doc, ["Fonte", "SQ", "GL", "QM", "F", "p-valor"],
                [(r["Fonte"], _n(r["SQ"], 4), str(r["GL"]), _n(r["QM"], 4),
                  _n(r["F"], 3), _p(r["p-valor"])) for r in fit.anova_rows],
                widths=[3.0, 3.0, 2.0, 3.0, 2.5, 3.0])
    _heading(doc, "Coeficientes", 2)
    coeff_rows = []
    for name in ["const"] + fit.design_names:
        display = "Intercepto" if name == "const" else name
        coeff_rows.append((display, format_coefficient(fit.params[name]), _n(fit.bse[name], 4),
                           _n(fit.tvalues[name], 3), _p(fit.pvalues[name])))
    _docx_table(doc, ["Variável", "Estimativa", "Erro padrão", "t", "p-valor"], coeff_rows,
                widths=[5.5, 3.2, 3.2, 2.5, 3.0])
    doc.add_paragraph("O teste t dos itens de fundamentação usa somente os regressores, nunca o intercepto.")
    for result in context.evaluations:
        _heading(doc, f"Avaliando: {result.name}", 2)
        _docx_table(doc, ["Variável", "Valor informado"],
                    [(name, _n(value, 4)) for name, value in result.values.items()],
                    widths=[8.0, 8.0])
        _docx_table(doc, ["Resultado", "Valor"], [
            ("Estimativa pontual", _n(result.prediction.point, 2)),
            ("IC 80% da média", f"{_n(result.prediction.ci_low, 2)} a {_n(result.prediction.ci_high, 2)}"),
            ("IP 80% (preço)", f"{_n(result.prediction.pi_low, 2)} a {_n(result.prediction.pi_high, 2)}"),
            ("Intervalo usado", result.interval_label),
            ("Intervalo admissível", f"{_n(result.display_admissible_low, 2)} a {_n(result.display_admissible_high, 2)}"),
            ("Campo de arbítrio (±15%)", f"{_n(result.arbitrio_low, 2)} a {_n(result.arbitrio_high, 2)}"),
            ("Valor adotado / arbitrado", _n(result.adopted, 2)),
            ("Justificativa", result.justification or "Não informada"),
        ], widths=[7.0, 9.0])
        try:
            elast = [(r.get("display", ""), r.get("kind", ""), r.get("text", ""))
                     for r in fit.elasticity_rows(result.values)]
        except Exception:
            elast = []
        if elast:
            _heading(doc, "Elasticidades no ponto", 3)
            _docx_table(doc, ["Variável", "Tipo", "Elasticidade / efeito"], elast,
                        widths=[4.0, 3.0, 9.0])
        _docx_table(doc, ["Variável", "Avaliando", "Amostra ativa", "Situação", "Aceitável?", "Afastamento"],
                    _extrapolation_rows(result), widths=[3.2, 2.2, 3.4, 2.0, 2.0, 3.2])
    _heading(doc, "Diagnóstico das premissas", 2)
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
    _heading(doc, "Valores observados, estimados e resíduos", 2)
    residual_values = [
        (row.label, _n(row.observed, 2), _n(row.estimated, 2), _n(row.residual, 2),
         _percent(row.relative_pct, 1))
        for row in diag.table
    ]
    _docx_table(doc, ["Imóvel", "Observado", "Estimado", "Resíduo", "Relativo"],
                residual_values, widths=[5.2, 3.2, 3.2, 3.2, 2.6])
    _heading(doc, "Padronizado, studentizado, Cook e Mahalanobis", 2)
    residual_influence = [
        (row.label, _n(row.standardized, 3), _n(row.studentized, 3), _n(row.cook, 4), _n(row.mahalanobis, 3))
        for row in diag.table
    ]
    _docx_table(doc, ["Imóvel", "Padronizado", "Studentizado", "Cook", "Mahalanobis"],
                residual_influence, widths=[5.2, 3.2, 3.2, 3.2, 2.6])
    doc.add_page_break()
    _heading(doc, "Gráfico de preços observados versus valores estimados", 2)
    if "aderencia" in images:
        _docx_add_image(doc, images["aderencia"], 15.0)
    for name, caption in (
        ("residuos_ajustados", "Resíduos × valores ajustados"),
        ("qq", "Q-Q dos resíduos"),
        ("hist_residuos", "Histograma dos resíduos"),
        ("cook", "Distância de Cook"),
        ("mahalanobis", "Distância de Mahalanobis"),
    ):
        if name in images:
            doc.add_paragraph(caption)
            _docx_add_image(doc, images[name], 14.0)

    doc.add_page_break()
    _heading(doc, chapters[11])
    if context.evaluations:
        _docx_table(doc, ["Avaliando", "Estimativa", "IC 80%", "Adotado", "Fundamentação", "Precisão"],
                    [(r.name, _n(r.prediction.point, 2),
                      f"{_n(r.prediction.ci_low, 2)} a {_n(r.prediction.ci_high, 2)}",
                      _n(r.adopted, 2), r.fundamental_degree, r.precision_degree)
                     for r in context.evaluations],
                    widths=[4.0, 2.8, 4.0, 2.8, 2.2, 2.2])
    else:
        doc.add_paragraph("Nenhum avaliando incluído.")
    doc.add_paragraph(f"Data de referência da avaliação: {format_date_br(meta.get('reference_date') or meta.get('date', ''))}.")
    doc.add_paragraph("O valor adotado e a responsabilidade técnica são do avaliador responsável.")

    doc.add_page_break()
    _heading(doc, chapters[12])
    doc.add_paragraph(f"Responsável técnico: {_or(meta.get('technical_name'))}")
    doc.add_paragraph(f"Qualificação legal: {_or(meta.get('technical_registry'), 'CREA/CAU não informado.')}")
    doc.add_paragraph(f"{_or(meta.get('signature_city') or meta.get('city'), 'Local')}, "
                      f"{format_date_br(meta.get('reference_date') or meta.get('date', ''))}.")
    doc.add_paragraph("__________________________________________________________")
    doc.add_paragraph("Assinatura do responsável técnico")

    doc.add_page_break()
    _heading(doc, chapters[13])
    for reference in (
        "ASSOCIAÇÃO BRASILEIRA DE NORMAS TÉCNICAS. NBR 14653-1:2019 — Avaliação de bens: "
        "procedimentos gerais. Rio de Janeiro: ABNT, 2019.",
        "ASSOCIAÇÃO BRASILEIRA DE NORMAS TÉCNICAS. NBR 14653-2:2011 — Avaliação de bens: "
        "imóveis urbanos. Rio de Janeiro: ABNT, 2011.",
        "IBAPE — INSTITUTO BRASILEIRO DE AVALIAÇÕES E PERÍCIAS. Normas de avaliação. "
        "São Paulo: IBAPE, [data da edição utilizada].",
    ):
        p = doc.add_paragraph(reference)
        p.paragraph_format.first_line_indent = Cm(0)

    _heading(doc, chapters[14])
    for item in (
        "Anexo A — documentação dominical do imóvel;",
        "Anexo B — fotografias do imóvel avaliando;",
        "Anexo C — plantas e desenhos;",
        "Anexo D — memória de cálculo e relatórios originais dos programas utilizados.",
    ):
        p = doc.add_paragraph(item)
        p.paragraph_format.first_line_indent = Cm(0)
    p = doc.add_paragraph(
        "A sugestão de equação não substitui o julgamento do avaliador. Confira os dados antes de usar em laudo."
    )
    p.paragraph_format.first_line_indent = Cm(0)
    try:
        doc.save(str(target))
    except Exception as exc:
        raise ReportError("Não foi possível gravar o arquivo DOCX. Confira a pasta escolhida.") from exc
    return target
