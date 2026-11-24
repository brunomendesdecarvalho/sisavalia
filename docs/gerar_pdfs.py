#!/usr/bin/env python3
"""Gera os PDFs do manual e do guia de testes.

Requer, no computador de desenvolvimento:
  - Python com python-docx;
  - pandoc;
  - LibreOffice (soffice/libreoffice).

Uso:
    python3 docs/gerar_pdfs.py

O texto vem dos arquivos Markdown; o Pandoc monta o DOCX, o python-docx
acrescenta capa, sumário e numeração, e o LibreOffice converte para PDF.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

DOCS = Path(__file__).resolve().parent
ROOT = DOCS.parent
VERSION = "1.0.0"
ICON = DOCS / "telas" / "icone_sisavalia.png"
BLUE = RGBColor(30, 58, 138)
DARK = RGBColor(15, 23, 42)
GRAY = RGBColor(71, 85, 105)


def find_executable(*names: str) -> str:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    raise SystemExit(
        "Ferramenta não encontrada: " + ", ".join(names)
        + ". Instale o pandoc e o LibreOffice para gerar os PDFs."
    )


def prepare_markdown(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    text = "\n".join(lines).lstrip()
    text = re.sub(r"^(\s*)[-*] \[ \] ", r"\1- ☐ ", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*)[-*] \[[xX]\] ", r"\1- ☑ ", text, flags=re.MULTILINE)
    return text


def headings(text: str, levels: tuple[int, ...]) -> list[str]:
    found: list[str] = []
    current_level = 0
    for line in text.splitlines():
        match = re.match(r"^(#{2,4})\s+(.+?)\s*$", line)
        if not match:
            continue
        current_level = len(match.group(1))
        if current_level in levels:
            found.append(match.group(2).strip())
    return found


def set_run_font(run, size: float, color: RGBColor = DARK, bold: bool | None = None,
                 name: str = "DejaVu Sans") -> None:
    run.font.name = name
    run.font.size = Pt(size)
    run.font.color.rgb = color
    if bold is not None:
        run.bold = bold
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    rfonts.set(qn("w:cs"), name)


def paragraph_border(paragraph, color: str = "CBD5E1", size: int = 6) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    borders = ppr.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        ppr.append(borders)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)


def shade_cell(cell, fill: str) -> None:
    tcpr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), fill)
    tcpr.append(shading)


def style_document(doc: Document) -> None:
    section = doc.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.1)
    section.right_margin = Cm(2.1)
    section.different_first_page_header_footer = True

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "DejaVu Sans"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = DARK
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.18
    for style_name in ("Body Text", "First Paragraph", "Compact"):
        try:
            style = styles[style_name]
            style.font.name = "DejaVu Sans"
            style.font.size = Pt(10 if style_name != "Compact" else 9.2)
            style.font.color.rgb = DARK
        except KeyError:
            pass
    for style_name, size, color, before, after in (
        ("Heading 1", 20, BLUE, 0, 10),
        ("Heading 2", 14.5, BLUE, 15, 5),
        ("Heading 3", 11.5, RGBColor(51, 65, 85), 11, 4),
    ):
        try:
            style = styles[style_name]
            style.font.name = "DejaVu Sans"
            style.font.size = Pt(size)
            style.font.bold = True
            style.font.color.rgb = color
            style.paragraph_format.space_before = Pt(before)
            style.paragraph_format.space_after = Pt(after)
            style.paragraph_format.keep_with_next = True
        except KeyError:
            pass

    # Fontes e espaçamento explícitos em todo o corpo vindo do Pandoc.
    for p in doc.paragraphs:
        style_name = p.style.name if p.style is not None else ""
        is_heading = style_name.startswith("Heading")
        is_code = "Source Code" in style_name
        for run in p.runs:
            if run.font.name and "Mono" in run.font.name:
                set_run_font(run, 9, RGBColor(15, 23, 42), name="DejaVu Sans Mono")
            elif is_heading:
                heading_size = 20 if "1" in style_name else 14.5 if "2" in style_name else 11.5
                set_run_font(run, heading_size, BLUE if not "3" in style_name else RGBColor(51, 65, 85), bold=True)
            elif is_code:
                set_run_font(run, 9, RGBColor(15, 23, 42), name="DejaVu Sans Mono")
            else:
                set_run_font(run, 10.5, DARK)
        if not is_heading:
            p.paragraph_format.space_after = Pt(5)
            p.paragraph_format.line_spacing = 1.18
    for table in doc.tables:
        try:
            table.style = "Table Grid"
        except Exception:
            pass
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for row_index, row in enumerate(table.rows):
            for cell in row.cells:
                if row_index == 0:
                    shade_cell(cell, "E2E8F0")
                for p in cell.paragraphs:
                    for run in p.runs:
                        set_run_font(run, 9, DARK, bold=(row_index == 0))

    # Número de página no rodapé, exceto na capa.
    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)
    set_run_font(run, 8.5, GRAY)


def add_cover_and_toc(doc: Document, title: str, subtitle: str, toc_items: list[str]) -> None:
    start = len(doc.paragraphs)
    picture = doc.add_picture(str(ICON), width=Cm(3.2))
    picture_paragraph = doc.paragraphs[-1]
    picture_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    picture_paragraph.paragraph_format.space_before = Pt(70)

    brand = doc.add_paragraph()
    brand.alignment = WD_ALIGN_PARAGRAPH.CENTER
    brand.paragraph_format.space_before = Pt(18)
    set_run_font(brand.add_run("SISA VALIA".replace(" ", "")), 12, BLUE, bold=True)

    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_p.paragraph_format.space_before = Pt(20)
    set_run_font(title_p.add_run(title), 30, BLUE, bold=True)

    subtitle_p = doc.add_paragraph()
    subtitle_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(subtitle_p.add_run(subtitle), 14, RGBColor(51, 65, 85))

    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.paragraph_format.space_before = Pt(22)
    set_run_font(meta.add_run(f"Versão {VERSION}  •  {date.today().strftime('%d/%m/%Y')}"), 10, GRAY)
    description = doc.add_paragraph()
    description.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(description.add_run("Análise estatística, regressão e engenharia de avaliações"), 10, GRAY)

    warning = doc.add_paragraph()
    warning.alignment = WD_ALIGN_PARAGRAPH.CENTER
    warning.paragraph_format.space_before = Pt(48)
    warning.paragraph_format.left_indent = Cm(2.0)
    warning.paragraph_format.right_indent = Cm(2.0)
    set_run_font(warning.add_run("Dados de exemplo. Não use em laudo."), 10, RGBColor(124, 45, 18), bold=True)
    note = doc.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    note.paragraph_format.left_indent = Cm(1.6)
    note.paragraph_format.right_indent = Cm(1.6)
    set_run_font(note.add_run("A decisão técnica e a responsabilidade do laudo são do avaliador."), 9.2, GRAY)

    doc.add_page_break()
    toc_title = doc.add_paragraph(style="Heading 1")
    set_run_font(toc_title.add_run("Conteúdo"), 20, BLUE, bold=True)
    for item in toc_items:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.5)
        p.paragraph_format.space_after = Pt(6)
        set_run_font(p.add_run(item), 10.5, DARK)
    doc.add_page_break()
    end = len(doc.paragraphs)
    cover_paragraphs = list(doc.paragraphs[start:end])
    body = doc.element.body
    for p in reversed(cover_paragraphs):
        body.remove(p._p)
        body.insert(0, p._p)


def generate(markdown_path: Path, pdf_path: Path, title: str, subtitle: str,
             toc_levels: tuple[int, ...], workdir: Path) -> None:
    if not ICON.exists():
        raise SystemExit(f"Ícone não encontrado: {ICON}")
    source = markdown_path.read_text(encoding="utf-8")
    temp_md = workdir / (markdown_path.stem + ".md")
    temp_md.write_text(prepare_markdown(source), encoding="utf-8")
    docx_path = workdir / (markdown_path.stem + ".docx")
    pandoc = find_executable("pandoc")
    subprocess.run(
        [pandoc, str(temp_md), "-f", "markdown+pipe_tables+task_lists",
         "--resource-path", str(DOCS), "-o", str(docx_path)],
        check=True, cwd=DOCS, timeout=180,
    )
    doc = Document(docx_path)
    doc.core_properties.title = title
    doc.core_properties.author = "SisAvalia"
    doc.core_properties.subject = subtitle
    style_document(doc)
    add_cover_and_toc(doc, title, subtitle, headings(source, toc_levels))
    doc.save(docx_path)

    libreoffice = find_executable("libreoffice", "soffice")
    profile = workdir / "lo_profile"
    subprocess.run(
        [libreoffice, f"-env:UserInstallation=file://{profile}", "--headless",
         "--convert-to", "pdf:writer_pdf_Export", "--outdir", str(workdir), str(docx_path)],
        check=True, cwd=workdir, timeout=240,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    generated = workdir / (markdown_path.stem + ".pdf")
    if not generated.exists():
        raise SystemExit(f"LibreOffice não gerou o PDF de {markdown_path.name}")
    shutil.copy2(generated, pdf_path)
    pages = ""
    try:
        import subprocess as sp
        info = sp.check_output(["pdfinfo", str(pdf_path)], text=True)
        pages = next(line.split(":", 1)[1].strip() for line in info.splitlines() if line.startswith("Pages:"))
    except Exception:
        pages = "?"
    print(f"{pdf_path.name}: {pages} página(s), {pdf_path.stat().st_size} bytes")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sisavalia_docs_") as temp:
        workdir = Path(temp)
        generate(
            DOCS / "MANUAL_DO_USUARIO.md",
            DOCS / "Manual_do_Usuario_SisAvalia.pdf",
            "Manual do Usuário",
            "Aprenda a usar o SisAvalia passo a passo",
            (2,),
            workdir,
        )
        generate(
            DOCS / "GUIA_DE_TESTES.md",
            DOCS / "Guia_de_Testes_SisAvalia.pdf",
            "Guia de Testes de Aceitação",
            "Roteiro para validar o fluxo de avaliação",
            (2, 3),
            workdir,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
