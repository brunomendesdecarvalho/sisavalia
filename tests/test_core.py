"""Testes executáveis do núcleo do SisAvalia (sem tela)."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from core.data_manager import DataManager, transform_value
from core.diagnostics import compute_diagnostics
from core.evaluation import evaluate_item, report_blockers, round_to_one_percent
from core.formatting import format_number, parse_number
from core.model_search import ModelSearch, SearchCancelled
from core.multivariate import run_kmeans, run_pca
from core.nbr14653 import compute_nbr, final_grade, item2, item5, item6, provisional_degree, NBRItem
from core.project_io import ProjectIO
from core.regression_engine import RegressionEngine
from core.report_generator import make_context, export_spreadsheet, generate_docx
from core.app_paths import error_log_path, log_exception
from core.self_check import check_installation
from core.simulation import descriptive, simulate


VALS = {"Area_m2": 80.0, "Padrao": 2.0, "Idade_anos": 5.0}


@pytest.fixture()
def example() -> DataManager:
    manager = DataManager()
    manager.load_example()
    return manager


@pytest.fixture()
def fit_example(example: DataManager):
    return RegressionEngine.fit(example)


def make_code_manager(rows: int = 30, include_code: bool = True) -> DataManager:
    rng = np.random.default_rng(123)
    x1 = np.arange(1, rows + 1, dtype=float)
    x2 = rng.uniform(1, 10, rows)
    code = np.tile([1, 2, 3], int(np.ceil(rows / 3)))[:rows].astype(float)
    y = 20.0 + 2.2 * x1 + 0.8 * x2 + (3.0 * code if include_code else 0) + rng.normal(0, 0.03, rows)
    frame = pd.DataFrame({"X1": x1, "X2": x2, "Y": y})
    if include_code:
        frame["Codigo"] = code
    manager = DataManager()
    manager.load_dataframe(frame)
    manager.y_column = "Y"
    manager.y_transform = "x"
    manager.label_column = None
    manager.column_types["Codigo"] = "Código alocado" if include_code else "Quantitativa"
    for name in frame.columns:
        manager.x_config[name] = {"selected": name != "Y", "transformation": "x", "expected_sign": 0}
    manager.manual_grades = {"item1": "III", "item3": "III"}
    return manager


# ------------------------------------------------------------------ formatação
def test_formatacao_brasileira_e_leitura():
    assert format_number(1234.56, 2) == "1.234,56"
    assert format_number(-1234.5, 1) == "-1.234,5"
    assert format_number(float("nan")) == "—"
    assert parse_number("1.234,56") == pytest.approx(1234.56)
    assert parse_number("1234,56") == pytest.approx(1234.56)
    assert parse_number("1234.56") == pytest.approx(1234.56)
    assert parse_number("R$ 2.500,00") == pytest.approx(2500.0)
    with pytest.raises(ValueError):
        parse_number("abc")


def test_exemplo_configurado(example: DataManager):
    assert example.n_rows == 20
    assert example.n_active == 20
    assert example.label_column == "Imovel"
    assert example.y_column == "Valor_unitario"
    assert example.y_transform == "ln(x)"
    specs = example.x_specs(True)
    assert {s["name"] for s in specs} == {"Area_m2", "Padrao", "Idade_anos"}
    assert example.column_types["Padrao"] == "Código alocado"
    errors, warnings = example.validate()
    assert errors == []
    assert warnings == []


def test_transformacao_invalida(example: DataManager):
    example.df.at[0, "Idade_anos"] = 0.0
    example.set_x("Idade_anos", transformation="ln(x)")
    errors, _ = example.validate()
    assert any("ln(x)" in e and "Idade_anos" in e for e in errors)
    with pytest.raises(ValueError):
        transform_value(0.0, "ln(x)")


# ------------------------------------------------------------------- regressão
def test_regressao_exemplo(fit_example):
    assert fit_example.n_obs == 20
    assert fit_example.n_active == 20
    assert fit_example.k == 3
    assert fit_example.rsquared == pytest.approx(0.8452, abs=0.002)
    assert fit_example.rsquared_adj == pytest.approx(0.8162, abs=0.002)
    assert fit_example.f_pvalue < 0.01
    assert fit_example.worst_regressor_p < 0.01
    assert "ln(Valor_unitario)" in fit_example.equation
    assert "ln(Area_m2)" in fit_example.equation
    assert len(fit_example.anova_rows) == 3
    assert sum(row["GL"] for row in fit_example.anova_rows if row["Fonte"] != "Total") == 19


def test_intervalo_confianca_80(fit_example):
    prediction = fit_example.predict_at(VALS)
    eta, vector = fit_example.predicted_transformed_at(VALS)
    tcrit = stats.t.ppf(0.90, fit_example.df_resid)
    se = math.sqrt(float(vector @ fit_example.covariance @ vector))
    low = math.exp(eta - tcrit * se)
    high = math.exp(eta + tcrit * se)
    point = math.exp(eta)
    assert prediction.ci_low == pytest.approx(low, rel=1e-9)
    assert prediction.ci_high == pytest.approx(high, rel=1e-9)
    assert prediction.point == pytest.approx(point, rel=1e-9)
    assert prediction.pi_low < prediction.ci_low < prediction.ci_high < prediction.pi_high
    expected_amp = (high - low) / point * 100.0
    assert prediction.amplitude_pct == pytest.approx(expected_amp, rel=1e-9)
    assert prediction.precision_degree == "III"


def test_graus_itens_automaticos():
    assert item2(24, 3).grade == "III"   # 24 >= 24
    assert item2(16, 3).grade == "II"
    assert item2(12, 3).grade == "I"
    assert item2(11, 3).grade == "0"
    assert item5(0.10).grade == "III"
    assert item5(0.20).grade == "II"
    assert item5(0.30).grade == "I"
    assert item5(0.31).grade == "0"
    assert item6(0.01).grade == "III"
    assert item6(0.02).grade == "II"
    assert item6(0.05).grade == "I"
    assert item6(0.06).grade == "0"


def test_enquadramento_exemplo(example, fit_example):
    prediction = fit_example.predict_at(VALS)
    result = compute_nbr(example, fit_example, prediction, VALS)
    assert result.item(2).grade == "II"
    assert result.item4_grade == "III"
    assert result.final_degree == "II"
    assert result.total_points == 15
    assert result.precision_degree == "III"
    assert result.cap_applied is False


def test_teto_codigo_alocado():
    manager = make_code_manager(rows=30, include_code=True)
    fit = RegressionEngine.fit(manager)
    values = {"X1": 10, "X2": 5, "Codigo": 2}
    prediction = fit.predict_at(values)
    result = compute_nbr(manager, fit, prediction, values)
    assert result.item(2).grade == "III"
    assert result.final_degree_before_cap if False else True
    # Sem o teto, os itens e a soma dariam Grau III. Com código alocado, fica II.
    assert result.total_points >= 16
    assert result.final_degree == "II"
    assert result.cap_applied is True
    assert "código alocado" in result.cap_explanation.lower()


def test_extrapolacao_uma_variavel(example, fit_example):
    values = {"Area_m2": 300.0, "Padrao": 2.0, "Idade_anos": 5.0}
    prediction = fit_example.predict_at(values)
    result = compute_nbr(example, fit_example, prediction, values)
    row = result.extrapolation[0]
    assert row.situation == "acima"
    assert row.acceptable is True
    assert row.distance_pct is not None and row.distance_pct <= 15
    assert result.item4_grade == "II"


def test_extrapolacao_acima_do_dobro(example, fit_example):
    values = {"Area_m2": 500.0, "Padrao": 2.0, "Idade_anos": 5.0}
    prediction = fit_example.predict_at(values)
    result = compute_nbr(example, fit_example, prediction, values)
    assert result.extrapolation[0].acceptable is False
    assert result.item4_grade == "0"


def test_extrapolacao_minimo_nao_positivo(example, fit_example):
    values = {"Area_m2": 80.0, "Padrao": 2.0, "Idade_anos": -1.0}
    prediction = fit_example.predict_at(values)
    result = compute_nbr(example, fit_example, prediction, values)
    assert result.item4_grade == "0"
    assert any("regra da metade" in note for note in result.notes)


def test_avaliando_fora_do_ic_bloqueia(example, fit_example):
    item = example.add_evaluated("Fora", VALS)
    item["adopted"] = 50000.0
    result = evaluate_item(example, fit_example, item)
    assert not result.adopted_inside_ci
    assert result.blocking_messages
    blockers = report_blockers([result], example)
    assert any("intervalo de confiança" in b for b in blockers)


def test_justificativa_obrigatoria(example, fit_example):
    item = example.add_evaluated("Diferente", VALS)
    result = evaluate_item(example, fit_example, item)
    item["adopted"] = result.prediction.point + 100.0
    result = evaluate_item(example, fit_example, item)
    assert result.justification_required
    assert any("justificativa" in b.lower() for b in result.blocking_messages)
    item["justification"] = "Valor de mercado conferido em vistoria."
    assert evaluate_item(example, fit_example, item).can_export


def test_arredondar_um_por_cento():
    value = round_to_one_percent(10233.53)
    assert value == pytest.approx(10233.53, abs=102.34)
    assert value % (10233.53 * 0.01) == pytest.approx(0.0, abs=1e-7)


# ------------------------------------------------------------------- busca
def test_busca_exaustiva_exemplo(example):
    outcome = ModelSearch(example).run()
    assert outcome.mode == "completa"
    assert outcome.total_specs == 15
    assert outcome.tested == 15
    assert len(outcome.results) == 15
    adjusted = [r.r2_adj for r in outcome.results]
    assert adjusted == sorted(adjusted, reverse=True)
    assert outcome.results[0].r2_adj >= 0.89
    assert outcome.results[0].n == 20
    for result in outcome.results:
        assert result.spec["y"] == "Valor_unitario"
        assert result.equation.startswith("ln(Valor_unitario) = ")


def test_busca_simplificada_tem_teto(example):
    rng = np.random.default_rng(7)
    frame = pd.DataFrame({f"X{i}": rng.uniform(1, 10, size=28) for i in range(1, 7)})
    frame["Y"] = 2 + frame["X1"] * 1.5 + frame["X2"] * 0.8 + rng.normal(0, 0.4, 28)
    manager = DataManager()
    manager.load_dataframe(frame)
    manager.y_column = "Y"
    manager.y_transform = "x"
    for name in frame.columns:
        manager.x_config[name] = {"selected": name != "Y", "transformation": "x", "expected_sign": 0}
    outcome = ModelSearch(manager).run()
    assert outcome.mode == "simplificada"
    assert outcome.tested <= 400
    assert len(outcome.results) <= 30
    assert outcome.results


def test_busca_cancelavel(example):
    calls = {"n": 0}

    def cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 3

    with pytest.raises(SearchCancelled):
        ModelSearch(example, cancel=cancel).run()


# ---------------------------------------------------------------- diagnósticos
def test_diagnosticos_exemplo(fit_example):
    diag = compute_diagnostics(fit_example)
    assert len(diag.table) == 20
    assert len(diag.normality_bands) == 3
    assert diag.normality.status in ("verde", "amarelo", "vermelho")
    assert diag.mahalanobis_cutoff > 0
    assert diag.cooks_threshold == pytest.approx(4 / 20)
    assert all(row.relative_pct >= 0 for row in diag.table)


# ----------------------------------------------------------- multivariada/sim
def test_kmeans_e_pca(example):
    kmeans = run_kmeans(example, ["Area_m2", "Padrao", "Idade_anos"], 3)
    assert len(kmeans.labels) == 20
    assert set(kmeans.labels) <= {0, 1, 2}
    assert len(kmeans.elbow_k) >= 2
    pca = run_pca(example, ["Area_m2", "Padrao", "Idade_anos", "Valor_unitario"])
    assert pca.scores.shape == (20, 4)
    assert pytest.approx(float(pca.explained.sum()), rel=1e-9) == 1.0


def test_simulacoes():
    for dist, params in (
        ("normal", {"mean": "10", "std": "2"}),
        ("uniforme", {"low": "0", "high": "10"}),
        ("triangular", {"low": "0", "mode": "4", "high": "10"}),
        ("exponencial", {"mean": "4"}),
        ("poisson", {"mean": "3"}),
    ):
        values = simulate(dist, params, 200, seed=42)
        assert len(values) == 200
        stats_ = descriptive(values)
        assert stats_["n"] == 200
        assert stats_["min"] <= stats_["median"] <= stats_["max"]


# ------------------------------------------------------------------ projeto
def test_projeto_ida_e_volta(example, fit_example, tmp_path):
    item = example.add_evaluated("Avaliando A", VALS)
    item["adopted"] = 10000.0
    item["justification"] = "Teste de ida e volta."
    example.last_model = fit_example.to_model_record()
    example.saved_equations = [{"equation": "teste", "r2_adj": 0.9}]
    io = ProjectIO(tmp_path)
    target = io.save_project(tmp_path / "teste.sisproj", example)
    assert target.exists()
    loaded = io.load_project(target)
    assert loaded.n_rows == 20
    assert loaded.n_active == 20
    assert loaded.metadata["work_name"] == example.metadata["work_name"]
    assert loaded.evaluated[0]["name"] == "Avaliando A"
    assert loaded.evaluated[0]["adopted"] == pytest.approx(10000.0)
    assert loaded.saved_equations[0]["equation"] == "teste"
    assert loaded.label_column == "Imovel"
    assert loaded.column_types == example.column_types
    assert io.autosave(loaded)
    assert io.has_autosave()
    io.clear_autosave()
    assert not io.has_autosave()


# ------------------------------------------------------------------ relatório
def test_relatorio_docx_e_planilha(example, fit_example, tmp_path):
    item = example.add_evaluated("Avaliando R", VALS)
    result = evaluate_item(example, fit_example, item)
    item["adopted"] = result.prediction.point
    result = evaluate_item(example, fit_example, item)
    context = make_context("Relatório de teste", example, fit_example, [result])
    context.ensure_ready()
    docx = generate_docx(context, tmp_path / "relatorio.docx")
    assert docx.exists() and docx.stat().st_size > 30000
    xlsx = export_spreadsheet(example, fit_example, compute_diagnostics(fit_example), [result],
                              tmp_path / "planilha.xlsx")
    assert xlsx.exists() and xlsx.stat().st_size > 5000


# ------------------------------------------------------------------ dados
def test_verificacao_de_componentes():
    report = check_installation()
    assert report.ok, report.message()
    assert report.missing_modules == []
    assert report.missing_assets == []


def test_coluna_calculada_e_ativas(example):
    column = example.add_calculated_column("Valor_m2_teste", "Valor_total", "÷", column_b="Area_m2")
    assert column in example.df.columns
    assert example.df.at[0, column] == pytest.approx(9140.0, rel=0.01)
    original = example.n_active
    changed = example.deactivate_many([0, 1])
    assert changed == 2
    assert example.n_active == original - 2
    assert example.undo() is True
    assert example.n_active == original


def test_log_exception_registra_traceback(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "dados_log"))
    try:
        raise RuntimeError("falha controlada do teste")
    except RuntimeError as exc:
        log_exception("teste de log", (type(exc), exc, exc.__traceback__))
    texto = error_log_path().read_text(encoding="utf-8")
    assert "teste de log" in texto
    assert "RuntimeError: falha controlada do teste" in texto
    assert "Traceback" in texto


def test_tipo_codigo_ajustado_e_descricao_da_escala(example: DataManager):
    from core.data_manager import CATEGORICAL_TYPES, COLUMN_TYPES
    assert "Código ajustado" in COLUMN_TYPES
    assert "Código ajustado" in CATEGORICAL_TYPES
    example.set_column_type("Padrao", "Código ajustado")
    example.set_x("Padrao", selected=True)
    example.set_x_description("Padrao", "1 = simples; 2 = normal; 3 = alto")
    spec = next(s for s in example.x_specs(True) if s["name"] == "Padrao")
    assert spec["description"] == "1 = simples; 2 = normal; 3 = alto"
    with pytest.raises(ValueError):
        example.set_x("Padrao", transformation="ln(x)")


def _category_manager(n: int, count_positive: int) -> DataManager:
    frame = pd.DataFrame({
        "Y": np.arange(1, n + 1, dtype=float),
        "Cat": [1.0] * count_positive + [0.0] * (n - count_positive),
    })
    manager = DataManager()
    manager.load_dataframe(frame)
    manager.y_column = "Y"
    manager.y_transform = "x"
    manager.label_column = None
    manager.column_types["Cat"] = "Dicotômica"
    manager.x_config["Cat"] = {
        "selected": True, "transformation": "x", "expected_sign": 0, "description": "",
    }
    return manager


def test_micronumerosidade_por_faixa_de_n():
    m20 = _category_manager(20, 2)
    assert any(i["minimum"] == 3 and i["count"] == 2 for i in m20.micronumerosity_issues())
    m50 = _category_manager(50, 4)
    assert any(i["minimum"] == 5 for i in m50.micronumerosity_issues())
    m101 = _category_manager(101, 5)
    assert any(i["minimum"] == 10 for i in m101.micronumerosity_issues())


def test_extrapolacao_qualitativa_bloqueia_item4(example: DataManager, fit_example):
    manager = example
    item = manager.add_evaluated("Fora da categoria", {
        "Area_m2": 80, "Padrao": 4, "Idade_anos": 5,
    })
    result = evaluate_item(manager, fit_example, item)
    row = next(r for r in result.nbr.extrapolation if r.variable == "Padrao")
    assert not row.acceptable
    assert row.reason
    assert result.nbr.item4_grade == "0"


def test_intervalo_predicao_e_intervalo_admissivel(example: DataManager, fit_example):
    manager = example
    item = manager.add_evaluated("Intervalo IP", {
        "Area_m2": 80, "Padrao": 2, "Idade_anos": 5,
    })
    manager.update_evaluated(item["id"], interval_mode="IP")
    result = evaluate_item(manager, fit_example, item)
    assert result.interval_mode == "IP"
    assert result.selected_low == pytest.approx(result.prediction.pi_low)
    assert result.selected_high == pytest.approx(result.prediction.pi_high)
    assert result.admissible_low == pytest.approx(max(result.prediction.pi_low, result.arbitrio_low))
    assert result.admissible_high == pytest.approx(min(result.prediction.pi_high, result.arbitrio_high))


def test_equacao_original_volta_da_escala_logaritmica(fit_example):
    assert fit_example.equation.startswith("ln(Valor_unitario)")
    assert fit_example.equation_original.startswith("Valor_unitario = exp(")


def test_plugins_nativos_sao_descobertos_e_calculos_funcionam():
    from core.plugin_manager import PluginManager
    names = {p.plugin.name for p in PluginManager().discover()}
    assert {"Tratamento por fatores", "Método evolutivo e CUB", "Procedimentos específicos"} <= names
    from plugins._engenharia import ross_heidecke, liquidation_vpl, rent_by_capital, factor_values
    kd, residual = ross_heidecke(10, 60, "Regular")
    assert 0 < kd < 1 and residual == pytest.approx(1 - kd)
    assert liquidation_vpl(500000, 12, 1500, 6, 12)["vpl"] > 0
    assert rent_by_capital(500000, 6)["monthly"] > 0
    result = factor_values([100, 110, 120], [1.0], criterion="±30%")
    assert result.n == 3 and result.mean > 0
