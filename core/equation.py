"""Equações em LaTeX e imagem PNG para tela e relatórios."""
from __future__ import annotations

import io
import re
from typing import Any

from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties

from .formatting import format_number


def _latex_text(text: str) -> str:
    text = str(text).replace("\\", r"\backslash ")
    for char, repl in (("_", r"\_"), ("%", r"\%"), ("&", r"\&"), ("#", r"\#"),
                       ("$", r"\$"), ("{", r"\{"), ("}", r"\}")):
        text = text.replace(char, repl)
    return r"\mathrm{" + text + "}"


def _latex_number(value: float, decimals: int = 4) -> str:
    text = format_number(float(value), decimals)
    text = text.replace(".", "")
    text = text.replace(",", "{,}")
    text = text.replace("−", "-")
    return text


def _variable(name: str, transform: str) -> str:
    base = _latex_text(name)
    if transform == "ln(x)":
        return rf"\ln\left({base}\right)"
    if transform == "1/x":
        return rf"\frac{{1}}{{{base}}}"
    if transform == "x²":
        return rf"{base}^{{2}}"
    if transform == "√x":
        return rf"\sqrt{{{base}}}"
    return base


def _lhs(name: str, transform: str) -> str:
    base = _latex_text(name)
    if transform == "ln(x)":
        return rf"\ln\left({base}\right)"
    if transform == "1/x":
        return rf"\frac{{1}}{{{base}}}"
    if transform == "x²":
        return rf"{base}^{{2}}"
    if transform == "√x":
        return rf"\sqrt{{{base}}}"
    return base


def equation_latex(fit: Any) -> str:
    """Equação estimada em LaTeX, com vírgula decimal brasileira."""
    terms: list[tuple[float, str]] = []
    constant = float(fit.params["const"])
    terms.append((constant, ""))
    for name, transform, design in zip(fit.x_names, fit.x_transforms, fit.design_names):
        terms.append((float(fit.params[design]), _variable(name, transform)))
    parts: list[str] = []
    for index, (coefficient, variable) in enumerate(terms):
        if not abs(coefficient) > 1e-14:
            continue
        sign = "-" if coefficient < 0 else "+"
        number = _latex_number(abs(coefficient))
        body = number + (rf"\,{variable}" if variable else "")
        if not parts:
            parts.append(("-" if sign == "-" else "") + body)
        else:
            parts.append((" - " if sign == "-" else " + ") + body)
    rhs = "".join(parts) or "0"
    return f"{_lhs(fit.y_name, fit.y_transform)} = {rhs}"


def equation_latex_original(fit: Any) -> str:
    """Equação com Y na escala original, em LaTeX."""
    rhs = equation_latex(fit).split(" = ", 1)[1]
    lhs = _latex_text(fit.y_name)
    if fit.y_transform == "ln(x)":
        return rf"{lhs} = \exp\left({rhs}\right)"
    if fit.y_transform == "1/x":
        return rf"{lhs} = \frac{{1}}{{{rhs}}}"
    if fit.y_transform == "x²":
        return rf"{lhs} = \sqrt{{{rhs}}}"
    if fit.y_transform == "√x":
        return rf"{lhs} = \left({rhs}\right)^{{2}}"
    return f"{lhs} = {rhs}"


def _equation_lines(latex: str, max_chars: int = 130) -> list[str]:
    if len(latex) <= max_chars or r"\exp" in latex:
        return [latex]
    parts = [part for part in re.split(r"(?= [+-] )", latex) if part]
    lines: list[str] = []
    current = ""
    for part in parts:
        candidate = current + part
        if current and len(candidate) > max_chars:
            lines.append(current.strip())
            current = part.strip()
        else:
            current = candidate
    if current:
        lines.append(current.strip())
    return lines or [latex]


def equation_png_bytes(latex: str, *, fontsize: float = 21, dpi: int = 220) -> bytes:
    """Renderiza a equação em PNG, fundo branco e traço preto."""
    lines = _equation_lines(latex)
    height = max(1.0, 0.72 * len(lines) + 0.5)
    fig = Figure(figsize=(10.0, height), dpi=180, facecolor="white")
    for index, line in enumerate(lines):
        y = 1.0 - (index + 0.55) / max(1, len(lines))
        fig.text(
            0.012, y, f"${line}$", color="black", fontsize=fontsize,
            va="center", ha="left", fontproperties=FontProperties(family="DejaVu Sans"),
        )
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi, facecolor="white",
                bbox_inches="tight", pad_inches=0.18)
    buffer.seek(0)
    return buffer.getvalue()


def equation_png_from_fit(fit: Any, *, original: bool = False) -> bytes:
    latex = equation_latex_original(fit) if original else equation_latex(fit)
    return equation_png_bytes(latex)
