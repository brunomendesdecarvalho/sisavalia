"""Gerenciamento da tabela de dados e da configuração do modelo."""
from __future__ import annotations

import copy
import csv
import io
import math
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from .formatting import format_date_br, format_number, is_missing, parse_number, safe_str

NUMERIC_TYPES = ("Quantitativa", "Dicotômica", "Código alocado", "Código ajustado", "Proxy")
CATEGORICAL_TYPES = ("Dicotômica", "Código alocado", "Código ajustado")
TEXT_TYPE = "Texto"
COLUMN_TYPES = NUMERIC_TYPES + (TEXT_TYPE,)
TRANSFORMS = ("x", "ln(x)", "1/x", "x²", "√x")
SIGNS = ("Subir", "Descer", "Tanto faz")
TIPOLOGIAS = ("Apartamento", "Casa", "Terreno", "Sala", "Galpão", "Rural", "Outra")
HIDDEN_EXPORT = {"cluster", "Cluster"}


def _is_numeric_text(text: Any) -> bool:
    if is_missing(text):
        return True
    try:
        parse_number(text)
        return True
    except (ValueError, TypeError):
        return False


def _safe_json_value(value: Any) -> Any:
    if is_missing(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, date)):
        return value.isoformat()
    return value


def transform_series(series: pd.Series, transformation: str) -> pd.Series:
    """Aplica a transformação escolhida, sem alterar vazios."""
    if transformation not in TRANSFORMS:
        raise ValueError(f"Transformação desconhecida: {transformation}.")
    numeric = pd.to_numeric(series, errors="coerce").astype(float)
    if transformation == "x":
        return numeric
    if transformation == "ln(x)":
        if (numeric.dropna() <= 0).any():
            raise ValueError("Não é possível usar ln(x): há valor zero ou negativo.")
        return np.log(numeric)
    if transformation == "1/x":
        if (numeric.dropna() <= 0).any():
            raise ValueError("Não é possível usar 1/x: há valor zero ou negativo.")
        return 1.0 / numeric
    if transformation == "x²":
        return numeric ** 2
    if transformation == "√x":
        if (numeric.dropna() < 0).any():
            raise ValueError("Não é possível usar √x: há valor negativo.")
        return np.sqrt(numeric)
    raise ValueError("Transformação inválida.")


def transformation_label(name: str, transformation: str) -> str:
    if transformation == "x":
        return name
    if transformation == "ln(x)":
        return f"ln({name})"
    if transformation == "1/x":
        return f"1/{name}"
    if transformation == "x²":
        return f"{name}²"
    if transformation == "√x":
        return f"√{name}"
    return name


def transform_value(value: float, transformation: str) -> float:
    if transformation == "x":
        return float(value)
    if transformation == "ln(x)":
        if value <= 0:
            raise ValueError("ln(x) exige valor maior que zero.")
        return float(math.log(value))
    if transformation == "1/x":
        if value <= 0:
            raise ValueError("1/x exige valor maior que zero.")
        return 1.0 / float(value)
    if transformation == "x²":
        return float(value) ** 2
    if transformation == "√x":
        if value < 0:
            raise ValueError("√x exige valor maior ou igual a zero.")
        return float(math.sqrt(value))
    raise ValueError("Transformação inválida.")


class DataManager:
    """Estado da amostra, das variáveis e dos avaliandos.

    A classe não depende de Qt para poder ser testada sem tela.
    """

    MAX_UNDO = 30

    def __init__(self) -> None:
        self.df = pd.DataFrame()
        self.active: list[bool] = []
        self.row_ids: list[int] = []
        self.column_types: dict[str, str] = {}
        self.label_column: Optional[str] = None
        self.y_column: Optional[str] = None
        self.y_transform: str = "x"
        self.x_config: dict[str, dict[str, Any]] = {}
        self.evaluated: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = self.default_metadata()
        self.manual_grades: dict[str, str] = {"item1": "II", "item3": "II"}
        self.last_model: Optional[dict[str, Any]] = None
        self.saved_equations: list[dict[str, Any]] = []
        self.cluster_column: Optional[str] = None
        self._undo_stack: list[dict[str, Any]] = []
        self._next_id = 1
        self.source_path: Optional[str] = None
        self.example_data = False
        self.revision = 0

    # ------------------------------------------------------------------ estado
    @staticmethod
    def default_metadata() -> dict[str, Any]:
        return {
            "author": "",
            "work_name": "Trabalho sem nome",
            "date": date.today().strftime("%d/%m/%Y"),
            "reference_date": date.today().strftime("%d/%m/%Y"),
            "city": "",
            "tipologia": "Apartamento",
            "description": "",
            "sample_note": "",
            "requester": "",
            "purpose": "",
            "objective": "",
            "assumptions": "",
            "limitations": "",
            "technical_name": "",
            "technical_registry": "",
            "signature_city": "",
            "inspection": "",
        }

    def set_metadata(self, metadata: dict[str, Any]) -> None:
        self.metadata.update({k: v for k, v in metadata.items() if k in self.default_metadata()})

    def has_data(self) -> bool:
        return not self.df.empty and len(self.df.columns) > 0

    @property
    def n_rows(self) -> int:
        return len(self.df)

    @property
    def n_active(self) -> int:
        return int(sum(bool(x) for x in self.active))

    @property
    def n_inactive(self) -> int:
        return int(len(self.active) - self.n_active)

    def active_mask(self) -> np.ndarray:
        return np.asarray(self.active, dtype=bool)

    def numeric_columns(self) -> list[str]:
        return [c for c in self.df.columns if self.column_types.get(c) != TEXT_TYPE]

    def text_columns(self) -> list[str]:
        return [c for c in self.df.columns if self.column_types.get(c) == TEXT_TYPE]

    def is_numeric(self, column: str) -> bool:
        return column in self.df.columns and self.column_types.get(column, TEXT_TYPE) != TEXT_TYPE

    def label_for_row(self, index: int) -> str:
        if self.label_column and self.label_column in self.df.columns:
            value = self.df.iloc[index][self.label_column]
            if not is_missing(value):
                return safe_str(value)
        return f"Imóvel {index + 1}"

    def active_labels(self) -> list[str]:
        return [self.label_for_row(i) for i, active in enumerate(self.active) if active]

    def _new_row_id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    def _touch(self) -> None:
        self.revision += 1

    # ------------------------------------------------------------------ undo
    def _snapshot(self) -> dict[str, Any]:
        return {
            "df": self.df.copy(deep=True),
            "active": list(self.active),
            "row_ids": list(self.row_ids),
            "column_types": dict(self.column_types),
            "label_column": self.label_column,
            "y_column": self.y_column,
            "y_transform": self.y_transform,
            "x_config": copy.deepcopy(self.x_config),
            "evaluated": copy.deepcopy(self.evaluated),
            "manual_grades": dict(self.manual_grades),
            "cluster_column": self.cluster_column,
        }

    def push_undo(self) -> None:
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > self.MAX_UNDO:
            self._undo_stack.pop(0)

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        state = self._undo_stack.pop()
        self.df = state["df"]
        self.active = state["active"]
        self.row_ids = state["row_ids"]
        self.column_types = state["column_types"]
        self.label_column = state["label_column"]
        self.y_column = state["y_column"]
        self.y_transform = state["y_transform"]
        self.x_config = state["x_config"]
        self.evaluated = state["evaluated"]
        self.manual_grades = state["manual_grades"]
        self.cluster_column = state["cluster_column"]
        self._touch()
        return True

    # --------------------------------------------------------------- importação
    @staticmethod
    def _clean_columns(columns: Iterable[Any]) -> list[str]:
        cleaned: list[str] = []
        seen: dict[str, int] = {}
        for i, raw in enumerate(columns, start=1):
            name = str(raw).strip() if raw is not None else ""
            if not name or name.lower().startswith("unnamed"):
                name = f"Coluna {i}"
            name = re.sub(r"\s+", " ", name)
            if name in seen:
                seen[name] += 1
                candidate = f"{name} ({seen[name]})"
                while candidate in cleaned:
                    seen[name] += 1
                    candidate = f"{name} ({seen[name]})"
                name = candidate
            else:
                seen[name] = 1
            cleaned.append(name)
        return cleaned

    @staticmethod
    def _csv_bytes(path: Path) -> tuple[str, str]:
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                return raw.decode(enc), enc
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace"), "utf-8"

    @staticmethod
    def _detect_delimiter(text: str) -> str:
        sample = text[:65536]
        lines = [line for line in sample.splitlines() if line.strip()][:20]
        if not lines:
            return ";"
        best, best_score = ";", -1.0
        for delimiter in (";", ",", "\t", "|"):
            counts = [line.count(delimiter) for line in lines]
            nonzero = [c for c in counts if c > 0]
            if not nonzero:
                continue
            consistency = len(nonzero) / len(counts)
            score = float(np.median(counts)) * consistency - (0.15 if delimiter == "," else 0)
            if score > best_score:
                best, best_score = delimiter, score
        return best

    @classmethod
    def _read_csv_dataframe(cls, path: Path) -> pd.DataFrame:
        text, _ = cls._csv_bytes(path)
        delimiter = cls._detect_delimiter(text)
        # Descobre o decimal observando os campos. Em arquivos com ; é comum
        # usar vírgula decimal; em arquivos com vírgula, ponto decimal.
        decimal = ","
        if delimiter == ",":
            decimal = "."
        elif delimiter == "\t" or delimiter == "|":
            comma_cells = len(re.findall(r"\d,\d", text[:65536]))
            decimal = "," if comma_cells > 0 else "."
        else:
            comma_cells = len(re.findall(r"\d,\d", text[:65536]))
            dot_cells = len(re.findall(r"\d\.\d", text[:65536]))
            decimal = "," if comma_cells >= dot_cells else "."
        thousands = "." if decimal == "," else None
        try:
            frame = pd.read_csv(
                io.StringIO(text),
                sep=delimiter,
                decimal=decimal,
                thousands=thousands,
                dtype=str,
                engine="python",
                skipinitialspace=True,
            )
        except Exception:
            frame = pd.read_csv(
                io.StringIO(text),
                sep=delimiter,
                dtype=str,
                engine="python",
                skipinitialspace=True,
            )
        return frame

    def import_file(self, path: str | Path) -> int:
        """Importa .xlsx, .xls ou .csv. Devolve o número de linhas."""
        file_path = Path(path)
        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            frame = self._read_csv_dataframe(file_path)
        elif suffix in (".xlsx", ".xls"):
            try:
                frame = pd.read_excel(file_path, dtype=object)
            except Exception as exc:
                raise ValueError(
                    "Não foi possível abrir esta planilha. Confira se o arquivo "
                    "não está danificado e se é .xlsx, .xls ou .csv."
                ) from exc
        else:
            raise ValueError("Formato não reconhecido. Use .xlsx, .xls ou .csv.")
        if frame.empty or len(frame.columns) == 0:
            raise ValueError("A planilha está vazia. Ela precisa ter uma linha de títulos e dados.")
        self.load_dataframe(frame)
        self.source_path = str(file_path)
        self.example_data = False
        return len(self.df)

    def parse_pasted_text(self, text: str) -> pd.DataFrame:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not text.strip():
            raise ValueError("A área de transferência está vazia. Copie a tabela no Calc primeiro.")
        delimiter = "\t" if "\t" in text.splitlines()[0] else self._detect_delimiter(text)
        decimal = ","
        if delimiter == ",":
            decimal = "."
        elif delimiter == "\t":
            decimal = "," if re.search(r"\d,\d", text) else "."
        try:
            frame = pd.read_csv(
                io.StringIO(text),
                sep=delimiter,
                decimal=decimal,
                thousands="." if decimal == "," else None,
                dtype=str,
                engine="python",
                skipinitialspace=True,
            )
        except Exception as exc:
            raise ValueError("Não foi possível entender a tabela copiada. Confira as colunas.") from exc
        if frame.empty:
            raise ValueError("A tabela copiada está vazia.")
        return frame

    def load_dataframe(self, frame: pd.DataFrame, *, configure: bool = True) -> None:
        frame = frame.copy()
        frame.columns = self._clean_columns(frame.columns)
        frame = frame.dropna(how="all").reset_index(drop=True)
        self.column_types = {}
        frame = self._normalize_frame(frame)
        self.df = frame
        self.row_ids = [self._new_row_id() for _ in range(len(frame))]
        self.active = [True] * len(frame)
        self._undo_stack.clear()
        self.cluster_column = None
        self.label_column = None
        self.y_column = None
        self.y_transform = "x"
        self.x_config = {}
        self.evaluated = []
        self.manual_grades = {"item1": "II", "item3": "II"}
        self.last_model = None
        self.saved_equations = []
        self.source_path = None
        self.example_data = False
        self._touch()
        if configure:
            self.autoconfigure()

    def _normalize_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = pd.DataFrame(index=frame.index)
        for col in frame.columns:
            raw = frame[col]
            nonempty = [v for v in raw.tolist() if not is_missing(v)]
            numeric_ok = bool(nonempty) and all(_is_numeric_text(v) for v in nonempty)
            if numeric_ok:
                values = []
                for v in raw.tolist():
                    if is_missing(v):
                        values.append(np.nan)
                    else:
                        try:
                            values.append(parse_number(v))
                        except ValueError:
                            values.append(np.nan)
                result[col] = pd.Series(values, dtype="float64")
                self.column_types[col] = self.column_types.get(col, "Quantitativa")
            else:
                values = [None if is_missing(v) else safe_str(v).strip() for v in raw.tolist()]
                result[col] = pd.Series(values, dtype="object")
                self.column_types[col] = TEXT_TYPE
        for col in result.columns:
            if col not in self.column_types:
                self.column_types[col] = "Quantitativa"
        return result

    def autoconfigure(self) -> None:
        """Escolhe uma configuração inicial razoável, sempre editável."""
        self.column_types = {c: self.column_types.get(c, "Quantitativa") for c in self.df.columns}
        text_cols = self.text_columns()
        self.label_column = text_cols[0] if text_cols else None
        numeric = self.numeric_columns()
        y_candidates = [
            c for c in numeric
            if any(term in c.lower() for term in ("valor_unit", "valor unit", "unitário", "unitario", "preço_m2", "preco_m2"))
        ]
        if not y_candidates:
            y_candidates = [c for c in numeric if any(term in c.lower() for term in ("valor", "preço", "preco"))]
        if not y_candidates:
            y_candidates = numeric[-1:] if numeric else []
        self.y_column = y_candidates[0] if y_candidates else None
        self.y_transform = "x"
        self.x_config = {}
        ignored = {"id", "código", "codigo", "cod"}
        chosen: list[str] = []
        for col in numeric:
            low = col.lower()
            if col == self.y_column:
                continue
            if low in ignored or low.endswith("_id") or low.endswith(" id"):
                continue
            if "total" in low and "unit" not in low:
                continue
            sign = 0
            if any(term in low for term in ("area", "área", "padrao", "padrão", "quart", "vaga", "garagem")):
                sign = 1
            if any(term in low for term in ("idade", "distancia", "distância", "tempo")):
                sign = -1
            transform = "x"
            if low.startswith(("valor", "preco", "preço")) or "area" in low or "área" in low:
                if self.df[col].dropna().gt(0).all() if len(self.df) else False:
                    transform = "ln(x)"
            self.x_config[col] = {
                "selected": len(chosen) < 4,
                "transformation": transform,
                "expected_sign": sign,
                "description": "",
            }
            chosen.append(col)
        for col in self.df.columns:
            if col not in self.x_config:
                self.x_config[col] = {"selected": False, "transformation": "x", "expected_sign": 0, "description": ""}
        self._choose_types_heuristic()
        if self.y_column and self.df[self.y_column].dropna().gt(0).all() and len(self.df):
            self.y_transform = "ln(x)"
        self.manual_grades = {"item1": "II", "item3": "II"}

    def _choose_types_heuristic(self) -> None:
        for col in self.numeric_columns():
            series = pd.to_numeric(self.df[col], errors="coerce").dropna()
            low = col.lower()
            if any(term in low for term in ("padrao", "padrão", "codigo", "código", "classe")):
                if len(series) and series.min() >= 1 and (series % 1 == 0).all():
                    self.column_types[col] = "Código alocado"
                    if col in self.x_config:
                        self.x_config[col]["transformation"] = "x"
            elif series.nunique() == 2 and set(series.unique()).issubset({0.0, 1.0}):
                self.column_types[col] = "Dicotômica"
                if col in self.x_config:
                    self.x_config[col]["transformation"] = "x"

    def load_example(self) -> None:
        from .app_paths import resource_path

        path = resource_path("exemplos/apartamentos.csv")
        if not path.exists():
            raise ValueError("O arquivo de exemplo não foi encontrado na instalação.")
        self.import_file(path)
        self.example_data = True
        self.source_path = None
        self.metadata = self.default_metadata()
        self.metadata.update({
            "author": "Exemplo do SisAvalia",
            "work_name": "Amostra de apartamentos — exemplo",
            "city": "Cidade Exemplo",
            "tipologia": "Apartamento",
            "description": "Amostra fictícia para aprender a usar o programa.",
            "sample_note": "Dados de exemplo. Não use em laudo.",
        })
        self.label_column = "Imovel" if "Imovel" in self.df.columns else self.label_column
        self.column_types["Imovel"] = TEXT_TYPE
        self.column_types["Endereco"] = TEXT_TYPE
        self.column_types["Bairro"] = TEXT_TYPE
        self.column_types["Fonte"] = TEXT_TYPE
        self.column_types["Padrao"] = "Código alocado"
        self.y_column = "Valor_unitario" if "Valor_unitario" in self.df.columns else self.y_column
        self.y_transform = "ln(x)"
        wanted = {
            "Area_m2": ("ln(x)", -1),
            "Padrao": ("x", 1),
            "Idade_anos": ("x", -1),
        }
        for col in self.df.columns:
            already = self.x_config.get(col, {})
            transform, sign = wanted.get(
                col, (already.get("transformation", "x"), already.get("expected_sign", 0))
            )
            self.x_config[col] = {
                "selected": col in wanted,
                "transformation": transform,
                "expected_sign": sign,
                "description": already.get("description", ""),
            }
        self.last_model = None
        self.saved_equations = []

    # ------------------------------------------------------------- configuração
    def set_y(self, column: Optional[str]) -> None:
        self.y_column = column
        self._touch()
        if column and self.column_types.get(column) == TEXT_TYPE:
            raise ValueError("A variável dependente precisa ser numérica.")

    def set_y_transform(self, transformation: str) -> None:
        if transformation not in TRANSFORMS:
            raise ValueError("Transformação inválida.")
        self.y_transform = transformation
        self._touch()

    def set_x(self, column: str, *, selected: Optional[bool] = None,
              transformation: Optional[str] = None,
              expected_sign: Optional[int] = None,
              column_type: Optional[str] = None) -> None:
        if column not in self.df.columns:
            raise ValueError("Coluna inexistente.")
        cfg = self.x_config.setdefault(column, {"selected": False, "transformation": "x", "expected_sign": 0, "description": ""})
        if selected is not None:
            cfg["selected"] = bool(selected)
        if transformation is not None:
            if transformation not in TRANSFORMS:
                raise ValueError("Transformação inválida.")
            if self.column_types.get(column) in CATEGORICAL_TYPES and transformation != "x":
                raise ValueError(
                    "Para Dicotômica, Código alocado e Código ajustado só se usa a transformação x."
                )
            cfg["transformation"] = transformation
        if expected_sign is not None:
            cfg["expected_sign"] = int(expected_sign)
        if column_type is not None:
            self.set_column_type(column, column_type)
        self._touch()

    def set_x_description(self, column: str, description: str) -> None:
        """Guarda o critério da escala qualitativa para o laudo (item 10.1 j)."""
        if column not in self.df.columns:
            raise ValueError("Coluna inexistente.")
        cfg = self.x_config.setdefault(
            column,
            {"selected": False, "transformation": "x", "expected_sign": 0, "description": ""},
        )
        cfg["description"] = str(description or "").strip()
        self._touch()

    def micronumerosity_issues(self) -> list[dict[str, Any]]:
        """Checagem por categoria do Anexo A, A.2 a e A.7.

        A regra global n >= 3(k+1) continua em ``validate``; esta função
        verifica quantos imóveis ativos existem em cada categoria das
        variáveis qualitativas usadas no modelo.
        """
        issues: list[dict[str, Any]] = []
        n = self.n_active
        if n <= 0:
            return issues
        if n <= 30:
            minimum = 3
            criterion = "n ≤ 30: mínimo de 3 por característica"
        elif n <= 100:
            minimum = max(3, int(math.ceil(0.10 * n)))
            criterion = f"30 < n ≤ 100: mínimo de 10% de {n} = {minimum}"
        else:
            minimum = 10
            criterion = "n > 100: mínimo de 10 por característica"
        for spec in self.x_specs(True):
            column = spec["name"]
            column_type = self.column_types.get(column)
            if column_type not in CATEGORICAL_TYPES:
                continue
            values = pd.to_numeric(
                self.df[column], errors="coerce"
            )[self.active_mask()].dropna()
            counts = values.value_counts()
            for code, count in counts.items():
                if int(count) < minimum:
                    issues.append({
                        "variable": column,
                        "type": column_type,
                        "code": float(code),
                        "count": int(count),
                        "minimum": int(minimum),
                        "sample_size": int(n),
                        "criterion": criterion,
                        "text": (
                            f"Micronumerosidade: “{column}” tem apenas {int(count)} "
                            f"imóvel(is) com o código {format_number(code, 0)} "
                            f"(mínimo exigido: {minimum}; {criterion}). "
                            "Isso pode distorcer o modelo."
                        ),
                    })
        return issues

    def set_column_type(self, column: str, column_type: str) -> None:
        if column not in self.df.columns:
            raise ValueError("Coluna inexistente.")
        if column_type not in COLUMN_TYPES:
            raise ValueError("Tipo de coluna inválido.")
        if column_type == TEXT_TYPE:
            self.column_types[column] = TEXT_TYPE
            if self.y_column == column:
                self.y_column = None
            if column in self.x_config:
                self.x_config[column]["selected"] = False
            if self.label_column is None:
                self.label_column = column
            self._touch()
            return
        if self.df[column].dtype == object:
            values: list[float] = []
            for raw in self.df[column].tolist():
                if is_missing(raw):
                    values.append(np.nan)
                else:
                    try:
                        values.append(parse_number(raw))
                    except ValueError as exc:
                        raise ValueError(
                            f"A coluna “{column}” tem texto que não é número. "
                            "Corrija as células antes de mudar o tipo."
                        ) from exc
            self.df[column] = pd.Series(values, dtype="float64")
        self.column_types[column] = column_type
        if column_type in CATEGORICAL_TYPES:
            cfg = self.x_config.setdefault(
                column,
                {"selected": False, "transformation": "x", "expected_sign": 0, "description": ""},
            )
            cfg["transformation"] = "x"
        if self.label_column == column:
            self.label_column = None
        self._touch()

    def x_specs(self, only_selected: bool = True) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for col in self.df.columns:
            if not self.is_numeric(col) or col == self.y_column:
                continue
            cfg = self.x_config.get(col, {})
            if only_selected and not cfg.get("selected", False):
                continue
            specs.append({
                "name": col,
                "type": self.column_types.get(col, "Quantitativa"),
                "transformation": cfg.get("transformation", "x"),
                "expected_sign": int(cfg.get("expected_sign", 0)),
                "description": str(cfg.get("description", "") or ""),
            })
        return specs

    def model_spec(self) -> dict[str, Any]:
        return {
            "y": self.y_column,
            "y_transform": self.y_transform,
            "x": self.x_specs(True),
        }

    def apply_model_spec(self, spec: dict[str, Any]) -> None:
        y = spec.get("y")
        if y not in self.df.columns:
            raise ValueError("A equação usa uma variável que não existe na tabela.")
        self.y_column = y
        self.y_transform = spec.get("y_transform", "x")
        selected = {item["name"]: item for item in spec.get("x", [])}
        for col in self.df.columns:
            if not self.is_numeric(col):
                continue
            item = selected.get(col)
            if item:
                previous = self.x_config.get(col, {})
                self.x_config[col] = {
                    "selected": True,
                    "transformation": item.get("transformation", "x"),
                    "expected_sign": int(item.get("expected_sign", 0)),
                    "description": previous.get("description", ""),
                }
            elif col in self.x_config:
                self.x_config[col]["selected"] = False
        self._touch()

    # ------------------------------------------------------------- validação
    def validate(self) -> tuple[list[str], list[str]]:
        """Devolve (erros, avisos) em linguagem simples."""
        errors: list[str] = []
        warnings: list[str] = []
        if not self.has_data():
            errors.append("Ainda não há dados. Importe uma planilha ou abra o exemplo.")
            return errors, warnings
        if self.n_active == 0:
            errors.append("Todos os imóveis estão desligados. Reative pelo menos três imóveis.")
            return errors, warnings
        if not self.y_column:
            errors.append("Escolha a variável dependente (Y), que é o valor a explicar.")
        elif self.y_column not in self.df.columns:
            errors.append("A variável dependente escolhida não existe mais na tabela.")
        elif self.column_types.get(self.y_column) == TEXT_TYPE:
            errors.append("A variável dependente precisa ser numérica.")
        elif self.y_column not in self.numeric_columns():
            errors.append("A variável dependente precisa ser numérica.")
        specs = self.x_specs(True)
        if not specs:
            errors.append("Escolha pelo menos uma variável independente (X).")
        for spec in specs:
            col = spec["name"]
            transform = spec["transformation"]
            if col == self.y_column:
                errors.append(f"A variável “{col}” não pode ser X e Y ao mesmo tempo.")
                continue
            if self.column_types.get(col) == TEXT_TYPE:
                errors.append(f"A coluna de texto “{col}” não pode entrar no modelo.")
                continue
            series = pd.to_numeric(self.df[col], errors="coerce")
            active_values = series[self.active_mask()].dropna()
            if len(active_values) == 0:
                errors.append(f"A variável “{col}” não tem valores nos imóveis ligados.")
                continue
            if transform in ("ln(x)", "1/x") and (active_values <= 0).any():
                errors.append(
                    f"Não é possível usar {transform} em “{col}”: há valor zero ou negativo. "
                    "Troque a transformação ou corrija os dados."
                )
            if transform == "√x" and (active_values < 0).any():
                errors.append(f"Não é possível usar √x em “{col}”: há valor negativo.")
            if self.column_types.get(col) in CATEGORICAL_TYPES and transform != "x":
                errors.append(
                    f"“{col}” é {self.column_types.get(col)} e só pode usar x."
                )
            if self.column_types.get(col) == "Código alocado":
                if not np.allclose(active_values % 1, 0):
                    warnings.append(
                        f"“{col}” está marcada como Código alocado, mas tem números quebrados. "
                        "Use números inteiros começando em 1."
                    )
                elif len(active_values) and active_values.min() < 1:
                    warnings.append(
                        f"“{col}” está marcada como Código alocado, mas há código menor que 1. "
                        "O recomendado é começar em 1."
                    )
            if self.column_types.get(col) == "Dicotômica":
                counts = active_values.value_counts()
                if len(counts) < 2:
                    warnings.append(
                        f"A variável “{col}” é dicotômica mas só tem um valor nos imóveis ligados. "
                        "Confira os dados."
                    )
        for issue in self.micronumerosity_issues():
            if issue["text"] not in warnings:
                warnings.append(issue["text"])
        if self.y_column:
            y_values = pd.to_numeric(self.df[self.y_column], errors="coerce")[self.active_mask()].dropna()
            if self.y_transform in ("ln(x)", "1/x") and len(y_values) and (y_values <= 0).any():
                errors.append(
                    f"A transformação {self.y_transform} em Y exige valores maiores que zero. "
                    "Corrija os valores ou use x."
                )
            if len(y_values) < 3:
                warnings.append("Há menos de três valores de Y nos imóveis ligados.")
        total_cells = self.n_active * (len(specs) + (1 if self.y_column else 0))
        if total_cells:
            used = pd.Series(True, index=self.df.index[self.active_mask()])
            for col in [self.y_column] + [s["name"] for s in specs]:
                if col:
                    used &= self.df.loc[self.active_mask(), col].notna().to_numpy()
            dropped = int(self.n_active - used.sum())
            if dropped:
                warnings.append(
                    f"{dropped} imóvel(is) ligado(s) têm vazio em Y ou X e sairão do cálculo "
                    "só neste modelo (exclusão pela lista completa)."
                )
        return errors, warnings

    def listwise_indices(self) -> list[int]:
        """Posições dos imóveis ativos com Y e todos os X preenchidos."""
        specs = self.x_specs(True)
        columns = [self.y_column] + [s["name"] for s in specs if s["name"] != self.y_column]
        positions: list[int] = []
        for i, active in enumerate(self.active):
            if not active:
                continue
            ok = True
            for col in columns:
                if col and is_missing(self.df.iloc[i][col]):
                    ok = False
                    break
            if ok:
                positions.append(i)
        return positions

    # -------------------------------------------------------------- edição
    def _check_column_name(self, name: str) -> str:
        name = str(name).strip()
        if not name:
            raise ValueError("O nome da coluna não pode ficar vazio.")
        if name in self.df.columns:
            raise ValueError(f"Já existe uma coluna chamada “{name}”.")
        return name

    def add_column(self, name: str, values: Optional[Iterable[Any]] = None,
                   column_type: str = "Quantitativa") -> str:
        self.push_undo()
        name = self._check_column_name(name)
        if values is None:
            values = [np.nan] * len(self.df)
        values = list(values)
        if len(values) != len(self.df):
            raise ValueError("A nova coluna precisa ter um valor para cada linha.")
        if column_type != TEXT_TYPE:
            converted = []
            for raw in values:
                if is_missing(raw):
                    converted.append(np.nan)
                else:
                    try:
                        converted.append(parse_number(raw))
                    except ValueError:
                        converted.append(np.nan)
            series = pd.Series(converted, dtype="float64")
        else:
            series = pd.Series([None if is_missing(v) else safe_str(v) for v in values], dtype="object")
        self.df[name] = series
        self.column_types[name] = column_type
        self.x_config[name] = {"selected": False, "transformation": "x", "expected_sign": 0, "description": ""}
        self._touch()
        return name

    def rename_column(self, old: str, new: str) -> None:
        if old not in self.df.columns:
            raise ValueError("A coluna escolhida não existe.")
        new = self._check_column_name(new)
        self.push_undo()
        self.df = self.df.rename(columns={old: new})
        self.column_types[new] = self.column_types.pop(old, "Quantitativa")
        if old in self.x_config:
            self.x_config[new] = self.x_config.pop(old)
        if self.label_column == old:
            self.label_column = new
        if self.y_column == old:
            self.y_column = new
        if self.cluster_column == old:
            self.cluster_column = new
        for item in self.evaluated:
            values = item.get("values", {})
            if old in values:
                values[new] = values.pop(old)
        self._touch()

    def delete_column(self, column: str) -> None:
        if column not in self.df.columns:
            raise ValueError("A coluna escolhida não existe.")
        self.push_undo()
        self.df = self.df.drop(columns=[column])
        self.column_types.pop(column, None)
        self.x_config.pop(column, None)
        if self.label_column == column:
            self.label_column = None
        if self.y_column == column:
            self.y_column = None
        if self.cluster_column == column:
            self.cluster_column = None
        for item in self.evaluated:
            item.get("values", {}).pop(column, None)
        self._touch()

    def add_row(self, values: Optional[dict[str, Any]] = None) -> int:
        self.push_undo()
        row: dict[str, Any] = {}
        for col in self.df.columns:
            value = (values or {}).get(col)
            if self.column_types.get(col) == TEXT_TYPE:
                row[col] = None if is_missing(value) else safe_str(value)
            else:
                if is_missing(value):
                    row[col] = np.nan
                else:
                    try:
                        row[col] = parse_number(value)
                    except ValueError:
                        row[col] = np.nan
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        self.active.append(True)
        self.row_ids.append(self._new_row_id())
        self._touch()
        return len(self.df) - 1

    def delete_rows(self, positions: Iterable[int]) -> int:
        positions = sorted({int(i) for i in positions if 0 <= int(i) < len(self.df)}, reverse=True)
        if not positions:
            return 0
        self.push_undo()
        for pos in positions:
            self.df = self.df.drop(self.df.index[pos]).reset_index(drop=True)
            del self.active[pos]
            del self.row_ids[pos]
        self._touch()
        return len(positions)

    def update_cell(self, position: int, column: str, raw_value: Any) -> None:
        if not (0 <= position < len(self.df)) or column not in self.df.columns:
            raise ValueError("Célula inválida.")
        if self.column_types.get(column) == TEXT_TYPE:
            self.df.at[position, column] = None if is_missing(raw_value) else safe_str(raw_value)
        else:
            if is_missing(raw_value):
                self.df.at[position, column] = np.nan
            else:
                self.df.at[position, column] = parse_number(raw_value)
        self._touch()

    def toggle_active(self, position: int, active: bool) -> None:
        if 0 <= position < len(self.active):
            self.active[position] = bool(active)
            self._touch()

    def deactivate_many(self, positions: Iterable[int]) -> int:
        positions = [int(i) for i in positions if 0 <= int(i) < len(self.active) and self.active[int(i)]]
        if not positions:
            return 0
        self.push_undo()
        for pos in positions:
            self.active[pos] = False
        self._touch()
        return len(positions)

    def reactivate_all(self) -> int:
        changed = sum(1 for a in self.active if not a)
        if changed:
            self.push_undo()
            self.active = [True] * len(self.active)
            self._touch()
        return changed

    def sort_by(self, column: str, ascending: bool = True) -> None:
        if column not in self.df.columns:
            raise ValueError("A coluna escolhida não existe.")
        self.push_undo()
        if self.column_types.get(column) == TEXT_TYPE:
            order = self.df[column].fillna("").astype(str).str.lower().argsort(kind="mergesort")
        else:
            numeric = pd.to_numeric(self.df[column], errors="coerce")
            order = numeric.sort_values(na_position="last", kind="mergesort").index.to_numpy()
        if not ascending:
            order = order[::-1]
        self.df = self.df.iloc[order].reset_index(drop=True)
        self.active = [self.active[i] for i in order]
        self.row_ids = [self.row_ids[i] for i in order]

    def add_calculated_column(self, name: str, column_a: str, operator: str,
                              column_b: Optional[str] = None,
                              constant: Optional[float] = None) -> str:
        if column_a not in self.df.columns:
            raise ValueError("Escolha a coluna A.")
        if operator not in ("+", "−", "×", "÷"):
            raise ValueError("Escolha uma operação.")
        if column_b is not None and column_b not in self.df.columns:
            raise ValueError("Escolha a coluna B.")
        if column_b is None and constant is None:
            raise ValueError("Escolha a coluna B ou digite uma constante.")
        if self.column_types.get(column_a) == TEXT_TYPE or (column_b and self.column_types.get(column_b) == TEXT_TYPE):
            raise ValueError("As colunas da conta precisam ser numéricas.")
        self.push_undo()
        name = self._check_column_name(name)
        a = pd.to_numeric(self.df[column_a], errors="coerce")
        b = pd.to_numeric(self.df[column_b], errors="coerce") if column_b else float(constant)
        if operator == "+":
            result = a + b
        elif operator == "−":
            result = a - b
        elif operator == "×":
            result = a * b
        else:
            denominator = b if isinstance(b, pd.Series) else pd.Series([b] * len(self.df))
            if (denominator == 0).any():
                raise ValueError("A conta tem divisão por zero em pelo menos uma linha.")
            result = a / denominator
        if isinstance(result, pd.Series) and np.isinf(result).any():
            raise ValueError("A conta gerou um número infinito. Confira os valores.")
        self.df[name] = result.astype(float)
        self.column_types[name] = "Quantitativa"
        self.x_config[name] = {"selected": False, "transformation": "x", "expected_sign": 0, "description": ""}
        self._touch()
        return name

    def set_cluster_column(self, values: Iterable[Optional[int]], name: str = "Cluster") -> str:
        """Grava (ou substitui) a coluna Cluster. None = imóvel sem grupo."""
        values = list(values)
        if len(values) != len(self.df):
            raise ValueError("O cluster precisa ter um valor para cada imóvel.")
        self.push_undo()
        base = name
        counter = 2
        while name in self.df.columns and name != self.cluster_column:
            name = f"{base} {counter}"
            counter += 1
        if self.cluster_column and self.cluster_column in self.df.columns:
            self.df = self.df.drop(columns=[self.cluster_column])
            self.column_types.pop(self.cluster_column, None)
        converted = [np.nan if v is None else int(v) for v in values]
        self.df[name] = pd.Series(converted, dtype="float64")
        self.column_types[name] = "Código alocado"
        self.cluster_column = name
        self.x_config.setdefault(name, {"selected": False, "transformation": "x", "expected_sign": 0, "description": ""})
        self._touch()
        return name

    # -------------------------------------------------------------- avaliandos
    def add_evaluated(self, name: str, values: dict[str, Any]) -> dict[str, Any]:
        specs = self.x_specs(True)
        clean: dict[str, float] = {}
        for spec in specs:
            col = spec["name"]
            raw = values.get(col)
            if is_missing(raw):
                raise ValueError(f"Preencha o campo “{col}” do imóvel avaliando.")
            try:
                clean[col] = parse_number(raw)
            except ValueError as exc:
                raise ValueError(f"O campo “{col}” precisa ser um número.") from exc
        item = {
            "id": uuid.uuid4().hex,
            "name": str(name).strip() or f"Avaliando {len(self.evaluated) + 1}",
            "values": clean,
            "adopted": None,
            "use_arbitrio": False,
            "justification": "",
            "interval_mode": "IC",
            "round_limits": False,
        }
        self.evaluated.append(item)
        return item

    def update_evaluated(self, evaluated_id: str, *, name: Optional[str] = None,
                         values: Optional[dict[str, Any]] = None,
                         adopted: Any = "__unchanged__",
                         use_arbitrio: Optional[bool] = None,
                         justification: Optional[str] = None,
                         interval_mode: Optional[str] = None,
                         round_limits: Optional[bool] = None) -> dict[str, Any]:
        item = self.get_evaluated(evaluated_id)
        if name is not None:
            item["name"] = str(name).strip() or item["name"]
        if values is not None:
            clean: dict[str, float] = {}
            for spec in self.x_specs(True):
                col = spec["name"]
                try:
                    clean[col] = parse_number(values.get(col))
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"O campo “{col}” precisa ser um número.") from exc
            item["values"] = clean
        if adopted != "__unchanged__":
            if adopted is None or is_missing(adopted):
                item["adopted"] = None
            else:
                item["adopted"] = parse_number(adopted)
        if use_arbitrio is not None:
            item["use_arbitrio"] = bool(use_arbitrio)
        if justification is not None:
            item["justification"] = str(justification).strip()
        if interval_mode is not None:
            item["interval_mode"] = "IP" if str(interval_mode).upper() == "IP" else "IC"
        if round_limits is not None:
            item["round_limits"] = bool(round_limits)
        return item

    def get_evaluated(self, evaluated_id: str) -> dict[str, Any]:
        for item in self.evaluated:
            if item.get("id") == evaluated_id:
                item.setdefault("interval_mode", "IC")
                item.setdefault("round_limits", False)
                return item
        raise ValueError("Avaliando não encontrado.")

    def delete_evaluated(self, evaluated_id: str) -> None:
        self.evaluated = [e for e in self.evaluated if e.get("id") != evaluated_id]

    # ---------------------------------------------------------- import/export
    def copy_table_tsv(self) -> str:
        lines: list[str] = []
        header = ["Ativo"] + [str(c) for c in self.df.columns]
        lines.append("\t".join(header))
        for i, row in self.df.iterrows():
            cells = ["Sim" if self.active[i] else "Não"]
            for col in self.df.columns:
                value = row[col]
                if is_missing(value):
                    cells.append("")
                elif self.column_types.get(col) == TEXT_TYPE:
                    cells.append(safe_str(value))
                else:
                    cells.append(format_number(value, 2, thousands=False))
            lines.append("\t".join(cells))
        return "\n".join(lines)

    def to_state(self) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        for _, row in self.df.iterrows():
            records.append({str(c): _safe_json_value(row[c]) for c in self.df.columns})
        return {
            "version": 1,
            "metadata": copy.deepcopy(self.metadata),
            "columns": list(map(str, self.df.columns)),
            "column_types": dict(self.column_types),
            "data": records,
            "active": list(map(bool, self.active)),
            "row_ids": list(self.row_ids),
            "next_row_id": self._next_id,
            "label_column": self.label_column,
            "y_column": self.y_column,
            "y_transform": self.y_transform,
            "x_config": copy.deepcopy(self.x_config),
            "evaluated": copy.deepcopy(self.evaluated),
            "manual_grades": dict(self.manual_grades),
            "last_model": copy.deepcopy(self.last_model),
            "saved_equations": copy.deepcopy(self.saved_equations),
            "cluster_column": self.cluster_column,
            "source_path": self.source_path,
            "example_data": self.example_data,
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "DataManager":
        manager = cls()
        columns = [str(c) for c in state.get("columns", [])]
        records = state.get("data", [])
        if columns:
            frame = pd.DataFrame(records)
            for col in columns:
                if col not in frame.columns:
                    frame[col] = np.nan
            frame = frame[columns]
        else:
            frame = pd.DataFrame()
        manager.df = frame.reset_index(drop=True)
        manager.column_types = {str(k): str(v) for k, v in state.get("column_types", {}).items()}
        for col in manager.df.columns:
            if col not in manager.column_types:
                manager.column_types[col] = "Quantitativa"
            if manager.column_types[col] != TEXT_TYPE:
                manager.df[col] = pd.to_numeric(manager.df[col], errors="coerce").astype(float)
            else:
                manager.df[col] = manager.df[col].astype(object)
        active = state.get("active", [])
        manager.active = [bool(x) for x in active[: len(manager.df)]]
        if len(manager.active) < len(manager.df):
            manager.active += [True] * (len(manager.df) - len(manager.active))
        row_ids = state.get("row_ids", [])
        manager.row_ids = [int(x) for x in row_ids[: len(manager.df)]]
        if len(manager.row_ids) < len(manager.df):
            start = max(manager.row_ids, default=0) + 1
            manager.row_ids += list(range(start, start + len(manager.df) - len(manager.row_ids)))
        manager._next_id = int(state.get("next_row_id", max(manager.row_ids, default=0) + 1))
        manager.label_column = state.get("label_column")
        manager.y_column = state.get("y_column")
        manager.y_transform = state.get("y_transform", "x")
        if manager.y_transform not in TRANSFORMS:
            manager.y_transform = "x"
        manager.x_config = copy.deepcopy(state.get("x_config", {}))
        for col in manager.df.columns:
            cfg = manager.x_config.setdefault(col, {"selected": False, "transformation": "x", "expected_sign": 0, "description": ""})
            cfg.setdefault("selected", False)
            cfg.setdefault("transformation", "x")
            cfg.setdefault("expected_sign", 0)
        manager.evaluated = copy.deepcopy(state.get("evaluated", []))
        manager.manual_grades = {"item1": "II", "item3": "II"}
        manager.manual_grades.update({k: v for k, v in state.get("manual_grades", {}).items() if k in ("item1", "item3")})
        manager.last_model = copy.deepcopy(state.get("last_model"))
        manager.saved_equations = copy.deepcopy(state.get("saved_equations", []))
        manager.cluster_column = state.get("cluster_column")
        manager.source_path = state.get("source_path")
        manager.example_data = bool(state.get("example_data", False))
        manager.metadata = manager.default_metadata()
        manager.metadata.update(state.get("metadata", {}))
        return manager
