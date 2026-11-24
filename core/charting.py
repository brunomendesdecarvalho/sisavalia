"""Gráficos comuns a telas e relatórios, com padrão brasileiro."""
from __future__ import annotations

import io
import math
from typing import Any, Iterable, Optional, Sequence

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from .formatting import format_number

BG = "#FFFFFF"
GRID = "#E2E8F0"
PRIMARY = "#2563EB"
PRIMARY_DARK = "#1D4ED8"
ACCENT = "#0EA5E9"
GREEN = "#16A34A"
YELLOW = "#D97706"
RED = "#DC2626"
GRAY = "#64748B"
LIGHT = "#F8FAFC"
SERIES = ["#2563EB", "#16A34A", "#D97706", "#DC2626", "#7C3AED", "#0891B2", "#DB2777", "#4B5563"]

_current_font_pt = 12


def configure_matplotlib(font_pt: int = 12) -> None:
    global _current_font_pt
    _current_font_pt = max(12, int(font_pt))
    matplotlib.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Liberation Sans", "Noto Sans"],
        "font.size": _current_font_pt,
        "axes.titlesize": _current_font_pt + 2,
        "axes.titleweight": "bold",
        "axes.labelsize": _current_font_pt,
        "xtick.labelsize": _current_font_pt,
        "ytick.labelsize": _current_font_pt,
        "legend.fontsize": _current_font_pt,
        "figure.titlesize": _current_font_pt + 3,
        "figure.facecolor": BG,
        "axes.facecolor": BG,
        "savefig.facecolor": BG,
        "axes.edgecolor": "#CBD5E1",
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linestyle": "--",
        "grid.linewidth": 0.8,
        "grid.alpha": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.axisbelow": True,
        "legend.frameon": False,
        "lines.linewidth": 2.0,
        "figure.autolayout": False,
    })


configure_matplotlib(12)


def _decimals_for(values: np.ndarray) -> int:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return 2
    spread = float(np.nanmax(np.abs(values)))
    if spread >= 10000:
        return 0
    if spread >= 100:
        return 0
    if spread >= 10:
        return 1
    return 2


def br_formatter(values: Optional[Iterable[float]] = None, decimals: Optional[int] = None) -> FuncFormatter:
    data = np.asarray(list(values) if values is not None else [], dtype=float)
    dec = _decimals_for(data) if decimals is None else decimals

    def _fmt(value: float, _pos: Any = None) -> str:
        if not math.isfinite(value):
            return ""
        return format_number(value, dec)

    return FuncFormatter(_fmt)


def new_figure(figsize: tuple[float, float] = (7.2, 4.2), dpi: int = 100) -> tuple[Figure, Any]:
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    return fig, ax


def tidy(ax: Any, *, title: str = "", xlabel: str = "", ylabel: str = "",
         x_values: Optional[Iterable[float]] = None, y_values: Optional[Iterable[float]] = None,
         grid_axis: str = "both") -> None:
    if title:
        ax.set_title(title, pad=12)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    ax.grid(True, axis=grid_axis, color=GRID, linestyle="--", linewidth=0.8, alpha=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if x_values is not None:
        ax.xaxis.set_major_formatter(br_formatter(x_values))
    if y_values is not None:
        ax.yaxis.set_major_formatter(br_formatter(y_values))


def scatter_xy(x: Sequence[float], y: Sequence[float], *, title: str,
               xlabel: str, ylabel: str,
               highlight_index: Optional[int] = None,
               highlight_label: Optional[str] = None) -> tuple[Figure, Any]:
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    fig, ax = new_figure()
    ax.scatter(x_arr, y_arr, s=55, color=PRIMARY, alpha=0.82, edgecolor="white", linewidth=0.9, zorder=3)
    if highlight_index is not None and 0 <= highlight_index < len(x_arr):
        ax.scatter([x_arr[highlight_index]], [y_arr[highlight_index]], s=170,
                   facecolor="none", edgecolor=RED, linewidth=2.4, zorder=5,
                   label=highlight_label or "Avaliando")
        ax.legend(loc="best")
    tidy(ax, title=title, xlabel=xlabel, ylabel=ylabel, x_values=x_arr, y_values=y_arr)
    fig.tight_layout()
    return fig, ax


def histogram(values: Sequence[float], *, title: str, xlabel: str,
              color: str = PRIMARY, bins: int = 12) -> tuple[Figure, Any]:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    fig, ax = new_figure()
    if len(arr):
        bins = max(4, min(bins, max(4, int(math.sqrt(len(arr)) * 1.5))))
        ax.hist(arr, bins=bins, color=color, edgecolor="white", alpha=0.86, zorder=3)
    tidy(ax, title=title, xlabel=xlabel, ylabel="Quantidade",
         x_values=arr, y_values=None, grid_axis="y")
    fig.tight_layout()
    return fig, ax


def fit_scatter(observed: Sequence[float], estimated: Sequence[float], labels: Sequence[str],
                *, title: str = "Observado × estimado") -> tuple[Figure, Any]:
    obs = np.asarray(observed, dtype=float)
    est = np.asarray(estimated, dtype=float)
    fig, ax = new_figure()
    ax.scatter(est, obs, s=58, color=PRIMARY, alpha=0.85, edgecolor="white", linewidth=0.9, zorder=3,
               label="Imóveis")
    finite = np.concatenate([obs[np.isfinite(obs)], est[np.isfinite(est)]])
    if len(finite):
        low, high = float(np.min(finite)), float(np.max(finite))
        pad = (high - low) * 0.05 if high > low else max(abs(high) * 0.05, 1.0)
        line = [low - pad, high + pad]
        ax.plot(line, line, color=RED, linestyle="--", linewidth=1.8, label="Reta de 45°")
        ax.set_xlim(line)
        ax.set_ylim(line)
    tidy(ax, title=title, xlabel="Valor estimado pela equação", ylabel="Valor observado",
         x_values=est, y_values=obs)
    ax.legend(loc="upper left")
    fig.tight_layout()
    return fig, ax


def residual_fitted(fitted: Sequence[float], residuals: Sequence[float], labels: Sequence[str]
                    ) -> tuple[Figure, Any]:
    est = np.asarray(fitted, dtype=float)
    res = np.asarray(residuals, dtype=float)
    fig, ax = new_figure()
    ax.axhline(0, color=GRAY, linewidth=1.2, linestyle="-")
    ax.scatter(est, res, s=58, color=PRIMARY, alpha=0.85, edgecolor="white", linewidth=0.9, zorder=3)
    tidy(ax, title="Resíduos × valores ajustados", xlabel="Valor ajustado",
         ylabel="Resíduo (observado − ajustado)", x_values=est, y_values=res)
    fig.tight_layout()
    return fig, ax


def qq_plot(residuals: Sequence[float]) -> tuple[Figure, Any]:
    from scipy import stats
    res = np.asarray(residuals, dtype=float)
    res = res[np.isfinite(res)]
    fig, ax = new_figure()
    if len(res) >= 3:
        (osm, osr), (slope, intercept, _r) = stats.probplot(res, dist="norm")
        ax.scatter(osm, osr, s=52, color=PRIMARY, alpha=0.85, edgecolor="white", linewidth=0.8, zorder=3)
        ax.plot(osm, slope * osm + intercept, color=RED, linewidth=1.8)
        tidy(ax, title="Q-Q dos resíduos", xlabel="Quantil teórico normal",
             ylabel="Resíduo ordenado", x_values=osm, y_values=osr)
    else:
        tidy(ax, title="Q-Q dos resíduos", xlabel="Quantil teórico normal", ylabel="Resíduo ordenado")
        ax.text(0.5, 0.5, "Amostra pequena para o gráfico", transform=ax.transAxes,
                ha="center", va="center", color=GRAY, fontsize=max(12, _current_font_pt))
    fig.tight_layout()
    return fig, ax


def stem_plot(values: Sequence[float], labels: Sequence[str], threshold: float, *,
              title: str, ylabel: str, flag_color: str = RED) -> tuple[Figure, Any]:
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    x = np.arange(1, n + 1)
    fig, ax = new_figure()
    colors = [flag_color if (math.isfinite(v) and v > threshold) else PRIMARY for v in arr]
    ax.vlines(x, 0, arr, colors=colors, linewidth=1.7, alpha=0.85)
    ax.scatter(x, arr, c=colors, s=26, zorder=3)
    if math.isfinite(threshold) and threshold > 0 and n:
        ax.axhline(threshold, color=YELLOW, linestyle="--", linewidth=1.3,
                   label=f"Corte = {format_number(threshold, 3)}")
        ax.legend(loc="upper right")
    tidy(ax, title=title, xlabel="Imóvel (ordem da tabela)", ylabel=ylabel,
         x_values=None, y_values=arr)
    fig.tight_layout()
    return fig, ax


def curve_plot(x: Sequence[float], y: Sequence[float], *, variable: str,
               point: Optional[tuple[float, float]] = None,
               warning: str = "") -> tuple[Figure, Any]:
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    fig, ax = new_figure()
    ax.plot(x_arr, y_arr, color=PRIMARY, linewidth=2.3)
    if point is not None:
        ax.scatter([point[0]], [point[1]], s=110, color=RED, zorder=4, label="Avaliando")
        ax.legend(loc="best")
    title = f"Como o valor muda com {variable}"
    if warning:
        ax.text(0.015, 0.97, warning, transform=ax.transAxes, va="top", ha="left",
                color=RED, fontsize=max(12, _current_font_pt - 1),
                bbox=dict(boxstyle="round,pad=0.4", facecolor="#FEF2F2", edgecolor=RED))
    tidy(ax, title=title, xlabel=variable, ylabel="Valor estimado", x_values=x_arr, y_values=y_arr)
    fig.tight_layout()
    return fig, ax


def kmeans_scatter(scores: np.ndarray, labels: np.ndarray, *, axis_labels: tuple[str, str],
                   highlight_labels: Optional[Sequence[str]] = None) -> tuple[Figure, Any]:
    fig, ax = new_figure()
    labels = np.asarray(labels, dtype=int)
    for cluster in sorted(set(int(x) for x in labels)):
        mask = labels == cluster
        ax.scatter(scores[mask, 0], scores[mask, 1], s=62,
                   color=SERIES[cluster % len(SERIES)], alpha=0.85,
                   edgecolor="white", linewidth=0.8, label=f"Grupo {cluster + 1}", zorder=3)
    tidy(ax, title="Grupos encontrados", xlabel=axis_labels[0], ylabel=axis_labels[1],
         x_values=scores[:, 0], y_values=scores[:, 1])
    ax.legend(loc="best", ncol=2)
    fig.tight_layout()
    return fig, ax


def elbow_plot(ks: Sequence[int], inertia: Sequence[float]) -> tuple[Figure, Any]:
    ks_arr = np.asarray(ks, dtype=float)
    in_arr = np.asarray(inertia, dtype=float)
    fig, ax = new_figure()
    ax.plot(ks_arr, in_arr, marker="o", color=PRIMARY, markersize=7)
    tidy(ax, title="Cotovelo: quantos grupos fazem sentido", xlabel="Número de grupos",
         ylabel="Coesão interna (menor é melhor)", x_values=ks_arr, y_values=in_arr)
    ax.set_xticks(ks_arr[np.isfinite(ks_arr)])
    fig.tight_layout()
    return fig, ax


def pca_scree(explained: Sequence[float], cumulative: Sequence[float]) -> tuple[Figure, Any]:
    n = len(explained)
    x = np.arange(1, n + 1)
    fig, ax = new_figure()
    ax.bar(x, np.asarray(explained) * 100.0, color=PRIMARY, alpha=0.85, label="Por componente")
    ax.plot(x, np.asarray(cumulative) * 100.0, color=RED, marker="o", markersize=5,
            label="Acumulado")
    ax.set_ylim(0, 105)
    tidy(ax, title="Quanta variação cada componente explica", xlabel="Componente",
         ylabel="Percentual da variação", x_values=None, y_values=None, grid_axis="y")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: format_number(v, 0) + "%"))
    ax.legend(loc="best")
    fig.tight_layout()
    return fig, ax


def pca_biplot(scores: np.ndarray, loadings: np.ndarray, explained: Sequence[float],
               names: Sequence[str], labels: Optional[Sequence[str]] = None) -> tuple[Figure, Any]:
    fig, ax = new_figure(figsize=(7.6, 4.8))
    ax.scatter(scores[:, 0], scores[:, 1], s=52, color=PRIMARY, alpha=0.55,
               edgecolor="white", linewidth=0.7, zorder=2)
    scale = 0.85 * max(float(np.max(np.abs(scores[:, :2]))), 1e-9)
    max_load = max(float(np.max(np.abs(loadings))), 1e-9)
    for i, name in enumerate(names):
        dx = loadings[i, 0] / max_load * scale
        dy = loadings[i, 1] / max_load * scale
        ax.arrow(0, 0, dx, dy, color=RED, width=0.005, head_width=scale * 0.045,
                 length_includes_head=True, zorder=3)
        ax.text(dx * 1.08, dy * 1.08, str(name), color=RED, fontsize=max(12, _current_font_pt - 1))
    pc1 = format_number(float(explained[0]) * 100, 1) if len(explained) else "0"
    pc2 = format_number(float(explained[1]) * 100, 1) if len(explained) > 1 else "0"
    tidy(ax, title="Mapa das variáveis e dos imóveis",
         xlabel=f"CP1 ({pc1}% da variação)", ylabel=f"CP2 ({pc2}% da variação)",
         x_values=scores[:, 0], y_values=scores[:, 1])
    ax.axhline(0, color=GRAY, linewidth=0.8)
    ax.axvline(0, color=GRAY, linewidth=0.8)
    fig.tight_layout()
    return fig, ax


def simulation_hist(values: Sequence[float], *, distribution: str) -> tuple[Figure, Any]:
    arr = np.asarray(values, dtype=float)
    fig, ax = new_figure()
    ax.hist(arr, bins=30, color=ACCENT, edgecolor="white", alpha=0.88, zorder=3)
    tidy(ax, title=f"Valores simulados — {distribution}", xlabel="Valor",
         ylabel="Quantidade", x_values=arr, grid_axis="y")
    fig.tight_layout()
    return fig, ax


def figure_to_bytes(fig: Figure, dpi: int = 220) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight", facecolor=BG)
    buffer.seek(0)
    return buffer.getvalue()


def figure_from_fit(fit: Any) -> tuple[Figure, Any]:
    return fit_scatter(fit.observed_original, fit.fitted_original, fit.labels)
