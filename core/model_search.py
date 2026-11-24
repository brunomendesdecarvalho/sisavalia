"""Busca de equações candidatas por R² ajustado."""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Sequence

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from .data_manager import DataManager, transform_series, transformation_label
from .formatting import format_coefficient, format_number, format_pvalue, is_missing
from .nbr14653 import provisional_degree


class SearchCancelled(Exception):
    """A busca foi cancelada pelo usuário."""


@dataclass
class SearchResult:
    spec: dict[str, Any]
    equation: str
    r2: float
    r2_adj: float
    f_p: float
    worst_p: float
    signs: str
    n: int
    degree: str
    has_allocated_code: bool
    coefficients: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec,
            "equation": self.equation,
            "r2": self.r2,
            "r2_adj": self.r2_adj,
            "f_p": self.f_p,
            "worst_p": self.worst_p,
            "signs": self.signs,
            "n": self.n,
            "degree": self.degree,
            "has_allocated_code": self.has_allocated_code,
            "coefficients": self.coefficients,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchResult":
        return cls(
            spec=data.get("spec", {}),
            equation=data.get("equation", ""),
            r2=float(data.get("r2", np.nan)),
            r2_adj=float(data.get("r2_adj", np.nan)),
            f_p=float(data.get("f_p", np.nan)),
            worst_p=float(data.get("worst_p", np.nan)),
            signs=data.get("signs", ""),
            n=int(data.get("n", 0)),
            degree=data.get("degree", ""),
            has_allocated_code=bool(data.get("has_allocated_code", False)),
            coefficients=data.get("coefficients", []),
        )


@dataclass
class SearchOutcome:
    results: list[SearchResult]
    tested: int
    mode: str
    total_specs: int
    cancelled: bool = False


ProgressCallback = Callable[[int, int, str], None]
CancelCallback = Callable[[], bool]


class ModelSearch:
    """Testa especificações lineares com transformações x, ln(x) e 1/x."""

    MAX_SPECS = 1500
    MAX_SIMPLIFIED_FITS = 400
    TOP_N = 30
    SEARCH_TRANSFORMS = ("x", "ln(x)", "1/x")

    def __init__(self, manager: DataManager, progress: Optional[ProgressCallback] = None,
                 cancel: Optional[CancelCallback] = None) -> None:
        self.manager = manager
        self.progress = progress
        self.cancel = cancel
        self._tested = 0
        self._total_hint = 0
        self._cancel_requested = False
        self._cache: dict[str, pd.Series] = {}
        if not manager.y_column:
            raise ValueError("Escolha a variável dependente (Y) antes de sugerir equações.")
        if manager.y_transform not in ("x", "ln(x)", "1/x", "x²", "√x"):
            raise ValueError("Transformação de Y inválida.")
        self.specs = manager.x_specs(True)
        if not self.specs:
            raise ValueError(
                "Marque na aba 1 as variáveis que podem entrar na equação. "
                "A sugestão usa as variáveis independentes escolhidas por você."
            )
        self.active_positions = [i for i, a in enumerate(manager.active) if a]
        self.y_raw = pd.to_numeric(manager.df[manager.y_column], errors="coerce")
        self.y_trans = self._transform(self.manager.y_column, manager.y_transform)
        self.y_valid = self.y_trans.notna()
        self.options: dict[str, list[str]] = {}
        for spec in self.specs:
            name = spec["name"]
            opts = ["x"]
            if spec["type"] not in ("Dicotômica", "Código alocado"):
                raw = pd.to_numeric(manager.df[name], errors="coerce")
                active = raw[self.manager.active_mask()].dropna()
                if len(active) and (active > 0).all():
                    opts.extend(["ln(x)", "1/x"])
            self.options[name] = opts
        self.total_specs = 1
        for opts in self.options.values():
            self.total_specs *= (1 + len(opts))
        self.total_specs -= 1

    def _transform(self, name: str, transformation: str) -> pd.Series:
        key = f"{name}::{transformation}"
        if key not in self._cache:
            try:
                self._cache[key] = transform_series(self.manager.df[name], transformation).astype(float)
            except (ValueError, TypeError):
                self._cache[key] = pd.Series(np.nan, index=self.manager.df.index, dtype=float)
        return self._cache[key]

    def _check_cancel(self) -> None:
        if self.cancel and self.cancel():
            self._cancel_requested = True
            raise SearchCancelled()

    def _notify(self, message: str) -> None:
        if self.progress:
            self.progress(self._tested, max(self._total_hint, 1), message)

    def _fit(self, chosen: Sequence[tuple[str, str]]) -> Optional[SearchResult]:
        self._check_cancel()
        if not chosen:
            return None
        columns: list[pd.Series] = []
        names: list[str] = []
        valid = pd.Series(True, index=self.manager.df.index)
        for name, transformation in chosen:
            series = self._transform(name, transformation)
            columns.append(series)
            names.append(transformation_label(name, transformation))
            valid &= series.notna()
        valid &= self.y_valid
        mask = valid.to_numpy() & self.manager.active_mask()
        n = int(mask.sum())
        k = len(chosen)
        if n < k + 2:
            self._tested += 1
            self._notify("Testando equações...")
            return None
        x_values = np.column_stack([c.to_numpy(dtype=float)[mask] for c in columns])
        y_values = self.y_trans.to_numpy(dtype=float)[mask]
        if np.linalg.matrix_rank(np.column_stack([np.ones(n), x_values])) < k + 1:
            self._tested += 1
            self._notify("Testando equações...")
            return None
        try:
            results = sm.OLS(y_values, sm.add_constant(x_values, has_constant="add")).fit()
        except Exception:
            self._tested += 1
            self._notify("Testando equações...")
            return None
        if not np.isfinite(results.params).all():
            self._tested += 1
            self._notify("Testando equações...")
            return None
        params = np.asarray(results.params, dtype=float)
        bse = np.asarray(results.bse, dtype=float)
        pvalues = np.asarray(results.pvalues, dtype=float)
        terms = [format_coefficient(params[0])]
        for beta, display in zip(params[1:], names):
            sign = "+" if beta >= 0 else "−"
            terms.append(f"{sign} {format_coefficient(abs(beta))}·{display}")
        lhs = transformation_label(self.manager.y_column, self.manager.y_transform)
        equation = f"{lhs} = " + " ".join(terms)
        worst = float(np.nanmax(pvalues[1:])) if len(pvalues) > 1 else float("nan")
        inverted: list[str] = []
        for (name, _transformation), beta in zip(chosen, params[1:]):
            expected = int(self.manager.x_config.get(name, {}).get("expected_sign", 0))
            if (expected > 0 and beta < 0) or (expected < 0 and beta > 0):
                inverted.append(name)
        signs = "ok" if not inverted else "invertido: " + ", ".join(inverted)
        has_code = any(self.manager.column_types.get(name) == "Código alocado" for name, _ in chosen)
        degree = provisional_degree(n, k, worst, float(results.f_pvalue), has_code)
        spec = {
            "y": self.manager.y_column,
            "y_transform": self.manager.y_transform,
            "x": [
                {
                    "name": name,
                    "type": self.manager.column_types.get(name, "Quantitativa"),
                    "transformation": transformation,
                    "expected_sign": int(self.manager.x_config.get(name, {}).get("expected_sign", 0)),
                }
                for name, transformation in chosen
            ],
        }
        coefficients = [{"name": "const", "estimate": float(params[0]), "se": float(bse[0]),
                         "p": float(pvalues[0])}]
        for (name, transformation), display, beta, se, p in zip(chosen, names, params[1:], bse[1:], pvalues[1:]):
            coefficients.append({"name": display, "source": name, "transformation": transformation,
                                 "estimate": float(beta), "se": float(se), "p": float(p)})
        result = SearchResult(
            spec=spec,
            equation=equation,
            r2=float(results.rsquared),
            r2_adj=float(results.rsquared_adj),
            f_p=float(results.f_pvalue),
            worst_p=worst,
            signs=signs,
            n=n,
            degree=degree,
            has_allocated_code=has_code,
            coefficients=coefficients,
        )
        self._tested += 1
        self._notify("Testando equações...")
        return result

    def run(self) -> SearchOutcome:
        if self.total_specs <= self.MAX_SPECS:
            self._total_hint = self.total_specs
            results = self._run_exhaustive()
            mode = "completa"
            cancelled = self._cancel_requested
        else:
            self._total_hint = self.MAX_SIMPLIFIED_FITS
            results = self._run_simplified()
            mode = "simplificada"
            cancelled = self._cancel_requested
        results.sort(key=lambda r: (r.r2_adj, r.r2, r.n), reverse=True)
        return SearchOutcome(
            results=results[: self.TOP_N],
            tested=self._tested,
            mode=mode,
            total_specs=self.total_specs,
            cancelled=cancelled,
        )

    def _run_exhaustive(self) -> list[SearchResult]:
        results: list[SearchResult] = []
        names = [s["name"] for s in self.specs]
        for size in range(1, len(names) + 1):
            for subset in itertools.combinations(names, size):
                option_lists = [self.options[name] for name in subset]
                for choice in itertools.product(*option_lists):
                    self._check_cancel()
                    result = self._fit(list(zip(subset, choice)))
                    if result is not None:
                        results.append(result)
        return results

    def _run_simplified(self) -> list[SearchResult]:
        results: list[SearchResult] = []
        names = [s["name"] for s in self.specs]
        chosen: list[tuple[str, str]] = []
        current = self._fit_intercept_only()
        budget = self.MAX_SIMPLIFIED_FITS
        used = 0
        # Forward passo a passo, escolhendo o menor p-valor do termo novo.
        while len(chosen) < min(5, max(1, (len(self.active_positions) // 3) - 1)):
            self._check_cancel()
            if used >= budget - 1:
                break
            candidates: list[tuple[float, str, Any]] = []
            remaining = [n for n in names if n not in [c[0] for c in chosen]]
            for name in remaining:
                if used >= budget - 1:
                    break
                trial = chosen + [(name, "x")]
                fit = self._fit(trial)
                used += 1
                if fit is not None:
                    candidates.append((fit.worst_p, name, fit))
                    results.append(fit)
            if not candidates:
                break
            candidates.sort(key=lambda item: item[0])
            best_p, best_name, best_fit = candidates[0]
            if best_p > 0.10 or not np.isfinite(best_p):
                break
            # Evita entrar em modelo saturado.
            if best_fit.n <= len(best_fit.spec["x"]) + 1:
                break
            chosen.append((best_name, "x"))
            current = best_fit
        if chosen:
            base = self._fit(chosen)
            if base is not None:
                results.append(base)
        # Depois, testa as transformações das variáveis mantidas.
        if chosen:
            remaining_budget = max(0, budget - used)
            total_combos = 1
            for name, _ in chosen:
                total_combos *= len(self.options[name])
            if total_combos <= remaining_budget:
                for choice in itertools.product(*[self.options[name] for name, _ in chosen]):
                    self._check_cancel()
                    result = self._fit(list(zip([c[0] for c in chosen], choice)))
                    if result is not None:
                        results.append(result)
            else:
                current_choice = [t for _, t in chosen]
                improved = True
                while improved and used < budget:
                    self._check_cancel()
                    improved = False
                    best_local = None
                    best_score = max((r.r2_adj for r in results), default=-math.inf)
                    for idx, (name, _) in enumerate(chosen):
                        for option in self.options[name]:
                            if option == current_choice[idx] or used >= budget:
                                continue
                            trial_choice = list(current_choice)
                            trial_choice[idx] = option
                            fit = self._fit(list(zip([c[0] for c in chosen], trial_choice)))
                            used += 1
                            if fit is not None:
                                results.append(fit)
                                if fit.r2_adj > best_score + 1e-9:
                                    best_score = fit.r2_adj
                                    best_local = trial_choice
                    if best_local is not None:
                        current_choice = best_local
                        improved = True
        return results

    def _fit_intercept_only(self) -> Optional[SearchResult]:
        valid = self.y_valid.to_numpy() & self.manager.active_mask()
        n = int(valid.sum())
        if n < 2:
            return None
        y = self.y_trans.to_numpy(dtype=float)[valid]
        results = sm.OLS(y, np.ones((n, 1))).fit()
        return SearchResult(
            spec={"y": self.manager.y_column, "y_transform": self.manager.y_transform, "x": []},
            equation=f"{transformation_label(self.manager.y_column, self.manager.y_transform)} = "
                     f"{format_coefficient(float(results.params[0]))}",
            r2=float(results.rsquared), r2_adj=float(results.rsquared_adj),
            f_p=float("nan"), worst_p=float("nan"), signs="ok", n=n,
            degree="", has_allocated_code=False,
        )
