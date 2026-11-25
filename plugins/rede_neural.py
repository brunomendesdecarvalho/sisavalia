"""Plugin de rede neural (MLP) para apoio à análise da amostra."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
    QProgressBar, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from core import charting
from core.formatting import format_number
from core.plugin_base import BasePlugin
from ui.clipboard import copy_text
from ui.file_dialogs import save_file_name
from ui.plots import PlotCard
from ui.widgets import button, show_info, show_warning

try:
    from ._neural import NeuralConfig, NeuralResult, parse_layers, train_neural
except ImportError:  # plugin carregado por caminho pelo PluginManager
    from _neural import NeuralConfig, NeuralResult, parse_layers, train_neural


class RedeNeural(BasePlugin):
    name = "Rede neural (MLP)"
    description = (
        "Treina uma rede neural de múltiplas camadas para apoiar a análise da amostra, "
        "com camadas, ativação, solver, regularização, épocas e validação configuráveis. "
        "Não é método de enquadramento da NBR 14653-2."
    )

    def run(self, dataframe: pd.DataFrame, parent_widget: Any) -> Any:
        dialog = NeuralDialog(dataframe, parent_widget)
        dialog.exec()
        return dialog.result_data


class NeuralWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, frame: pd.DataFrame, y: str, x: list[str], config: NeuralConfig,
                 active: Optional[list[bool]], transforms: dict[str, str],
                 y_transform: str, parent: Any = None) -> None:
        super().__init__(parent)
        self.frame = frame.copy()
        self.y = y
        self.x = x
        self.config = config
        self.active = list(active) if active is not None else None
        self.transforms = dict(transforms)
        self.y_transform = y_transform

    def run(self) -> None:
        try:
            result = train_neural(
                self.frame, self.y, self.x, self.config,
                active=self.active, transforms=self.transforms, y_transform=self.y_transform,
            )
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class NeuralDialog(QDialog):
    def __init__(self, dataframe: pd.DataFrame, parent: Any = None) -> None:
        super().__init__(parent)
        self.dataframe = dataframe.copy()
        self.result_data: dict[str, Any] | None = None
        self.worker: Optional[NeuralWorker] = None
        self.result: Optional[NeuralResult] = None
        window = parent.window() if parent is not None else None
        self.manager = getattr(window, "manager", None)
        self.setWindowTitle("Rede neural (MLP) — apoio à análise")
        self.resize(1080, 820)
        outer = QVBoxLayout(self)
        title = QLabel("Rede neural de múltiplas camadas")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        hint = QLabel(
            "A rede neural procura relações não lineares entre as variáveis. Ela é uma ferramenta "
            "de apoio: a NBR 14653-2 não prescreve rede neural para enquadramento de fundamentação "
            "ou precisão. Compare sempre com a regressão e com o seu julgamento."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        outer.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)
        data_box = QFormLayout()
        self.y_combo = QComboBox()
        self.y_combo.currentTextChanged.connect(self._refresh_x)
        for column in self.dataframe.columns:
            if pd.to_numeric(self.dataframe[column], errors="coerce").notna().sum() >= 8:
                self.y_combo.addItem(str(column))
        if self.manager is not None and getattr(self.manager, "y_column", None):
            idx = self.y_combo.findText(str(self.manager.y_column))
            if idx >= 0:
                self.y_combo.setCurrentIndex(idx)
        data_box.addRow("Variável Y (alvo):", self.y_combo)
        x_title = QLabel("Variáveis X (marque as que entram na rede):")
        x_title.setWordWrap(True)
        data_box.addRow(x_title)
        self.x_list = QListWidget()
        self.x_list.setMinimumHeight(155)
        self.x_list.setAccessibleName("Variáveis independentes da rede neural")
        self._fill_x()
        data_box.addRow(self.x_list)
        x_actions = QHBoxLayout()
        all_button = button("Marcar todas", "ok")
        none_button = button("Desmarcar todas", "close")
        all_button.clicked.connect(lambda: self._set_all_x(True))
        none_button.clicked.connect(lambda: self._set_all_x(False))
        x_actions.addWidget(all_button)
        x_actions.addWidget(none_button)
        x_actions.addStretch(1)
        data_box.addRow(x_actions)
        root.addLayout(data_box)
        form_title = QLabel("Configurações da rede")
        form_title.setObjectName("SectionTitle")
        root.addWidget(form_title)
        form = QFormLayout()
        form.setSpacing(7)
        self.layers = QLineEdit("32, 16")
        self.layers.setToolTip("Neurônios por camada oculta, separados por vírgula. Ex.: 64, 32, 16.")
        self.activation = QComboBox()
        self.activation.addItem("ReLU — rápida e comum", "relu")
        self.activation.addItem("Tangente hiperbólica (tanh)", "tanh")
        self.activation.addItem("Logística (sigmoide)", "logistic")
        self.activation.addItem("Identidade (linear)", "identity")
        self.solver = QComboBox()
        self.solver.addItem("Adam — adaptativo, recomendado", "adam")
        self.solver.addItem("LBFGS — bom para amostras pequenas", "lbfgs")
        self.solver.addItem("SGD — descida de gradiente", "sgd")
        self.alpha = self._spin(0, 10, 0.0001, 5, 0.0001)
        self.alpha.setToolTip("Regularização L2. Quanto maior, mais simples e menos overfitting.")
        self.learning_rate = self._spin(0.00001, 1.0, 0.001, 5, 0.0001)
        self.schedule = QComboBox()
        self.schedule.addItem("Constante", "constant")
        self.schedule.addItem("Adaptativa — reduz quando não melhora", "adaptive")
        self.schedule.addItem("Potência inversa", "invscaling")
        self.max_iter = QSpinBox()
        self.max_iter.setRange(100, 20000)
        self.max_iter.setValue(1500)
        self.max_iter.setSingleStep(100)
        self.early = QCheckBox("Parada antecipada (early stopping)")
        self.early.setChecked(True)
        self.early.setToolTip("Separa uma parte do treino para parar quando a validação deixa de melhorar.")
        self.validation = self._spin(5, 40, 15, 0, 1)
        self.validation.setSuffix(" %")
        self.validation.setToolTip("Fração do treino usada para validar a parada antecipada.")
        self.patience = QSpinBox()
        self.patience.setRange(3, 200)
        self.patience.setValue(20)
        self.patience.setToolTip("Épocas sem melhora antes de parar.")
        self.test_size = self._spin(10, 40, 25, 0, 1)
        self.test_size.setSuffix(" %")
        self.test_size.setToolTip("Fração dos imóveis separada para teste. O teste não participa do treino.")
        self.standardize = QCheckBox("Padronizar X e Y")
        self.standardize.setChecked(True)
        self.standardize.setToolTip("Coloca as variáveis em escala comparável; recomendado quando há unidades diferentes.")
        self.use_transforms = QCheckBox("Usar as transformações atuais de X e Y")
        self.use_transforms.setToolTip(
            "Aplica as transformações escolhidas na aba 1. Se desmarcado, usa os valores originais."
        )
        self.seed = QSpinBox()
        self.seed.setRange(1, 999999)
        self.seed.setValue(42)
        self.seed.setToolTip("Semente para repetir a mesma divisão treino/teste e a mesma inicialização.")
        for label, widget, tip in (
            ("Camadas ocultas (neurônios):", self.layers, "Ex.: 32, 16 significa duas camadas, uma com 32 e outra com 16 neurônios."),
            ("Ativação:", self.activation, "Função que dá não linearidade à rede."),
            ("Solver:", self.solver, "Algoritmo que ajusta os pesos."),
            ("Alpha (regularização L2):", self.alpha, "Pena pesos grandes; ajuda a evitar overfitting."),
            ("Taxa de aprendizado inicial:", self.learning_rate, "Tamanho do passo inicial do ajuste dos pesos."),
            ("Agenda da taxa:", self.schedule, "Como a taxa de aprendizado muda ao longo do treino (solver SGD)."),
            ("Máximo de épocas:", self.max_iter, "Quantas passagens pelo treino a rede pode fazer."),
            ("", self.early, "Para o treino quando a validação não melhora."),
            ("Validação da parada:", self.validation, "Fração do treino reservada para a parada antecipada."),
            ("Paciência:", self.patience, "Épocas sem melhora antes de parar."),
            ("Teste:", self.test_size, "Fração separada para medir a generalização."),
            ("", self.standardize, "Padroniza as variáveis."),
            ("", self.use_transforms, "Aplica as transformações da aba 1."),
            ("Semente aleatória:", self.seed, "Reprodutibilidade."),
        ):
            widget.setToolTip(tip)
            form.addRow(label, widget)
        root.addLayout(form)
        self.solver.currentTextChanged.connect(self._solver_changed)
        self.early.toggled.connect(self._early_changed)
        self._solver_changed()
        self._early_changed()
        explanation = QPlainTextEdit()
        explanation.setReadOnly(True)
        explanation.setMinimumHeight(150)
        explanation.setPlainText(
            "O que cada ajuste faz:\n"
            "• Camadas/neurônios: mais camadas e neurônios capturam relações mais complexas, mas aumentam o risco de overfitting.\n"
            "• Ativação: ReLU é rápida; tanh e logística suavizam; identidade deixa a rede praticamente linear.\n"
            "• Solver: Adam é o mais robusto no dia a dia; LBFGS funciona bem em amostras pequenas; SGD exige ajuste fino da taxa.\n"
            "• Alpha: regularização; aumente se a rede decorar o treino e for mal no teste.\n"
            "• Taxa de aprendizado: passos grandes aceleram e podem oscilar; passos pequenos são mais estáveis e lentos.\n"
            "• Épocas: número de passagens; a parada antecipada evita continuar sem ganho.\n"
            "• Teste: parte dos imóveis fica fora do treino; o R² de teste é a medida mais honesta de generalização.\n"
            "• Padronização: necessária quando as variáveis têm escalas muito diferentes.\n"
            "• Semente: repete a mesma divisão e inicialização para comparar configurações."
        )
        explanation.setAccessibleName("Explicação das configurações da rede neural")
        root.addWidget(explanation)
        actions = QHBoxLayout()
        self.train_button = button("Treinar rede", "calculator", primary=True)
        self.copy_button = button("Copiar resultado", "copy")
        self.save_button = button("Salvar resultado", "save")
        self.train_button.clicked.connect(self.train)
        self.copy_button.clicked.connect(self.copy_result)
        self.save_button.clicked.connect(self.save_result)
        actions.addWidget(self.train_button)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.save_button)
        actions.addStretch(1)
        root.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)
        self.result_text = QPlainTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMinimumHeight(190)
        self.result_text.setPlaceholderText("Os indicadores da rede aparecem aqui depois do treinamento.")
        root.addWidget(self.result_text)
        self.loss_plot = PlotCard("Curva de perda do treinamento", minimum_height=430)
        self.fit_plot = PlotCard("Teste: observado × previsto pela rede", minimum_height=430)
        root.addWidget(self.loss_plot)
        root.addWidget(self.fit_plot)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        close = button("Fechar", "close")
        close.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close)
        outer.addLayout(bottom)
        self._transforms = {}
        self._y_transform = "x"
        if self.manager is not None:
            self._transforms = {s["name"]: s["transformation"] for s in self.manager.x_specs(True)}
            self._y_transform = self.manager.y_transform

    @staticmethod
    def _spin(minimum: float, maximum: float, value: float, decimals: int,
              step: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setValue(value)
        spin.setSingleStep(step)
        return spin

    def _fill_x(self) -> None:
        selected = set()
        if self.manager is not None:
            selected = {s["name"] for s in self.manager.x_specs(True)}
        y = self.y_combo.currentText()
        for column in self.dataframe.columns:
            if str(column) == y:
                continue
            if pd.to_numeric(self.dataframe[column], errors="coerce").notna().sum() < 8:
                continue
            item = QListWidgetItem(str(column))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if (not selected or str(column) in selected) else Qt.CheckState.Unchecked)
            self.x_list.addItem(item)
        # Se não veio do gerenciador, não marque todas: deixe as três primeiras.
        if self.manager is None or not selected:
            for i in range(self.x_list.count()):
                self.x_list.item(i).setCheckState(
                    Qt.CheckState.Checked if i < 3 else Qt.CheckState.Unchecked
                )

    def _refresh_x(self) -> None:
        if not hasattr(self, "x_list"):
            return
        self.x_list.clear()
        self._fill_x()

    def _set_all_x(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.x_list.count()):
            self.x_list.item(i).setCheckState(state)

    def _solver_changed(self) -> None:
        solver = str(self.solver.currentData())
        self.schedule.setEnabled(solver == "sgd")
        self.learning_rate.setEnabled(solver != "lbfgs")

    def _early_changed(self) -> None:
        enabled = self.early.isChecked()
        self.validation.setEnabled(enabled)
        self.patience.setEnabled(enabled)

    def _selected_x(self) -> list[str]:
        result = []
        for i in range(self.x_list.count()):
            item = self.x_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.text())
        return result

    def _config(self) -> NeuralConfig:
        return NeuralConfig(
            hidden_layers=parse_layers(self.layers.text()),
            activation=str(self.activation.currentData()),
            solver=str(self.solver.currentData()),
            alpha=self.alpha.value(),
            learning_rate_init=self.learning_rate.value(),
            learning_rate=str(self.schedule.currentData()),
            max_iter=self.max_iter.value(),
            early_stopping=self.early.isChecked(),
            validation_fraction=self.validation.value() / 100.0,
            n_iter_no_change=self.patience.value(),
            test_size=self.test_size.value() / 100.0,
            standardize=self.standardize.isChecked(),
            random_state=self.seed.value(),
            use_current_transforms=self.use_transforms.isChecked(),
        )

    def train(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        y = self.y_combo.currentText()
        x = self._selected_x()
        if not x:
            show_warning(self, "Marque pelo menos uma variável X.")
            return
        try:
            config = self._config()
        except Exception as exc:
            show_warning(self, f"Configuração inválida: {exc}")
            return
        active = list(self.manager.active) if self.manager is not None else None
        if self.manager is not None and hasattr(self.manager, "active_mask"):
            try:
                active = [bool(v) for v in self.manager.active_mask()]
            except Exception:
                active = None
        worker = NeuralWorker(self.dataframe, y, x, config, active,
                              self._transforms, self._y_transform, self)
        self.worker = worker
        self.train_button.setEnabled(False)
        self.progress.setVisible(True)
        self.result_text.setPlainText("Treinando a rede...")
        worker.completed.connect(self._finished)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._thread_finished)
        worker.start()

    def _finished(self, result: NeuralResult) -> None:
        self.result = result
        lines = [
            "Rede neural — resultado do teste",
            f"Imóveis usados: {result.n_total}  •  treino: {result.n_train}  •  teste: {result.n_test}",
            f"Camadas: {', '.join(str(n) for n in result.config.hidden_layers)}  •  ativação: {result.config.activation}  •  solver: {result.config.solver}",
            "",
            f"R² treino: {format_number(result.train_r2, 4)}  •  R² teste: {format_number(result.test_r2, 4)}",
            f"MAE teste: {format_number(result.test_mae, 2)}  •  RMSE teste: {format_number(result.test_rmse, 2)}",
            f"MAPE teste: {format_number(result.test_mape, 2)}%",
            f"Regressão linear de referência — R² teste: {format_number(result.baseline_test_r2, 4)}  •  RMSE teste: {format_number(result.baseline_test_rmse, 2)}",
            f"Épocas efetivas: {result.training_iterations}",
            "",
        ]
        if result.warnings:
            lines.append("Atenção:")
            lines.extend("• " + w for w in result.warnings)
            lines.append("")
        lines.append(
            "A rede neural é apoio exploratório. Ela não gera grau de fundamentação/precisão "
            "da NBR 14653-2; use a regressão e o seu julgamento para o laudo."
        )
        self.result_text.setPlainText("\n".join(lines))
        self.result_text_data = "\n".join(lines)
        self.result_data = {"metrics": result, "text": self.result_text_data}
        self._plot_loss(result)
        self._plot_fit(result)

    def _failed(self, message: str) -> None:
        show_warning(self, f"A rede não pôde ser treinada: {message}")
        self.result_text.setPlainText("Treinamento não concluído.")

    def _thread_finished(self) -> None:
        self.progress.setVisible(False)
        self.train_button.setEnabled(True)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def _plot_loss(self, result: NeuralResult) -> None:
        if not result.loss_curve:
            self.loss_plot.clear_plot("A rede não registrou a curva de perda.")
            return
        fig, ax = charting.new_figure()
        ax.plot(range(1, len(result.loss_curve) + 1), result.loss_curve,
                color=charting.PRIMARY, linewidth=2)
        charting.tidy(ax, title="Perda durante o treinamento", xlabel="Época",
                      ylabel="Perda (MSE)", x_values=None, y_values=None)
        self.loss_plot.set_figure(fig)

    def _plot_fit(self, result: NeuralResult) -> None:
        fig, _ = charting.fit_scatter(
            result.test_observed, result.test_predicted, result.test_labels,
            title="Rede neural — teste: observado × previsto",
        )
        self.fit_plot.set_figure(
            fig, x_values=result.test_predicted, y_values=result.test_observed,
            labels=result.test_labels,
        )

    def copy_result(self) -> None:
        text = getattr(self, "result_text_data", "").strip()
        if not text:
            show_info(self, "Treine a rede antes de copiar.")
            return
        copy_text(text)
        show_info(self, "Resultado copiado.")

    def save_result(self) -> None:
        if self.result is None:
            show_info(self, "Treine a rede antes de salvar.")
            return
        filename = save_file_name(
            self, "Salvar resultado da rede neural", "rede_neural.csv",
            "Planilha CSV (*.csv)", "csv",
        )
        if not filename:
            return
        target = Path(filename)
        if target.suffix.lower() != ".csv":
            target = target.with_suffix(".csv")
        lines = ["observado;previsto;rotulo"]
        for obs, pred, label in zip(self.result.test_observed, self.result.test_predicted,
                                    self.result.test_labels):
            lines.append(f"{format_number(obs, 2).replace('.', ',')};"
                         f"{format_number(pred, 2).replace('.', ',')};{label}")
        lines.append("")
        lines.append(self.result_text_data)
        target.write_text("\n".join(lines), encoding="utf-8-sig")
        show_info(self, f"CSV salvo em:\n{target}", title="CSV salvo")

    def reject(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            show_info(self, "Aguarde o treinamento terminar antes de fechar.")
            return
        super().reject()
