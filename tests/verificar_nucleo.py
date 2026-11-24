#!/usr/bin/env python3
"""Verificação executável, sem pytest e sem tela.

Rode na pasta do projeto:
    python3 tests/verificar_nucleo.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scipy import stats

from core.data_manager import DataManager
from core.diagnostics import compute_diagnostics
from core.evaluation import evaluate_item
from core.model_search import ModelSearch
from core.nbr14653 import compute_nbr
from core.regression_engine import RegressionEngine


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"[OK] {message}")
    else:
        raise AssertionError(message)


def main() -> int:
    manager = DataManager()
    manager.load_example()
    check(manager.n_rows == 20, "exemplo com 20 apartamentos")
    check(manager.validate()[0] == [], "configuração do exemplo sem erros")
    fit = RegressionEngine.fit(manager)
    check(0.80 < fit.rsquared_adj < 0.90, "R² ajustado do exemplo na faixa esperada")
    values = {"Area_m2": 80.0, "Padrao": 2.0, "Idade_anos": 5.0}
    prediction = fit.predict_at(values)
    eta, vector = fit.predicted_transformed_at(values)
    tcrit = stats.t.ppf(0.90, fit.df_resid)
    se = math.sqrt(float(vector @ fit.covariance @ vector))
    check(abs(prediction.ci_low - math.exp(eta - tcrit * se)) < 1e-6, "IC 80% inferior confere")
    check(abs(prediction.ci_high - math.exp(eta + tcrit * se)) < 1e-6, "IC 80% superior confere")
    check(prediction.precision_degree == "III", "grau de precisão do exemplo é III")
    nbr = compute_nbr(manager, fit, prediction, values)
    check(nbr.total_points == 15, "pontuação de fundamentação do exemplo é 15")
    check(nbr.final_degree == "II", "grau de fundamentação do exemplo é II")
    outside = dict(values)
    outside["Area_m2"] = 300.0
    pred2 = fit.predict_at(outside)
    nbr2 = compute_nbr(manager, fit, pred2, outside)
    check(nbr2.item4_grade == "II", "extrapolação aceitável de uma variável dá item 4 grau II")
    too_far = dict(values)
    too_far["Area_m2"] = 500.0
    nbr3 = compute_nbr(manager, fit, fit.predict_at(too_far), too_far)
    check(nbr3.item4_grade == "0", "extrapolação acima do dobro zera o item 4")
    item = manager.add_evaluated("Teste", values)
    result = evaluate_item(manager, fit, item)
    check(result.adopted_inside_ci, "valor adotado padrão dentro do IC")
    search = ModelSearch(manager).run()
    check(search.mode == "completa" and len(search.results) > 0,
          "busca de equações encontrou sugestões")
    check(search.results[0].r2_adj >= search.results[-1].r2_adj,
          "sugestões ordenadas pelo R² ajustado")
    diag = compute_diagnostics(fit)
    check(len(diag.table) == 20, "diagnósticos cobrem os 20 imóveis")
    print("\nTodas as verificações do núcleo passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
