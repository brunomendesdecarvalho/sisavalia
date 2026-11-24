"""K-médias e análise de componentes principais (PCA)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from .data_manager import DataManager, TEXT_TYPE
from .formatting import format_number


class MultivariateError(ValueError):
    """Erro das análises multivariadas, com mensagem para o usuário."""


@dataclass
class KMeansResult:
    labels: np.ndarray
    centers: np.ndarray
    inertia: float
    k: int
    variables: list[str]
    used_positions: list[int]
    scaled: bool
    scores_2d: np.ndarray
    axis_labels: tuple[str, str]
    elbow_k: list[int]
    elbow_inertia: list[float]
    explained_2d: Optional[np.ndarray] = None

    def cluster_sizes(self) -> dict[int, int]:
        return {int(c): int(np.sum(self.labels == c)) for c in sorted(set(int(x) for x in self.labels))}


@dataclass
class PCAResult:
    scores: np.ndarray
    loadings: pd.DataFrame
    explained: np.ndarray
    cumulative: np.ndarray
    variables: list[str]
    used_positions: list[int]
    means: np.ndarray
    n_obs: int

    def biplot_data(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return self.scores[:, :2], self.loadings.iloc[:, :2].to_numpy(), self.explained[:2]


def _numeric_matrix(manager: DataManager, variables: list[str], *, active_only: bool = True
                    ) -> tuple[np.ndarray, list[int]]:
    if not variables:
        raise MultivariateError("Escolha pelo menos duas variáveis numéricas.")
    if len(set(variables)) != len(variables):
        raise MultivariateError("Uma variável foi escolhida duas vezes.")
    for name in variables:
        if name not in manager.df.columns:
            raise MultivariateError(f"A variável “{name}” não existe.")
        if manager.column_types.get(name) == TEXT_TYPE:
            raise MultivariateError(f"A coluna de texto “{name}” não pode ser usada aqui.")
    subset = manager.df[variables].apply(pd.to_numeric, errors="coerce")
    mask = subset.notna().all(axis=1)
    if active_only:
        mask &= pd.Series(manager.active, index=subset.index)
    positions = [int(i) for i in subset.index[mask]]
    if len(positions) < 3:
        raise MultivariateError(
            "São necessários pelo menos três imóveis com todas as variáveis escolhidas preenchidas."
        )
    matrix = subset.loc[mask, variables].to_numpy(dtype=float)
    return matrix, positions


def run_kmeans(manager: DataManager, variables: list[str], k: int,
               standardize: bool = True) -> KMeansResult:
    matrix, positions = _numeric_matrix(manager, variables, active_only=True)
    n = len(positions)
    if n < 3:
        raise MultivariateError("Amostra pequena para K-médias.")
    if k < 2:
        raise MultivariateError("Escolha pelo menos 2 grupos.")
    if k >= n:
        raise MultivariateError("O número de grupos precisa ser menor que o número de imóveis.")
    if np.std(matrix, axis=0).min() == 0:
        raise MultivariateError("Uma variável escolhida não tem variação. Retire-a.")
    scaled = StandardScaler().fit_transform(matrix) if standardize else matrix.copy()
    try:
        model = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = model.fit_predict(scaled)
    except Exception as exc:
        raise MultivariateError("Não foi possível formar os grupos com esta configuração.") from exc
    # Gráfico 2D: duas variáveis ou as duas primeiras componentes.
    explained_2d = None
    if len(variables) == 2:
        scores_2d = scaled
        axis_labels = (variables[0], variables[1])
    else:
        pca = PCA(n_components=2, random_state=42)
        scores_2d = pca.fit_transform(scaled)
        explained_2d = pca.explained_variance_ratio_
        axis_labels = ("Componente 1", "Componente 2")
    max_k = min(10, n - 1)
    elbow_k: list[int] = []
    elbow_inertia: list[float] = []
    for kk in range(1, max_k + 1):
        try:
            km = KMeans(n_clusters=kk, n_init=10, random_state=42)
            km.fit(scaled)
            elbow_k.append(kk)
            elbow_inertia.append(float(km.inertia_))
        except Exception:
            continue
    return KMeansResult(
        labels=np.asarray(labels, dtype=int),
        centers=np.asarray(model.cluster_centers_, dtype=float),
        inertia=float(model.inertia_),
        k=int(k),
        variables=list(variables),
        used_positions=positions,
        scaled=bool(standardize),
        scores_2d=np.asarray(scores_2d, dtype=float),
        axis_labels=axis_labels,
        elbow_k=elbow_k,
        elbow_inertia=elbow_inertia,
        explained_2d=explained_2d,
    )


def run_pca(manager: DataManager, variables: list[str]) -> PCAResult:
    if len(variables) < 2:
        raise MultivariateError("Escolha pelo menos duas variáveis para a PCA.")
    matrix, positions = _numeric_matrix(manager, variables, active_only=True)
    if np.std(matrix, axis=0).min() == 0:
        raise MultivariateError("Uma variável escolhida não tem variação. Retire-a.")
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)
    n_components = min(matrix.shape[0], matrix.shape[1])
    pca = PCA(n_components=n_components, random_state=42)
    scores = pca.fit_transform(scaled)
    loadings = pd.DataFrame(
        pca.components_.T,
        index=variables,
        columns=[f"CP{i + 1}" for i in range(n_components)],
    )
    return PCAResult(
        scores=np.asarray(scores, dtype=float),
        loadings=loadings,
        explained=np.asarray(pca.explained_variance_ratio_, dtype=float),
        cumulative=np.cumsum(pca.explained_variance_ratio_),
        variables=list(variables),
        used_positions=positions,
        means=np.asarray(scaler.mean_, dtype=float),
        n_obs=len(positions),
    )


def pca_loading_text(value: float) -> str:
    return format_number(value, 3)
