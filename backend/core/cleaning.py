# backend/core/cleaning.py

import re
import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Any

from models.schemas import CleaningAction, OutlierInfo, CleaningReport


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def _log(
    actions: List[CleaningAction],
    stage: str,
    action: str,
    rows_affected: int,
    detail: str,
    column: str = None,
) -> None:
    """Append one cleaning action to the audit log."""
    actions.append(CleaningAction(
        stage=stage,
        column=column,
        action=action,
        rows_affected=rows_affected,
        detail=detail,
    ))


# ══════════════════════════════════════════════════════════════════
# STAGE 1 — Column type inference
# ══════════════════════════════════════════════════════════════════

def infer_and_cast_types(
    df: pd.DataFrame,
    actions: List[CleaningAction],
) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Intelligently infer the true data type of each column and cast it.

    Why we do this manually instead of trusting pandas:
    Pandas read_csv uses simple heuristics. A column like ["1","2","3.5"]
    may stay as object. Worse, mixed columns like ["25", "N/A", "30"]
    will definitely stay as object because of the "N/A" string.

    Our strategy:
    1. Try numeric conversion (int → float → keep as-is)
    2. Try datetime conversion
    3. Detect boolean-like columns ("yes/no", "true/false", "0/1")
    4. If cardinality is low → categorical
    5. Otherwise → string (object)
    """
    df = df.copy()
    type_map: Dict[str, str] = {}

    # Common strings that mean "missing" — replace with actual NaN
    NA_STRINGS = {
        "na", "n/a", "nan", "null", "none", "nil",
        "-", "--", "?", "unknown", "undefined", "",
        "missing", "not available", "n.a.", "na.",
    }

    BOOL_TRUE  = {"yes", "true", "1", "y", "t", "on"}
    BOOL_FALSE = {"no", "false", "0", "n", "f", "off"}

    for col in df.columns:
        series = df[col]

        # ── Replace NA-like strings with NaN ───────────────────
        if series.dtype == object:
            mask = series.astype(str).str.strip().str.lower().isin(NA_STRINGS)
            if mask.sum() > 0:
                df[col] = series.mask(mask, other=np.nan)
                _log(actions, "type_inference", "replaced_na_strings",
                     int(mask.sum()), f"Replaced {mask.sum()} NA-like strings with NaN",
                     column=col)
            series = df[col]

        non_null = series.dropna()

        # ── Boolean detection ───────────────────────────────────
        if series.dtype == object and len(non_null) > 0:
            lower_vals = set(non_null.astype(str).str.strip().str.lower().unique())
            if lower_vals <= (BOOL_TRUE | BOOL_FALSE):
                df[col] = non_null.astype(str).str.strip().str.lower().map(
                    lambda v: True if v in BOOL_TRUE else False
                )
                type_map[col] = "boolean"
                _log(actions, "type_inference", "cast_boolean", len(non_null),
                     f"Cast '{col}' to boolean", column=col)
                continue

        # ── Numeric detection ───────────────────────────────────
        if series.dtype == object:
            try:
                # Remove currency symbols and commas before trying
                cleaned = series.astype(str).str.replace(
                    r"[,$£€%\s]", "", regex=True
                )
                numeric = pd.to_numeric(cleaned, errors="coerce")
                # Accept if ≥80% of non-null values parsed successfully
                success_rate = numeric.notna().sum() / max(len(series), 1)
                if success_rate >= 0.8:
                    df[col] = numeric
                    # Use int if no decimal part
                    if numeric.dropna().apply(float.is_integer).all():
                        df[col] = numeric.astype("Int64")  # nullable int
                        type_map[col] = "integer"
                    else:
                        type_map[col] = "float"
                    _log(actions, "type_inference", "cast_numeric", len(non_null),
                         f"Cast '{col}' to {type_map[col]}", column=col)
                    continue
            except Exception:
                pass

        # ── Datetime detection ──────────────────────────────────
        if series.dtype == object:
            try:
                parsed = pd.to_datetime(series, infer_format=True, 
                                        errors="coerce")
                success_rate = parsed.notna().sum() / max(len(series), 1)
                if success_rate >= 0.7:
                    df[col] = parsed
                    type_map[col] = "datetime"
                    _log(actions, "type_inference", "cast_datetime", len(non_null),
                         f"Cast '{col}' to datetime", column=col)
                    continue
            except Exception:
                pass

        # ── Categorical detection ───────────────────────────────
        # Low cardinality relative to total rows = categorical
        if series.dtype == object:
            cardinality_ratio = series.nunique() / max(len(series), 1)
            if cardinality_ratio < 0.05 or series.nunique() < 20:
                df[col] = series.astype("category")
                type_map[col] = "categorical"
            else:
                type_map[col] = "string"

        if col not in type_map:
            type_map[col] = str(df[col].dtype)

    return df, type_map


# ══════════════════════════════════════════════════════════════════
# STAGE 2 — Missing value handling
# ══════════════════════════════════════════════════════════════════

def handle_missing_values(
    df: pd.DataFrame,
    actions: List[CleaningAction],
    type_map: Dict[str, str],
    null_drop_threshold: float = 0.5,
) -> pd.DataFrame:
    """
    Handle missing values column by column using the appropriate strategy.

    Decision logic per column:
    ┌─────────────────────────────────────────────────────────────┐
    │ null% > 50%      → drop the column entirely                 │
    │ numeric column   → impute with MEDIAN (outlier-robust)      │
    │ categorical/str  → impute with MODE (most frequent)         │
    │ datetime column  → forward fill then backward fill          │
    │ boolean column   → impute with mode                         │
    └─────────────────────────────────────────────────────────────┘

    Why median over mean?
    If your salary column has one value of 10,000,000 (data entry error),
    the mean gets pulled up dramatically. The median is not affected.
    """
    df = df.copy()
    cols_to_drop = []

    for col in df.columns:
        null_count = int(df[col].isna().sum())
        if null_count == 0:
            continue

        null_pct = null_count / len(df)
        inferred_type = type_map.get(col, "string")

        # ── Drop if too many nulls ──────────────────────────────
        if null_pct > null_drop_threshold:
            cols_to_drop.append(col)
            _log(actions, "missing_values", "dropped_column", null_count,
                 f"Dropped '{col}': {null_pct:.1%} nulls exceeds threshold",
                 column=col)
            continue

        # ── Numeric: median imputation ──────────────────────────
        if inferred_type in ("integer", "float"):
            median_val = df[col].median()
            df[col] = df[col].fillna(median_val)
            _log(actions, "missing_values", "imputed_median", null_count,
                 f"Imputed {null_count} nulls with median={median_val:.4g}",
                 column=col)

        # ── Datetime: forward then backward fill ────────────────
        elif inferred_type == "datetime":
            df[col] = df[col].ffill().bfill()
            _log(actions, "missing_values", "forward_fill", null_count,
                 f"Forward/backward filled {null_count} datetime nulls",
                 column=col)

        # ── Categorical / string / boolean: mode imputation ─────
        else:
            if df[col].dropna().empty:
                df[col] = df[col].fillna("unknown")
                _log(actions, "missing_values", "filled_unknown", null_count,
                     f"No non-null values; filled with 'unknown'",
                     column=col)
            else:
                mode_val = df[col].mode()[0]
                df[col] = df[col].fillna(mode_val)
                _log(actions, "missing_values", "imputed_mode", null_count,
                     f"Imputed {null_count} nulls with mode='{mode_val}'",
                     column=col)

    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)

    return df