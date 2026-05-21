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