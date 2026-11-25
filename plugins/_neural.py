"""Treinamento de rede neural para o plugin do SisAvalia.

A implementação usa scikit-learn MLPRegressor para não acrescentar TensorFlow
ou PyTorch ao pacote. O resultado é uma ferramenta de apoio: a NBR 14653-2 não
prescreve rede neural como método de enquadramento.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler


@dataclass
class NeuralConfig:
    hidden_layers: tuple[int, ...] = (32, 16)
    activation: str = "relu"
    solver: str = "adam"
    alpha: float = 0.0001
    learning_rate_init: float = 0.001
    learning_rate: str = "constant"
    max_iter: int = 1500
    early_stopping: bool = True
    validation_fraction: float = 0.15
    n_iter_no_change: int = 20
    test_size: float = 0.25
    standardize: bool = True
    random_state: int = 42
    use_current_transforms: bool = False


@dataclass
class NeuralResult:
    config: NeuralConfig
    n_total: int
    n_train: int
    n_test: int
    train_r2: float
    test_r2: float
    train_mae: float
    test_mae: float
    train_rmse: float
    test_rmse: float
    train_mape: float
    test_mape: float
    baseline_test_r2: float
    baseline_test_rmse: float
    loss_curve: list[float]
    test_observed: list[float]
    test_predicted: list[float]
    test_labels: list[str]
    training_iterations: int
    warnings: list[str] = field(default_factory=list)


def parse_layers(text: str) -> tuple[int, ...]:
    parts = [p.strip() for p in str(text).replace(";", ",").split(",") if p.strip()]
    if not parts:
        raise ValueError("Informe pelo menos uma camada oculta.")
    layers = tuple(int(p) for p in parts)
    if any(n < 1 or n > 512 for n in layers):
        raise ValueError("Cada camada deve ter entre 1 e 512 neurônios.")
    if len(layers) > 4:
        raise ValueError("Use no máximo quatro camadas ocultas.")
    return layers


def _mape(observed: np.ndarray, predicted: np.ndarray) -> float:
    mask = np.abs(observed) > 1e-12
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((observed[mask] - predicted[mask]) / observed[mask])) * 100.0)


def prepare_xy(frame: pd.DataFrame, y: str, x_columns: Sequence[str],
               *, active: Sequence[bool] | None = None,
               use_transforms: bool = False,
               transforms: dict[str, str] | None = None,
               y_transform: str = "x") -> tuple[np.ndarray, np.ndarray, list[str]]:
    from core.data_manager import transform_value
    if y not in frame.columns:
        raise ValueError("A coluna Y escolhida não existe.")
    missing = [c for c in x_columns if c not in frame.columns]
    if missing:
        raise ValueError("Algumas colunas X não existem: " + ", ".join(missing))
    if not x_columns:
        raise ValueError("Escolha pelo menos uma variável independente.")
    rows = []
    labels = []
    for position in range(len(frame)):
        if active is not None and not active[position]:
            continue
        raw_y = frame.iloc[position][y]
        if pd.isna(raw_y):
            continue
        xs: list[float] = []
        ok = True
        for name in x_columns:
            raw = frame.iloc[position][name]
            if pd.isna(raw):
                ok = False
                break
            try:
                value = float(raw)
                if use_transforms:
                    value = transform_value(value, (transforms or {}).get(name, "x"))
                xs.append(value)
            except (TypeError, ValueError):
                ok = False
                break
        if not ok:
            continue
        try:
            target = float(raw_y)
            if use_transforms:
                target = transform_value(target, y_transform)
        except (TypeError, ValueError):
            continue
        rows.append(xs)
        labels.append(str(position + 1))
    if len(rows) < 8:
        raise ValueError("São necessários pelo menos 8 imóveis completos para dividir treino e teste.")
    return np.asarray(rows, dtype=float), np.asarray(
        [float(frame.iloc[int(label) - 1][y]) if not use_transforms
         else transform_value(float(frame.iloc[int(label) - 1][y]), y_transform)
         for label in labels], dtype=float
    ), labels


def train_neural(frame: pd.DataFrame, y: str, x_columns: Sequence[str],
                 config: NeuralConfig, *, active: Sequence[bool] | None = None,
                 transforms: dict[str, str] | None = None,
                 y_transform: str = "x") -> NeuralResult:
    X, Y, labels = prepare_xy(
        frame, y, x_columns, active=active, use_transforms=config.use_current_transforms,
        transforms=transforms, y_transform=y_transform,
    )
    if config.test_size < 0.10 or config.test_size > 0.40:
        raise ValueError("O teste deve ficar entre 10% e 40%.")
    X_train, X_test, y_train, y_test, lab_train, lab_test = train_test_split(
        X, Y, labels, test_size=config.test_size, random_state=config.random_state,
    )
    scaler_x = StandardScaler() if config.standardize else None
    scaler_y = StandardScaler() if config.standardize else None
    Xt = scaler_x.fit_transform(X_train) if scaler_x else X_train
    Xv = scaler_x.transform(X_test) if scaler_x else X_test
    yt = scaler_y.fit_transform(y_train.reshape(-1, 1)).ravel() if scaler_y else y_train
    model = MLPRegressor(
        hidden_layer_sizes=config.hidden_layers,
        activation=config.activation,
        solver=config.solver,
        alpha=config.alpha,
        learning_rate_init=config.learning_rate_init,
        learning_rate=config.learning_rate,
        max_iter=config.max_iter,
        early_stopping=config.early_stopping,
        validation_fraction=config.validation_fraction if config.early_stopping else 0.1,
        n_iter_no_change=config.n_iter_no_change,
        random_state=config.random_state,
    )
    model.fit(Xt, yt)
    train_pred = model.predict(Xt)
    test_pred = model.predict(Xv)
    if scaler_y:
        train_pred = scaler_y.inverse_transform(train_pred.reshape(-1, 1)).ravel()
        test_pred = scaler_y.inverse_transform(test_pred.reshape(-1, 1)).ravel()
    baseline = LinearRegression().fit(X_train, y_train)
    base_pred = baseline.predict(X_test)
    warnings: list[str] = []
    if len(y_test) < 5:
        warnings.append("O conjunto de teste tem menos de 5 imóveis; os indicadores são frágeis.")
    if model.n_iter_ >= config.max_iter:
        warnings.append("A rede atingiu o número máximo de épocas; aumente as épocas ou simplifique a rede.")
    if not math.isfinite(float(np.nanmean(test_pred))):
        warnings.append("A rede gerou valores inválidos; confira os dados e a padronização.")
    return NeuralResult(
        config=config,
        n_total=len(Y),
        n_train=len(y_train),
        n_test=len(y_test),
        train_r2=float(r2_score(y_train, train_pred)),
        test_r2=float(r2_score(y_test, test_pred)),
        train_mae=float(mean_absolute_error(y_train, train_pred)),
        test_mae=float(mean_absolute_error(y_test, test_pred)),
        train_rmse=float(math.sqrt(mean_squared_error(y_train, train_pred))),
        test_rmse=float(math.sqrt(mean_squared_error(y_test, test_pred))),
        train_mape=_mape(y_train, train_pred),
        test_mape=_mape(y_test, test_pred),
        baseline_test_r2=float(r2_score(y_test, base_pred)),
        baseline_test_rmse=float(math.sqrt(mean_squared_error(y_test, base_pred))),
        loss_curve=[float(v) for v in model.loss_curve_],
        test_observed=[float(v) for v in y_test],
        test_predicted=[float(v) for v in test_pred],
        test_labels=[str(v) for v in lab_test],
        training_iterations=int(model.n_iter_),
        warnings=warnings,
    )
