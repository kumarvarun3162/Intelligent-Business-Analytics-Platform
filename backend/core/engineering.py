import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple

from models.schemas import (
    TransformRecord, ValidationRule,
    EngineeringReport
)


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def _record(
    transforms: List[TransformRecord],
    column: str,
    transform: str,
    params: Dict[str, Any],
    new_columns: List[str],
    original_dtype: str,
    output_dtype: str,
    note: str,
) -> None:
    transforms.append(TransformRecord(
        column=column,
        transform=transform,
        params=params,
        new_columns=new_columns,
        original_dtype=original_dtype,
        output_dtype=output_dtype,
        note=note,
    ))


# ══════════════════════════════════════════════════════════════════
# STAGE 1 — Categorical encoding
# ══════════════════════════════════════════════════════════════════

# Cardinality thresholds that mirror the decision tree diagram
OHE_THRESHOLD   = 5   # ≤ this → one-hot encode
LABEL_THRESHOLD = 15  # ≤ this → label encode; > this → frequency encode


def encode_categoricals(
    df: pd.DataFrame,
    transforms: List[TransformRecord],
    type_map: Dict[str, str],
) -> pd.DataFrame:
    """
    Encode all categorical and boolean columns using the decision tree:

    cardinality ≤ OHE_THRESHOLD   → one-hot encoding
    cardinality ≤ LABEL_THRESHOLD → label encoding
    cardinality >  LABEL_THRESHOLD → frequency encoding

    Boolean columns are simply cast to int (0/1) — no encoding needed.

    Key concept — why we DON'T drop the first dummy (drop_first=False):
    Dropping the first dummy is common advice to avoid multicollinearity
    in linear regression. But for tree-based ML models and general EDA,
    keeping all dummies is clearer. The user can drop later if needed.
    """
    df = df.copy()
    cols_to_encode = [
        col for col, t in type_map.items()
        if t in ("categorical", "string", "boolean") and col in df.columns
    ]

    for col in cols_to_encode:
        original_dtype = str(df[col].dtype)
        cardinality    = df[col].nunique(dropna=True)

        # ── Boolean → int ────────────────────────────────────────
        if type_map.get(col) == "boolean":
            df[col] = df[col].astype(int)
            _record(transforms, col, "bool_to_int", {},
                    [col], original_dtype, "int64",
                    f"Cast boolean '{col}' to 0/1 integer")
            continue

        # ── One-hot encoding ─────────────────────────────────────
        if cardinality <= OHE_THRESHOLD:
            dummies = pd.get_dummies(
                df[col], prefix=col, dtype=int
            )
            # Clean column names (spaces → underscores)
            dummies.columns = [
                c.lower().replace(" ", "_").replace("-", "_")
                for c in dummies.columns
            ]
            df = pd.concat([df.drop(columns=[col]), dummies], axis=1)
            _record(transforms, col, "one_hot_encode",
                    {"cardinality": cardinality,
                     "categories": list(dummies.columns)},
                    list(dummies.columns),
                    original_dtype, "int64",
                    f"One-hot encoded '{col}' → {len(dummies.columns)} columns")
            # Update type_map for new columns
            for c in dummies.columns:
                type_map[c] = "integer"
            del type_map[col]

        # ── Label encoding ───────────────────────────────────────
        elif cardinality <= LABEL_THRESHOLD:
            categories = sorted(df[col].dropna().unique().tolist())
            label_map  = {v: i for i, v in enumerate(categories)}
            df[col]    = df[col].map(label_map)
            _record(transforms, col, "label_encode",
                    {"mapping": {str(k): v for k, v in label_map.items()}},
                    [col], original_dtype, "int64",
                    f"Label encoded '{col}': {len(categories)} categories → 0..{len(categories)-1}")
            type_map[col] = "integer"

        # ── Frequency encoding ───────────────────────────────────
        else:
            freq_map   = df[col].value_counts().to_dict()
            df[col]    = df[col].map(freq_map).astype(float)
            _record(transforms, col, "frequency_encode",
                    {"n_unique": cardinality,
                     "min_freq": int(min(freq_map.values())),
                     "max_freq": int(max(freq_map.values()))},
                    [col], original_dtype, "float64",
                    f"Frequency encoded '{col}': {cardinality} unique values → count-based float")
            type_map[col] = "float"

    return df

# ══════════════════════════════════════════════════════════════════
# STAGE 2 — Numeric scaling
# ══════════════════════════════════════════════════════════════════

def scale_numerics(
    df: pd.DataFrame,
    transforms: List[TransformRecord],
    type_map: Dict[str, str],
    method: str = "auto",
) -> pd.DataFrame:
    """
    Scale numeric columns.

    method options:
    - "auto"    → use the decision tree (robust if outliers, else minmax)
    - "minmax"  → force min-max for all numeric columns
    - "standard"→ force Z-score standardisation
    - "robust"  → force robust (median/IQR) scaling
    - "none"    → skip scaling entirely

    Why scaling matters:
    Without scaling, a column with values [0, 1] and a column with
    values [0, 1,000,000] will have the million-dollar column dominate
    distance-based algorithms (k-means, KNN, SVM) purely because of
    its magnitude — not because it's more important.
    """
    if method == "none":
        return df

    df = df.copy()
    numeric_cols = [
        col for col, t in type_map.items()
        if t in ("integer", "float") and col in df.columns
    ]

    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 2:
            continue

        original_dtype = str(df[col].dtype)

        # ── Auto-detect: check for outliers via IQR ─────────────
        Q1  = series.quantile(0.25)
        Q3  = series.quantile(0.75)
        IQR = Q3 - Q1
        has_outliers = False
        if IQR > 0:
            lower = Q1 - 1.5 * IQR
            upper = Q3 + 1.5 * IQR
            has_outliers = bool(((series < lower) | (series > upper)).any())

        chosen = method
        if method == "auto":
            chosen = "robust" if has_outliers else "minmax"

        # ── Apply chosen scaler ──────────────────────────────────

        if chosen == "minmax":
            col_min = float(series.min())
            col_max = float(series.max())
            denom   = col_max - col_min
            if denom == 0:
                continue  # constant column — skip
            df[col] = (df[col] - col_min) / denom
            _record(transforms, col, "minmax_scale",
                    {"min": round(col_min, 6), "max": round(col_max, 6)},
                    [col], original_dtype, "float64",
                    f"Min-max scaled '{col}' → [0, 1] "
                    f"(was [{col_min:.4g}, {col_max:.4g}])")

        elif chosen == "standard":
            mean = float(series.mean())
            std  = float(series.std())
            if std == 0:
                continue
            df[col] = (df[col] - mean) / std
            _record(transforms, col, "standard_scale",
                    {"mean": round(mean, 6), "std": round(std, 6)},
                    [col], original_dtype, "float64",
                    f"Z-score scaled '{col}' → mean=0, std=1")

        elif chosen == "robust":
            median = float(series.median())
            iqr    = float(IQR)
            if iqr == 0:
                continue
            df[col] = (df[col] - median) / iqr
            _record(transforms, col, "robust_scale",
                    {"median": round(median, 6), "iqr": round(iqr, 6)},
                    [col], original_dtype, "float64",
                    f"Robust scaled '{col}' using median={median:.4g}, IQR={iqr:.4g}")

        type_map[col] = "float"

    return df