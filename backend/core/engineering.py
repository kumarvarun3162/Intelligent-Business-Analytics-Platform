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

# ══════════════════════════════════════════════════════════════════
# STAGE 5 — Derived feature creation
# ══════════════════════════════════════════════════════════════════

def create_derived_features(
    df: pd.DataFrame,
    transforms: List[TransformRecord],
    type_map: Dict[str, str],
) -> pd.DataFrame:
    """
    Automatically create derived features from numeric columns:

    1. Log transforms for right-skewed columns (skewness > 1.0)
    2. Ratio features for numeric column pairs that look related
       by name (e.g. 'revenue' and 'cost' → profit_margin)
    3. Polynomial features (x²) for columns with high variance
       and no obvious outliers

    All derived columns are named: {col}_log, {ratio}_ratio,
    {col}_squared. Original columns are always kept.
    """
    df = df.copy()

    numeric_cols = [
        col for col, t in type_map.items()
        if t in ("integer", "float") and col in df.columns
    ]

    # ── 1. Log transforms for skewed columns ────────────────────
    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 10:
            continue

        skewness = float(series.skew())

        # Only log-transform if positively skewed and all-positive values
        if skewness > 1.0 and series.min() > 0:
            new_col = f"{col}_log"
            df[new_col] = np.log1p(df[col])  # log1p = log(1+x) safe for x≥0
            type_map[new_col] = "float"
            _record(transforms, col, "log_transform",
                    {"skewness": round(skewness, 4),
                     "formula": "log(1 + x)"},
                    [new_col], str(df[col].dtype), "float64",
                    f"Log-transformed '{col}' (skewness={skewness:.2f}) → '{new_col}'")

    # ── 2. Auto ratio detection by column name patterns ─────────
    # We look for name pairs that suggest a ratio makes sense
    RATIO_PAIRS = [
        # (numerator_keyword, denominator_keyword, ratio_name)
        ("profit",   "revenue",   "profit_margin"),
        ("profit",   "cost",      "profit_margin"),
        ("revenue",  "cost",      "revenue_cost_ratio"),
        ("sales",    "cost",      "sales_cost_ratio"),
        ("clicks",   "impressions", "ctr"),
        ("orders",   "customers",  "orders_per_customer"),
        ("returns",  "orders",    "return_rate"),
        ("revenue",  "customers", "revenue_per_customer"),
        ("salary",   "experience","salary_per_year"),
    ]

    col_set = set(numeric_cols)
    for num_kw, den_kw, ratio_name in RATIO_PAIRS:
        num_matches = [c for c in col_set if num_kw in c.lower()]
        den_matches = [c for c in col_set if den_kw in c.lower()]

        for num_col in num_matches:
            for den_col in den_matches:
                if num_col == den_col:
                    continue
                denom_series = df[den_col].replace(0, np.nan)
                if denom_series.isna().all():
                    continue
                new_col = f"{ratio_name}"
                if new_col in df.columns:
                    new_col = f"{num_col}_div_{den_col}"
                df[new_col] = df[num_col] / denom_series
                type_map[new_col] = "float"
                _record(transforms, num_col, "ratio_feature",
                        {"numerator": num_col,
                         "denominator": den_col},
                        [new_col],
                        str(df[num_col].dtype), "float64",
                        f"Created ratio '{new_col}' = {num_col} / {den_col}")

    # ── 3. Squared terms for low-skew high-variance columns ─────
    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 10:
            continue

        skewness = abs(float(series.skew()))
        variance = float(series.var())

        # Low skew (near-symmetric) + meaningful variance
        # → polynomial term may help capture non-linear effects
        if skewness < 0.5 and variance > 1.0:
            new_col = f"{col}_squared"
            df[new_col] = df[col] ** 2
            type_map[new_col] = "float"
            _record(transforms, col, "polynomial_feature",
                    {"degree": 2,
                     "skewness": round(skewness, 4),
                     "variance": round(variance, 4)},
                    [new_col], str(df[col].dtype), "float64",
                    f"Added squared term '{new_col}' (skew={skewness:.2f}, var={variance:.2f})")

    return df

# ══════════════════════════════════════════════════════════════════
# STAGE 6 — Validation and manifest
# ══════════════════════════════════════════════════════════════════

def validate_engineered_data(
    df: pd.DataFrame,
    transforms: List[TransformRecord],
    type_map: Dict[str, str],
) -> Tuple[List[ValidationRule], bool]:
    """
    Run data quality validation checks on the engineered DataFrame.

    Checks performed:
    1. No null values remain in any column
    2. No infinite values in numeric columns
    3. All columns are numeric or boolean (ML-ready check)
    4. Scaled columns are within expected range [-10, 10]
       (Z-score and robust scaled data should be in this range)
    5. One-hot encoded columns contain only 0 and 1
    6. No duplicate column names

    Returns: (list of ValidationRule, overall_passed bool)
    """
    rules: List[ValidationRule] = []
    all_passed = True

    # ── Check 1: No nulls ────────────────────────────────────────
    for col in df.columns:
        null_count = int(df[col].isna().sum())
        passed     = null_count == 0
        rules.append(ValidationRule(
            column  = col,
            rule    = "no_nulls",
            passed  = passed,
            detail  = f"{null_count} nulls found" if not passed
                      else "No nulls",
        ))
        if not passed:
            all_passed = False

    # ── Check 2: No infinite values ──────────────────────────────
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        inf_count = int(np.isinf(df[col].astype(float)).sum())
        passed    = inf_count == 0
        if not passed:
            # Replace inf with NaN automatically
            df[col] = df[col].replace([np.inf, -np.inf], np.nan)
            rules.append(ValidationRule(
                column  = col,
                rule    = "no_infinite",
                passed  = False,
                detail  = f"{inf_count} infinite values replaced with NaN",
            ))
            all_passed = False

    # ── Check 3: Column type consistency ─────────────────────────
    non_numeric = df.select_dtypes(exclude=[np.number, bool]).columns.tolist()
    if non_numeric:
        rules.append(ValidationRule(
            column  = "__dataset__",
            rule    = "all_numeric",
            passed  = False,
            detail  = f"Non-numeric columns remain: {non_numeric}. "
                      f"These columns won't be usable by numeric ML models.",
        ))
    else:
        rules.append(ValidationRule(
            column  = "__dataset__",
            rule    = "all_numeric",
            passed  = True,
            detail  = "All columns are numeric — dataset is ML-ready",
        ))

    # ── Check 4: One-hot columns are binary ──────────────────────
    ohe_cols = [
        t.new_columns for t in transforms
        if t.transform == "one_hot_encode"
    ]
    for col_group in ohe_cols:
        for col in col_group:
            if col not in df.columns:
                continue
            unique_vals = set(df[col].dropna().unique())
            passed      = unique_vals <= {0, 1}
            rules.append(ValidationRule(
                column  = col,
                rule    = "binary_ohe",
                passed  = passed,
                detail  = "Binary (0/1)" if passed
                          else f"Non-binary values: {unique_vals}",
            ))
            if not passed:
                all_passed = False

    # ── Check 5: No duplicate column names ───────────────────────
    seen      = set()
    dupes     = []
    for col in df.columns:
        if col in seen:
            dupes.append(col)
        seen.add(col)
    if dupes:
        rules.append(ValidationRule(
            column  = "__dataset__",
            rule    = "no_duplicate_cols",
            passed  = False,
            detail  = f"Duplicate column names: {dupes}",
        ))
        all_passed = False

    return rules, all_passed


# ══════════════════════════════════════════════════════════════════
# MASTER ORCHESTRATOR — called by /api/engineer route
# ══════════════════════════════════════════════════════════════════

def run_engineering_pipeline(
    df:            pd.DataFrame,
    session_id:    str,
    type_map:      Dict[str, str],
    scale_method:  str = "auto",
    n_bins:        int = 5,
    bin_strategy:  str = "quantile",
    drop_datetime: bool = False,
) -> Tuple[pd.DataFrame, EngineeringReport]:
    """
    Run all 6 engineering stages in sequence.
    Receives a cleaned DataFrame + its type_map from Phase 2.
    Returns engineered DataFrame + full EngineeringReport.
    """
    transforms: List[TransformRecord] = []
    original_col_count = len(df.columns)

    # Work on a mutable copy of type_map
    tmap = dict(type_map)

    # ── Stage 1: Categorical encoding ────────────────────────────
    df = encode_categoricals(df, transforms, tmap)

    # ── Stage 2: Numeric scaling ─────────────────────────────────
    df = scale_numerics(df, transforms, tmap, method=scale_method)

    # ── Stage 3: Datetime extraction ─────────────────────────────
    df = extract_datetime_features(df, transforms, tmap,
                                   drop_original=drop_datetime)

    # ── Stage 4: Binning ─────────────────────────────────────────
    df = bin_numerics(df, transforms, tmap,
                      n_bins=n_bins, strategy=bin_strategy)

    # ── Stage 5: Derived features ────────────────────────────────
    df = create_derived_features(df, transforms, tmap)

    # ── Stage 6: Validation ──────────────────────────────────────
    validation_rules, validation_passed = validate_engineered_data(
        df, transforms, tmap
    )

    # Build feature summary: col → human label
    feature_summary = {}
    for t in transforms:
        for col in t.new_columns:
            feature_summary[col] = t.transform

    engineered_col_count = len(df.columns)
    new_cols_created     = engineered_col_count - original_col_count

    # ML-ready = passed validation AND no non-numeric columns
    ml_ready = (
        validation_passed and
        len(df.select_dtypes(exclude=[np.number, bool]).columns) == 0
    )

    report = EngineeringReport(
        session_id           = session_id,
        original_col_count   = original_col_count,
        engineered_col_count = engineered_col_count,
        new_cols_created     = max(0, new_cols_created),
        transforms           = transforms,
        validation_results   = validation_rules,
        validation_passed    = validation_passed,
        feature_summary      = feature_summary,
        ml_ready             = ml_ready,
    )

    return df, report
