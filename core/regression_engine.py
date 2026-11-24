"""Regressão linear múltipla por mínimos quadrados ordinários (OLS)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.outliers_influence import variance_inflation_factor

from .data_manager import DataManager, transform_series, transform_value, transformation_label
from .formatting import format_coefficient, format_number, format_pvalue, is_missing, parse_number


class ModelError(ValueError):
    """Erro de modelo com mensagem própria para o usuário."""


@dataclass
class Prediction:
    point: float
    ci_low: float
    ci_high: float
    pi_low: float
    pi_high: float
    se_mean: float
    se_prediction: float
    amplitude_pct: float
    precision_degree: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "point": self.point,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "pi_low": self.pi_low,
            "pi_high": self.pi_high,
            "se_mean": self.se_mean,
            "se_prediction": self.se_prediction,
            "amplitude_pct": self.amplitude_pct,
            "precision_degree": self.precision_degree,
        }


def precision_degree(amplitude_pct: float) -> str:
    if not math.isfinite(amplitude_pct):
        return "Fora de norma"
    if amplitude_pct <= 30.0:
        return "III"
    if amplitude_pct <= 40.0:
        return "II"
    if amplitude_pct <= 50.0:
        return "I"
    return "Fora de norma"


def inverse_y_transform(values: np.ndarray, transformation: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if transformation == "ln(x)":
        return np.exp(arr)
    if transformation == "1/x":
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(arr != 0, 1.0 / arr, np.nan)
    if transformation == "√x":
        return np.where(arr >= 0, arr ** 2, np.nan)
    return arr


def y_transform_is_decreasing(transformation: str) -> bool:
    return transformation == "1/x"


def original_scale_interval(low_transformed: float, high_transformed: float,
                            transformation: str) -> tuple[float, float]:
    low = float(inverse_y_transform(np.array([low_transformed]), transformation)[0])
    high = float(inverse_y_transform(np.array([high_transformed]), transformation)[0])
    if y_transform_is_decreasing(transformation):
        low, high = high, low
    return low, high


@dataclass
class FitResult:
    spec: dict[str, Any]
    n_active: int
    n_obs: int
    used_positions: list[int]
    dropped_positions: list[int]
    used_row_ids: list[int]
    y_name: str
    y_transform: str
    x_names: list[str]
    x_transforms: list[str]
    design_names: list[str]
    params: pd.Series
    bse: pd.Series
    tvalues: pd.Series
    pvalues: pd.Series
    rsquared: float
    rsquared_adj: float
    fvalue: float
    f_pvalue: float
    mse_resid: float
    scale: float
    df_model: int
    df_resid: int
    anova_rows: list[dict[str, Any]]
    covariance: np.ndarray
    design_matrix: pd.DataFrame
    y_transformed: pd.Series
    fitted_transformed: np.ndarray
    residuals: np.ndarray
    fitted_original: np.ndarray
    observed_original: np.ndarray
    standardized_residuals: np.ndarray
    studentized_residuals: np.ndarray
    cooks_distance: np.ndarray
    leverage: np.ndarray
    mahalanobis: np.ndarray
    mahalanobis_cutoff: float
    mahalanobis_approximate: bool
    correlation: pd.DataFrame
    vif: dict[str, float]
    equation: str
    warnings: list[str]
    labels: list[str]
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def k(self) -> int:
        return len(self.x_names)

    @property
    def worst_regressor_p(self) -> float:
        values = [float(self.pvalues.get(name, np.nan)) for name in self.design_names if name != "const"]
        values = [v for v in values if math.isfinite(v)]
        return max(values) if values else float("nan")

    @property
    def coeff_table(self) -> pd.DataFrame:
        rows = []
        for name in ["const"] + self.design_names:
            display = "Intercepto" if name == "const" else name
            rows.append({
                "Variável": display,
                "Estimativa": float(self.params[name]),
                "Erro padrão": float(self.bse[name]),
                "t": float(self.tvalues[name]),
                "p-valor": float(self.pvalues[name]),
            })
        return pd.DataFrame(rows)

    def predicted_transformed_at(self, values: dict[str, Any]) -> tuple[float, np.ndarray]:
        row = [1.0]
        for name, transform in zip(self.x_names, self.x_transforms):
            if name not in values or is_missing(values[name]):
                raise ModelError(f"Informe o valor de “{name}”.")
            raw = parse_number(values[name])
            row.append(transform_value(raw, transform))
        vector = np.asarray(row, dtype=float)
        if not np.all(np.isfinite(vector)):
            raise ModelError("Há valor inválido nos campos do avaliando.")
        eta = float(vector @ self.params.values)
        return eta, vector

    def predict_at(self, values: dict[str, Any], level: float = 0.80) -> Prediction:
        eta, vector = self.predicted_transformed_at(values)
        alpha = 1.0 - level
        tcrit = float(stats.t.ppf(1.0 - alpha / 2.0, self.df_resid))
        var_mean = float(vector @ self.covariance @ vector)
        se_mean = math.sqrt(max(var_mean, 0.0))
        se_pred = math.sqrt(max(self.scale ** 2 + var_mean, 0.0))
        eta_low, eta_high = eta - tcrit * se_mean, eta + tcrit * se_mean
        pred_low_t, pred_high_t = eta - tcrit * se_pred, eta + tcrit * se_pred
        point = float(inverse_y_transform(np.array([eta]), self.y_transform)[0])
        ci_low, ci_high = original_scale_interval(eta_low, eta_high, self.y_transform)
        pi_low, pi_high = original_scale_interval(pred_low_t, pred_high_t, self.y_transform)
        if abs(point) > 0 and math.isfinite(point):
            amplitude = (ci_high - ci_low) / abs(point) * 100.0
        else:
            amplitude = float("inf")
        return Prediction(
            point=point,
            ci_low=ci_low,
            ci_high=ci_high,
            pi_low=pi_low,
            pi_high=pi_high,
            se_mean=se_mean,
            se_prediction=se_pred,
            amplitude_pct=float(amplitude),
            precision_degree=precision_degree(float(amplitude)),
        )

    def prediction_from_eta(self, eta: float, vector: np.ndarray, level: float = 0.80) -> Prediction:
        alpha = 1.0 - level
        tcrit = float(stats.t.ppf(1.0 - alpha / 2.0, self.df_resid))
        var_mean = float(vector @ self.covariance @ vector)
        se_mean = math.sqrt(max(var_mean, 0.0))
        se_pred = math.sqrt(max(self.scale ** 2 + var_mean, 0.0))
        ci_low, ci_high = original_scale_interval(eta - tcrit * se_mean, eta + tcrit * se_mean, self.y_transform)
        pi_low, pi_high = original_scale_interval(eta - tcrit * se_pred, eta + tcrit * se_pred, self.y_transform)
        point = float(inverse_y_transform(np.array([eta]), self.y_transform)[0])
        amplitude = (ci_high - ci_low) / abs(point) * 100.0 if abs(point) > 0 else float("inf")
        return Prediction(point, ci_low, ci_high, pi_low, pi_high, se_mean, se_pred,
                          float(amplitude), precision_degree(float(amplitude)))

    def estimate_at(self, values: dict[str, Any]) -> float:
        return self.predict_at(values).point

    def transformed_row(self, values: dict[str, Any]) -> np.ndarray:
        return self.predicted_transformed_at(values)[1]

    def elasticity_rows(self, values: dict[str, Any]) -> list[dict[str, Any]]:
        """Elasticidades no ponto, ou diferença entre códigos para dicotômica."""
        result: list[dict[str, Any]] = []
        base = dict(values)
        for name, transform, design_display in zip(self.x_names, self.x_transforms, self.design_names):
            raw = parse_number(base[name])
            display = name.replace("_", " ")
            column_type = self.extra.get("x_types", {}).get(name, "Quantitativa")
            sign = self.extra.get("expected_signs", {}).get(name, 0)
            if column_type == "Dicotômica":
                low_high = self.extra.get("dichotomous_values", {}).get(name)
                if not low_high or len(low_high) < 2:
                    result.append({
                        "name": name, "display": display, "kind": "dicotômica",
                        "text": f"{display}: não há dois códigos nos imóveis ligados para comparar.",
                        "inverted": self._inverted(name), "expected_sign": sign,
                    })
                    continue
                low, high = low_high[0], low_high[1]
                low_values = dict(base)
                high_values = dict(base)
                low_values[name] = low
                high_values[name] = high
                y_low = self.estimate_at(low_values)
                y_high = self.estimate_at(high_values)
                if abs(y_low) > 0:
                    diff = (y_high - y_low) / abs(y_low) * 100.0
                    direction = "subir" if diff >= 0 else "descer"
                    text = (
                        f"Passar de {format_number(low, 0)} para {format_number(high, 0)} em "
                        f"{display} faz a estimativa {direction} cerca de {format_number(abs(diff), 1)}%, "
                        "com o resto parado."
                    )
                else:
                    text = f"{display}: não foi possível calcular a diferença percentual."
                result.append({
                    "name": name, "display": display, "kind": "dicotômica",
                    "text": text, "inverted": self._inverted(name),
                    "expected_sign": sign, "difference_pct": diff if abs(y_low) > 0 else float("nan"),
                })
                continue
            # Elasticidade numérica: 1% em X, resto parado.
            step = 0.01
            if raw == 0:
                low_values = dict(base)
                high_values = dict(base)
                low_values[name] = raw + 0.5 * step
                high_values[name] = raw + 1.5 * step
                base_y = self.estimate_at(base)
                if abs(base_y) <= 0:
                    elasticity = float("nan")
                else:
                    dy = (self.estimate_at(high_values) - self.estimate_at(low_values)) / step
                    elasticity = dy * 0.01 / base_y
            else:
                low_values = dict(base)
                high_values = dict(base)
                low_values[name] = raw * (1.0 - step)
                high_values[name] = raw * (1.0 + step)
                y_low = self.estimate_at(low_values)
                y_high = self.estimate_at(high_values)
                y0 = self.estimate_at(base)
                elasticity = ((y_high - y_low) / (2.0 * step)) / y0 if abs(y0) > 0 else float("nan")
            if math.isfinite(elasticity):
                direction = "sobe" if elasticity >= 0 else "desce"
                text = (
                    f"Se {display} sobe 1% e o resto fica parado, o valor {direction} "
                    f"cerca de {format_number(abs(elasticity), 4)}%."
                )
            else:
                text = f"{display}: não foi possível calcular a elasticidade neste ponto."
            result.append({
                "name": name, "display": display, "kind": "elástica",
                "text": text, "inverted": self._inverted(name),
                "expected_sign": sign, "elasticity": elasticity,
            })
        return result

    def _inverted(self, name: str) -> bool:
        expected = self.extra.get("expected_signs", {}).get(name, 0)
        coefficient = float(self.params.get(name, 0.0))
        return (expected > 0 and coefficient < 0) or (expected < 0 and coefficient > 0)

    def curve(self, variable: str, base_values: dict[str, Any], points: int = 120
              ) -> pd.DataFrame:
        if variable not in self.x_names:
            raise ModelError("Escolha uma variável do modelo para desenhar a curva.")
        idx = self.x_names.index(variable)
        transform = self.x_transforms[idx]
        raw_series = self.extra.get("raw_x", {}).get(variable)
        if raw_series is None or len(raw_series) == 0:
            raise ModelError("Sem dados para desenhar a curva.")
        raw = np.asarray(raw_series, dtype=float)
        low, high = float(np.nanmin(raw)), float(np.nanmax(raw))
        if not math.isfinite(low) or not math.isfinite(high) or high <= low:
            raise ModelError("A variável não tem faixa suficiente para a curva.")
        margin = (high - low) * 0.05
        grid = np.linspace(low - margin, high + margin, max(points, 20))
        if transform in ("ln(x)", "1/x"):
            grid = grid[grid > 0]
        if transform == "√x":
            grid = grid[grid >= 0]
        xs: list[float] = []
        ys: list[float] = []
        for value in grid:
            vals = dict(base_values)
            vals[variable] = float(value)
            try:
                xs.append(float(value))
                ys.append(self.estimate_at(vals))
            except (ModelError, ValueError, OverflowError):
                continue
        return pd.DataFrame({"x": xs, "y": ys})

    def to_model_record(self) -> dict[str, Any]:
        return {
            "spec": self.spec,
            "equation": self.equation,
            "n_obs": self.n_obs,
            "n_active": self.n_active,
            "dropped": len(self.dropped_positions),
            "r2": self.rsquared,
            "r2_adj": self.rsquared_adj,
            "f": self.fvalue,
            "f_p": self.f_pvalue,
            "worst_p": self.worst_regressor_p,
            "coefficients": [
                {"name": name, "estimate": float(self.params[name]), "se": float(self.bse[name]),
                 "t": float(self.tvalues[name]), "p": float(self.pvalues[name])}
                for name in ["const"] + self.design_names
            ],
            "used_row_ids": list(self.used_row_ids),
            "x_names": list(self.x_names),
            "x_transforms": list(self.x_transforms),
            "y_name": self.y_name,
            "y_transform": self.y_transform,
        }


class RegressionEngine:
    """Ajusta o modelo OLS a partir do estado do DataManager."""

    @staticmethod
    def fit(manager: DataManager, *, level: float = 0.80) -> FitResult:
        errors, _warnings = manager.validate()
        if errors:
            raise ModelError(" ".join(errors[:4]))
        if not manager.y_column:
            raise ModelError("Escolha a variável dependente (Y).")
        specs = manager.x_specs(True)
        if not specs:
            raise ModelError("Escolha pelo menos uma variável independente (X).")
        active_positions = [i for i, a in enumerate(manager.active) if a]
        used_positions: list[int] = []
        y_values: list[float] = []
        x_rows: list[list[float]] = []
        dropped: list[int] = []
        for pos in active_positions:
            row = manager.df.iloc[pos]
            if is_missing(row[manager.y_column]):
                dropped.append(pos)
                continue
            try:
                y_raw = float(row[manager.y_column])
                y_t = transform_value(y_raw, manager.y_transform)
                values = []
                ok = True
                for spec in specs:
                    raw = row[spec["name"]]
                    if is_missing(raw):
                        ok = False
                        break
                    values.append(transform_value(float(raw), spec["transformation"]))
                if not ok:
                    dropped.append(pos)
                    continue
            except (ValueError, TypeError, OverflowError, ZeroDivisionError):
                dropped.append(pos)
                continue
            used_positions.append(pos)
            y_values.append(y_t)
            x_rows.append(values)
        n_obs = len(used_positions)
        k = len(specs)
        if n_obs < k + 2:
            raise ModelError(
                f"Sobraram {n_obs} imóvel(is) completos para {k} variável(is) X. "
                "São necessários pelo menos dois imóveis a mais que o número de X. "
                "Reative imóveis, preencha vazios ou retire uma variável."
            )
        design_names = [transformation_label(s["name"], s["transformation"]) for s in specs]
        display_names: list[str] = []
        used: dict[str, int] = {}
        for original, display in zip([s["name"] for s in specs], design_names):
            used.setdefault(display, 0)
            used[display] += 1
            display_names.append(display if used[display] == 1 else f"{display} ({used[display]})")
        x_df = pd.DataFrame(x_rows, columns=display_names, dtype=float)
        if (x_df.nunique(dropna=True) <= 1).any():
            constant = [c for c in x_df.columns if x_df[c].nunique(dropna=True) <= 1]
            raise ModelError(
                "Uma variável não muda entre os imóveis ligados ("
                + ", ".join(constant)
                + "). Sem variação ela não pode explicar o valor."
            )
        y_series = pd.Series(y_values, dtype=float, name=manager.y_column)
        exog = sm.add_constant(x_df, has_constant="add")
        try:
            model = sm.OLS(y_series.to_numpy(dtype=float), exog.to_numpy(dtype=float))
            results = model.fit()
        except Exception as exc:
            raise ModelError(
                "Não foi possível calcular a regressão. Confira se há valores repetidos "
                "ou colunas com informação igual."
            ) from exc
        params = pd.Series(results.params, index=["const"] + display_names)
        bse = pd.Series(results.bse, index=["const"] + display_names)
        tvalues = pd.Series(results.tvalues, index=["const"] + display_names)
        pvalues = pd.Series(results.pvalues, index=["const"] + display_names)
        if not all(np.isfinite(params.values)):
            raise ModelError("O cálculo gerou coeficientes inválidos. Confira os dados.")
        ss_res = float(results.ssr)
        ss_total = float(((y_series - y_series.mean()) ** 2).sum())
        ss_model = ss_total - ss_res
        df_model = k
        df_resid = n_obs - k - 1
        ms_model = ss_model / df_model if df_model else float("nan")
        ms_resid = ss_res / df_resid if df_resid > 0 else float("nan")
        fvalue = float(results.fvalue) if df_model else float("nan")
        fpvalue = float(results.f_pvalue) if df_model else float("nan")
        if not math.isfinite(fvalue):
            fvalue = ms_model / ms_resid if ms_resid and math.isfinite(ms_resid) else float("nan")
        if not math.isfinite(fpvalue) and math.isfinite(fvalue):
            fpvalue = float(stats.f.sf(fvalue, df_model, df_resid))
        anova_rows = [
            {"Fonte": "Regressão", "SQ": ss_model, "GL": df_model,
             "QM": ms_model, "F": fvalue, "p-valor": fpvalue},
            {"Fonte": "Resíduo", "SQ": ss_res, "GL": df_resid,
             "QM": ms_resid, "F": float("nan"), "p-valor": float("nan")},
            {"Fonte": "Total", "SQ": ss_total, "GL": n_obs - 1,
             "QM": float("nan"), "F": float("nan"), "p-valor": float("nan")},
        ]
        fitted_t = np.asarray(results.fittedvalues, dtype=float)
        resid = np.asarray(results.resid, dtype=float)
        fitted_original = inverse_y_transform(fitted_t, manager.y_transform)
        observed_original = inverse_y_transform(y_series.to_numpy(dtype=float), manager.y_transform)
        scale = math.sqrt(max(float(results.mse_resid), 0.0))
        influence = results.get_influence()
        cooks = np.asarray(influence.cooks_distance[0], dtype=float)
        studentized = np.asarray(influence.resid_studentized_external, dtype=float)
        leverage = np.asarray(influence.hat_matrix_diag, dtype=float)
        standardized = resid / scale if scale > 0 else np.full_like(resid, np.nan)
        # Mahalanobis nas independentes, na forma transformada usada no modelo.
        x_matrix = x_df.to_numpy(dtype=float)
        p = x_matrix.shape[1]
        if n_obs > 1:
            center = x_matrix.mean(axis=0)
            cov = np.cov(x_matrix, rowvar=False, ddof=1)
            try:
                inv_cov = np.linalg.pinv(np.atleast_2d(cov))
                diff = x_matrix - center
                d2 = np.einsum("ij,jk,ik->i", diff, inv_cov, diff)
                d2 = np.maximum(d2, 0.0)
            except np.linalg.LinAlgError:
                d2 = np.zeros(n_obs)
        else:
            d2 = np.zeros(n_obs)
        mahal_approx = False
        if p > 0 and n_obs - p - 1 > 0:
            scale_beta = (n_obs - 1) ** 2 / n_obs
            cutoff_d2 = float(scale_beta * stats.beta.ppf(0.95, p / 2.0, (n_obs - p - 1) / 2.0))
        else:
            cutoff_d2 = float(stats.chi2.ppf(0.95, max(p, 1)))
            mahal_approx = True
        mahalanobis = np.sqrt(np.maximum(d2, 0.0))
        cutoff = math.sqrt(max(cutoff_d2, 0.0))
        corr = x_df.corr()
        vif: dict[str, float] = {}
        exog_values = exog.to_numpy(dtype=float)
        for i, name in enumerate(display_names, start=1):
            try:
                value = float(variance_inflation_factor(exog_values, i))
                vif[name] = value if math.isfinite(value) else float("inf")
            except Exception:
                vif[name] = float("nan")
        equation = RegressionEngine.equation_text(manager, specs, params)
        warnings: list[str] = []
        for spec in specs:
            display = transformation_label(spec["name"], spec["transformation"])
            expected = int(spec.get("expected_sign", 0))
            coefficient = float(params.get(display, 0.0))
            if expected > 0 and coefficient < 0:
                warnings.append(
                    f"Sinal invertido em {display}: você esperava que o valor subisse quando "
                    "esta variável aumenta, mas o coeficiente ficou negativo. Nada foi forçado."
                )
            elif expected < 0 and coefficient > 0:
                warnings.append(
                    f"Sinal invertido em {display}: você esperava que o valor descesse quando "
                    "esta variável aumenta, mas o coeficiente ficou positivo. Nada foi forçado."
                )
        if results.rsquared < 0.75:
            warnings.append(
                "A equação explica pouco da variação (R² abaixo de 0,75). "
                "Vale revisar as variáveis e os imóveis fora da curva."
            )
        raw_x: dict[str, np.ndarray] = {}
        for spec in specs:
            raw_x[spec["name"]] = pd.to_numeric(manager.df[spec["name"]], errors="coerce").to_numpy(dtype=float)[manager.active_mask()]
        x_types = {s["name"]: s["type"] for s in specs}
        signs = {s["name"]: s["expected_sign"] for s in specs}
        dichotomous_values: dict[str, list[float]] = {}
        for spec in specs:
            if spec["type"] == "Dicotômica":
                vals = pd.to_numeric(manager.df[spec["name"]], errors="coerce")[manager.active_mask()].dropna()
                dichotomous_values[spec["name"]] = sorted(float(v) for v in vals.unique())[:2]
        fit = FitResult(
            spec=manager.model_spec(),
            n_active=manager.n_active,
            n_obs=n_obs,
            used_positions=used_positions,
            dropped_positions=dropped,
            used_row_ids=[manager.row_ids[i] for i in used_positions],
            y_name=manager.y_column,
            y_transform=manager.y_transform,
            x_names=[s["name"] for s in specs],
            x_transforms=[s["transformation"] for s in specs],
            design_names=display_names,
            params=params,
            bse=bse,
            tvalues=tvalues,
            pvalues=pvalues,
            rsquared=float(results.rsquared),
            rsquared_adj=float(results.rsquared_adj),
            fvalue=fvalue,
            f_pvalue=fpvalue,
            mse_resid=float(results.mse_resid),
            scale=scale,
            df_model=df_model,
            df_resid=df_resid,
            anova_rows=anova_rows,
            covariance=np.asarray(results.cov_params(), dtype=float),
            design_matrix=exog,
            y_transformed=y_series,
            fitted_transformed=fitted_t,
            residuals=resid,
            fitted_original=np.asarray(fitted_original, dtype=float),
            observed_original=np.asarray(observed_original, dtype=float),
            standardized_residuals=np.asarray(standardized, dtype=float),
            studentized_residuals=studentized,
            cooks_distance=cooks,
            leverage=leverage,
            mahalanobis=mahalanobis,
            mahalanobis_cutoff=cutoff,
            mahalanobis_approximate=mahal_approx,
            correlation=corr,
            vif=vif,
            equation=equation,
            warnings=warnings,
            labels=[manager.label_for_row(i) for i in used_positions],
            extra={
                "x_types": x_types,
                "expected_signs": signs,
                "dichotomous_values": dichotomous_values,
                "raw_x": raw_x,
                "level": level,
                "y_label": manager.y_column,
            },
        )
        return fit

    @staticmethod
    def equation_text(manager: DataManager, specs: list[dict[str, Any]], params: pd.Series) -> str:
        def display_transform(name: str, transform: str) -> str:
            return transformation_label(name, transform)
        lhs = display_transform(manager.y_column or "Y", manager.y_transform)
        terms: list[str] = []
        intercept = float(params.get("const", 0.0))
        terms.append(format_coefficient(intercept))
        for spec in specs:
            display = transformation_label(spec["name"], spec["transformation"])
            beta = float(params.get(display, 0.0))
            sign = "+" if beta >= 0 else "−"
            terms.append(f"{sign} {format_coefficient(abs(beta))}·{display}")
        return f"{lhs} = " + " ".join(terms)
