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

# ══════════════════════════════════════════════════════════════════
# STAGE 3 — Datetime feature extraction
# ══════════════════════════════════════════════════════════════════

def extract_datetime_features(
    df: pd.DataFrame,
    transforms: List[TransformRecord],
    type_map: Dict[str, str],
    drop_original: bool = False,
) -> pd.DataFrame:
    """
    Decompose datetime columns into interpretable numeric parts.

    Extracted parts per datetime column:
    ┌──────────────┬──────────────────────────────────────────┐
    │ {col}_year   │ Full year (2023)                         │
    │ {col}_month  │ 1–12                                     │
    │ {col}_day    │ 1–31                                     │
    │ {col}_weekday│ 0=Mon … 6=Sun                            │
    │ {col}_hour   │ 0–23 (0 if no time component)            │
    │ {col}_quarter│ 1–4                                      │
    │ {col}_is_wknd│ 1 if Sat or Sun, else 0                  │
    └──────────────┴──────────────────────────────────────────┘

    drop_original: if True, remove the original datetime column
    after extraction. Useful for ML pipelines that need pure numerics.
    """
    df = df.copy()
    datetime_cols = [
        col for col, t in type_map.items()
        if t == "datetime" and col in df.columns
    ]

    for col in datetime_cols:
        original_dtype = str(df[col].dtype)
        dt = pd.to_datetime(df[col], errors="coerce")

        new_cols = {}
        new_cols[f"{col}_year"]    = dt.dt.year
        new_cols[f"{col}_month"]   = dt.dt.month
        new_cols[f"{col}_day"]     = dt.dt.day
        new_cols[f"{col}_weekday"] = dt.dt.weekday          # 0=Mon
        new_cols[f"{col}_hour"]    = dt.dt.hour
        new_cols[f"{col}_quarter"] = dt.dt.quarter
        new_cols[f"{col}_is_wknd"] = (dt.dt.weekday >= 5).astype(int)

        for new_col, values in new_cols.items():
            df[new_col] = values.astype("Int64")
            type_map[new_col] = "integer"

        created = list(new_cols.keys())
        _record(transforms, col, "datetime_extract",
                {"parts": created, "drop_original": drop_original},
                created, original_dtype, "int64",
                f"Extracted {len(created)} features from datetime '{col}'")

        if drop_original:
            df = df.drop(columns=[col])
            del type_map[col]

    return df


# ══════════════════════════════════════════════════════════════════
# STAGE 4 — Binning and discretization
# ══════════════════════════════════════════════════════════════════

def bin_numerics(
    df: pd.DataFrame,
    transforms: List[TransformRecord],
    type_map: Dict[str, str],
    n_bins: int = 5,
    strategy: str = "quantile",
    cols_to_bin: List[str] = None,
) -> pd.DataFrame:
    """
    Discretize continuous numeric columns into labelled bins.

    strategy:
    - "quantile"    → equal-frequency bins (recommended default)
    - "uniform"     → equal-width bins

    We only bin columns with high cardinality (>20 unique values)
    by default. Binning a column with 3 unique values is pointless.

    New column naming: {col}_bin  (original column is kept)

    Why keep the original?
    Binning creates a new perspective on the data, but the original
    continuous column still has value. We add both to the DataFrame.
    The user can drop originals in Phase 6 export if needed.
    """
    df = df.copy()

    if cols_to_bin is None:
        # Auto-select: high-cardinality numeric columns
        cols_to_bin = [
            col for col, t in type_map.items()
            if t in ("integer", "float")
            and col in df.columns
            and df[col].nunique() > 20
        ]

    bin_labels = [f"q{i+1}" for i in range(n_bins)]  # q1, q2, q3, q4, q5

    for col in cols_to_bin:
        if col not in df.columns:
            continue
        original_dtype = str(df[col].dtype)
        new_col = f"{col}_bin"

        try:
            if strategy == "quantile":
                # duplicates="drop" handles cases where quantile edges overlap
                binned = pd.qcut(
                    df[col], q=n_bins,
                    labels=bin_labels[:n_bins],
                    duplicates="drop"
                )
            else:
                binned = pd.cut(
                    df[col], bins=n_bins,
                    labels=bin_labels[:n_bins],
                )

            df[new_col]      = binned.astype(str)
            type_map[new_col] = "categorical"

            # Record actual bin edges for the manifest
            if strategy == "quantile":
                edges = list(pd.qcut(df[col], q=n_bins,
                                     duplicates="drop", retbins=True)[1])
            else:
                edges = list(pd.cut(df[col], bins=n_bins, retbins=True)[1])

            _record(transforms, col, f"bin_{strategy}",
                    {"n_bins": n_bins,
                     "edges": [round(float(e), 4) for e in edges],
                     "labels": bin_labels[:n_bins]},
                    [new_col], original_dtype, "category",
                    f"Binned '{col}' → '{new_col}' "
                    f"({strategy}, {n_bins} bins)")

        except Exception as e:
            # Silently skip columns that can't be binned
            # (e.g. too many duplicate values for quantile cuts)
            continue

    return df