"""Formatação e leitura de números no padrão brasileiro.

Toda a interface, gráficos e relatórios passam por estas funções para que
nenhum número apareça com ponto decimal americano.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any, Optional

import numpy as np
import pandas as pd


NBSP = "\u00a0"
_EMPTY = "—"
_MONEY_RE = re.compile(r"[^0-9,.\-+eE]")


def is_missing(value: Any) -> bool:
    """Verdadeiro para None, NaN, NaT e textos vazios."""
    if value is None:
        return True
    if isinstance(value, (float, np.floating)):
        return math.isnan(float(value)) or math.isinf(float(value))
    try:
        result = pd.isna(value)
        if isinstance(result, (bool, np.bool_)):
            return bool(result)
    except (TypeError, ValueError):
        return isinstance(value, str) and not value.strip()
    return isinstance(value, str) and not value.strip()


def parse_number(text: Any) -> float:
    """Converte texto digitado pelo usuário em número.

    Aceita vírgula ou ponto como separador decimal, símbolo de moeda,
    porcentagem e espaços. Quando há os dois separadores, o último é o
    decimal. Levanta ValueError com mensagem em português.
    """
    if text is None:
        raise ValueError("Digite um número.")
    if isinstance(text, (int, float, np.integer, np.floating)) and not isinstance(text, bool):
        value = float(text)
        if math.isnan(value) or math.isinf(value):
            raise ValueError("Digite um número válido.")
        return value
    raw = str(text).strip().replace(NBSP, " ").replace("−", "-")
    if not raw:
        raise ValueError("Digite um número.")
    raw = raw.replace("R$", "").replace("r$", "").replace("%", "").strip()
    raw = raw.replace(" ", "")
    if not raw:
        raise ValueError("Digite um número.")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    # Só ponto: é aceito como separador decimal digitado.
    raw = _MONEY_RE.sub("", raw)
    if raw in {"", "-", "+", ".", "-.", "+."}:
        raise ValueError("Digite um número válido.")
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"“{text}” não é um número válido. Use, por exemplo, 1.234,56.") from exc
    if math.isnan(value) or math.isinf(value):
        raise ValueError("Digite um número finito.")
    return value


def format_number(
    value: Any,
    decimals: int = 2,
    *,
    thousands: bool = True,
    empty: str = _EMPTY,
    signed: bool = False,
) -> str:
    """Formata um número no padrão brasileiro: 1.234,56."""
    if is_missing(value):
        return empty
    try:
        number = float(value)
    except (TypeError, ValueError):
        return empty
    if math.isnan(number) or math.isinf(number):
        return empty
    if abs(number) >= 1e12 or (0 < abs(number) < 1e-4 and decimals < 6):
        text = f"{number:.4e}"
        mantissa, exponent = text.split("e")
        mantissa = mantissa.replace(".", ",")
        exp = int(exponent)
        return f"{mantissa} × 10^{exp}"
    if abs(number) < 0.5 * 10 ** (-decimals):
        number = 0.0
    pattern = f"{number:,.{decimals}f}"
    if thousands:
        pattern = pattern.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")
    else:
        pattern = pattern.replace(".", ",")
    if signed and number > 0:
        pattern = "+" + pattern
    return pattern


def format_int(value: Any, *, empty: str = _EMPTY) -> str:
    if is_missing(value):
        return empty
    try:
        return f"{int(round(float(value))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return empty


def format_percent(value: Any, decimals: int = 1, *, empty: str = _EMPTY) -> str:
    """Formata um valor percentual já multiplicado por 100."""
    if is_missing(value):
        return empty
    return format_number(value, decimals) + "%"


def format_fraction_percent(value: Any, decimals: int = 1, *, empty: str = _EMPTY) -> str:
    """Formata uma fração (0,35) como porcentagem (35,0%)."""
    if is_missing(value):
        return empty
    return format_percent(float(value) * 100.0, decimals)


def format_pvalue(value: Any) -> str:
    if is_missing(value):
        return _EMPTY
    try:
        p = float(value)
    except (TypeError, ValueError):
        return _EMPTY
    if p < 0.0001:
        return "< 0,0001"
    if p < 0.001:
        return format_number(p, 4)
    return format_number(p, 3)


def format_scientific(value: Any, decimals: int = 3) -> str:
    if is_missing(value):
        return _EMPTY
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _EMPTY
    if number == 0:
        return "0"
    exponent = int(math.floor(math.log10(abs(number))))
    mantissa = number / (10 ** exponent)
    return f"{format_number(mantissa, decimals)} × 10^{exponent}"


def format_date_br(value: Any) -> str:
    if is_missing(value):
        return _EMPTY
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.strftime("%d/%m/%Y")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return str(value)


def parse_date_br(text: str) -> Optional[date]:
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(text).strip(), fmt).date()
        except ValueError:
            continue
    return None


def format_coefficient(value: Any) -> str:
    """Coeficiente com até quatro casas, sem zeros inúteis no fim."""
    if is_missing(value):
        return _EMPTY
    number = float(value)
    if abs(number) < 0.001 and number != 0:
        return format_scientific(number, 3)
    text = format_number(number, 4)
    text = text.rstrip("0").rstrip(",")
    return text or "0"


def format_currency(value: Any) -> str:
    if is_missing(value):
        return _EMPTY
    return "R$ " + format_number(value, 2)


def safe_str(value: Any) -> str:
    if is_missing(value):
        return ""
    return str(value)


def br_to_float_or_none(text: str) -> Optional[float]:
    try:
        return parse_number(text)
    except ValueError:
        return None
