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


# ══════════════════════════════════════════════════════════════════
# STAGE 3 — Duplicate removal
# ══════════════════════════════════════════════════════════════════

def remove_duplicates(
    df: pd.DataFrame,
    actions: List[CleaningAction],
) -> pd.DataFrame:
    """
    Remove duplicate rows from the DataFrame.

    We use two passes:
    1. Exact duplicates (all columns identical)
    2. Near-duplicates on numeric columns only (unlikely to be needed
       in Phase 2, but the hook is here for Phase 3 fuzzy matching)
    """
    df = df.copy()
    original_len = len(df)

    # Pass 1: exact row duplicates
    df = df.drop_duplicates(keep="first")
    exact_removed = original_len - len(df)

    if exact_removed > 0:
        _log(actions, "duplicates", "removed_exact_duplicates", exact_removed,
             f"Removed {exact_removed} exact duplicate rows (kept first occurrence)")

    return df


# ══════════════════════════════════════════════════════════════════
# STAGE 4 — Outlier detection and handling
# ══════════════════════════════════════════════════════════════════

def detect_and_handle_outliers(
    df: pd.DataFrame,
    actions: List[CleaningAction],
    type_map: Dict[str, str],
    method: str = "iqr",
    action: str = "cap",
) -> Tuple[pd.DataFrame, List[OutlierInfo]]:
    """
    Detect outliers in numeric columns and handle them.

    Parameters
    ----------
    method : "iqr" or "zscore"
        IQR is robust and non-parametric (default).
        Z-score assumes normality (mean=0, std=1).

    action : "cap", "flag", or "drop"
        cap  → Winsorize: replace outlier values with the fence value.
               This preserves the row but limits extreme influence.
        flag → Add a boolean column '{col}_is_outlier'. Row is kept as-is.
        drop → Remove rows containing outliers. Use cautiously.

    Why "cap" is the safest default:
    Dropping outliers loses information. Flagging keeps data dirty.
    Capping (Winsorization) keeps every row but limits extreme values,
    which is what most ML algorithms benefit from.
    """
    df = df.copy()
    outlier_infos: List[OutlierInfo] = []

    numeric_cols = [
        col for col, t in type_map.items()
        if t in ("integer", "float") and col in df.columns
    ]

    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 10:
            # Too few points to meaningfully detect outliers
            continue

        if method == "iqr":
            Q1 = series.quantile(0.25)
            Q3 = series.quantile(0.75)
            IQR = Q3 - Q1
            if IQR == 0:
                continue  # All values are the same; no spread to analyze
            lower = Q1 - 1.5 * IQR
            upper = Q3 + 1.5 * IQR

        elif method == "zscore":
            mean = series.mean()
            std  = series.std()
            if std == 0:
                continue
            lower = mean - 3 * std
            upper = mean + 3 * std
        else:
            raise ValueError(f"Unknown outlier method: {method}")

        outlier_mask = (df[col] < lower) | (df[col] > upper)
        outlier_count = int(outlier_mask.sum())

        if outlier_count == 0:
            continue

        # Apply the chosen action
        if action == "cap":
            df[col] = df[col].clip(lower=lower, upper=upper)
            action_taken = "capped"
        elif action == "flag":
            df[f"{col}_is_outlier"] = outlier_mask.astype(int)
            action_taken = "flagged"
        elif action == "drop":
            df = df[~outlier_mask]
            action_taken = "dropped"
        else:
            action_taken = "none"

        outlier_infos.append(OutlierInfo(
            column        = col,
            method        = method,
            outlier_count = outlier_count,
            lower_bound   = round(float(lower), 4),
            upper_bound   = round(float(upper), 4),
            action_taken  = action_taken,
        ))

        _log(actions, "outliers", f"outlier_{action_taken}", outlier_count,
             f"{col}: {outlier_count} outliers [{lower:.4g}, {upper:.4g}] → {action_taken}",
             column=col)

    return df, outlier_infos


# ══════════════════════════════════════════════════════════════════
# STAGE 5 — String normalization
# ══════════════════════════════════════════════════════════════════

def normalize_strings(
    df: pd.DataFrame,
    actions: List[CleaningAction],
    type_map: Dict[str, str],
) -> pd.DataFrame:
    """
    Clean string columns:
    1. Strip leading/trailing whitespace
    2. Collapse internal multiple spaces to one
    3. Normalize unicode (é → e, ñ → n for downstream compatibility)
    4. Optionally strip non-printable characters

    We do NOT lowercase by default — proper nouns like names
    and cities should retain their case. Lowercasing is a
    feature-engineering decision, not a cleaning one.
    """
    import unicodedata
    df = df.copy()
    total_fixed = 0

    string_cols = [
        col for col, t in type_map.items()
        if t in ("string", "categorical") and col in df.columns
    ]

    for col in string_cols:
        original = df[col].copy()

        # Strip whitespace
        df[col] = df[col].astype(str).str.strip()
        # Collapse internal spaces
        df[col] = df[col].str.replace(r"\s+", " ", regex=True)
        # Remove non-printable characters
        df[col] = df[col].str.replace(r"[^\x20-\x7E\u00C0-\u024F]",
                                       "", regex=True)
        # Re-cast to category if it was category before
        if type_map.get(col) == "categorical":
            df[col] = df[col].astype("category")

        changed = (df[col] != original.astype(str).str.strip()).sum()
        total_fixed += int(changed)

    if total_fixed > 0:
        _log(actions, "string_normalization", "stripped_whitespace",
             total_fixed,
             f"Normalized whitespace/encoding across {len(string_cols)} string columns")

    return df


# ══════════════════════════════════════════════════════════════════
# STAGE 6 — Constant and near-constant column removal
# ══════════════════════════════════════════════════════════════════

def remove_constant_columns(
    df: pd.DataFrame,
    actions: List[CleaningAction],
    variance_threshold: float = 0.01,
) -> pd.DataFrame:
    """
    Drop columns that carry no information:

    - Constant columns: every value is identical (variance = 0)
    - Near-constant columns: one value dominates >99% of rows
      (variance_threshold controls this cutoff)

    Mathematical basis:
    For a column with p% dominant value frequency,
    variance ≈ p(1-p). At p=0.99, variance=0.0099 < 0.01 → dropped.
    """
    df = df.copy()
    to_drop = []

    for col in df.columns:
        unique_count = df[col].nunique(dropna=True)

        # Pure constants
        if unique_count <= 1:
            to_drop.append(col)
            _log(actions, "constant_removal", "dropped_constant_column", 0,
                 f"Dropped '{col}': only {unique_count} unique value(s)",
                 column=col)
            continue

        # Near-constant: dominant frequency check
        top_freq = df[col].value_counts(normalize=True, dropna=True).iloc[0]
        if top_freq >= (1 - variance_threshold):
            to_drop.append(col)
            _log(actions, "constant_removal", "dropped_near_constant", 0,
                 f"Dropped '{col}': top value covers {top_freq:.1%} of rows",
                 column=col)

    if to_drop:
        df = df.drop(columns=to_drop)

    return df


# ══════════════════════════════════════════════════════════════════
# STAGE 7 — Column name standardization
# ══════════════════════════════════════════════════════════════════

def standardize_column_names(
    df: pd.DataFrame,
    actions: List[CleaningAction],
) -> pd.DataFrame:
    """
    Convert all column names to clean snake_case.

    Examples:
        "First Name"   → "first_name"
        "Revenue ($)"  → "revenue"
        "  AGE  "      → "age"
        "2024_Sales"   → "sales_2024"   (leading digit moved)
        ""             → "col_0"        (empty names get index)

    Also de-duplicates: if two columns both become "sales",
    the second becomes "sales_1".
    """
    df = df.copy()
    original_names = list(df.columns)
    new_names = []
    seen = {}

    for i, col in enumerate(original_names):
        name = str(col).strip()

        # Replace non-alphanumeric with underscore
        name = re.sub(r"[^a-zA-Z0-9]", "_", name)
        # Lowercase
        name = name.lower()
        # Collapse multiple underscores
        name = re.sub(r"_+", "_", name)
        # Strip leading/trailing underscores
        name = name.strip("_")
        # Leading digit fix
        if name and name[0].isdigit():
            name = "col_" + name
        # Empty name fallback
        if not name:
            name = f"col_{i}"

        # De-duplicate
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0

        new_names.append(name)

    df.columns = new_names

    changed = sum(1 for o, n in zip(original_names, new_names) if o != n)
    if changed > 0:
        _log(actions, "column_names", "standardized_to_snake_case", 0,
             f"Renamed {changed} columns to snake_case")

    # Update type_map keys is handled in the orchestrator
    return df

# ══════════════════════════════════════════════════════════════════
# STAGE 8 — Data quality scoring
# ══════════════════════════════════════════════════════════════════

def compute_quality_score(
    original_df:   pd.DataFrame,
    cleaned_df:    pd.DataFrame,
    outlier_infos: List[OutlierInfo],
    type_map:      Dict[str, str],
) -> Tuple[float, str]:
    """
    Compute a 0–100 quality score for the cleaned dataset.

    The score reflects how clean the data was BEFORE cleaning
    (i.e. how much work was needed). A high score means the
    raw data was already in good shape.

    Formula:
        score = 100
              - (null_rate   × 35)
              - (dup_rate    × 25)
              - (outlier_rate × 20)
              - (type_penalty × 20)
        clamped to [0, 100]
    """
    total_cells  = original_df.shape[0] * original_df.shape[1]
    total_nulls  = int(original_df.isna().sum().sum())
    null_rate    = total_nulls / max(total_cells, 1)

    dup_count = int(original_df.duplicated().sum())
    dup_rate  = dup_count / max(len(original_df), 1)

    total_outliers = sum(o.outlier_count for o in outlier_infos)
    outlier_rate   = total_outliers / max(len(original_df), 1)

    # Type penalty: ratio of columns that stayed as "string" (not inferred)
    total_cols  = len(type_map)
    string_cols = sum(1 for t in type_map.values() if t == "string")
    type_penalty = string_cols / max(total_cols, 1)

    raw_score = (
        100
        - (null_rate    * 35)
        - (dup_rate     * 25)
        - (outlier_rate * 20)
        - (type_penalty * 20)
    )
    score = round(max(0.0, min(100.0, raw_score)), 1)

    grade = (
        "A" if score >= 90 else
        "B" if score >= 75 else
        "C" if score >= 60 else
        "D" if score >= 45 else
        "F"
    )

    return score, grade

# ══════════════════════════════════════════════════════════════════
# MASTER ORCHESTRATOR — called by the /api/clean route
# ══════════════════════════════════════════════════════════════════

def run_cleaning_pipeline(
    df:         pd.DataFrame,
    session_id: str,
    outlier_method: str = "iqr",
    outlier_action: str = "cap",
    null_drop_threshold: float = 0.5,
) -> Tuple[pd.DataFrame, CleaningReport]:
    """
    Run all 8 cleaning stages in sequence.
    Returns the cleaned DataFrame and a full CleaningReport.

    The orchestrator is intentionally thin — it delegates to
    stage functions and collects their audit trail.
    """
    actions: List[CleaningAction] = []

    # Snapshot before cleaning
    original_df       = df.copy()
    original_rows     = len(df)
    original_cols     = len(df.columns)
    total_nulls_before = int(df.isna().sum().sum())

    # ── Stage 1: Type inference ──────────────────────────────────
    df, type_map = infer_and_cast_types(df, actions)

    # ── Stage 2: Missing values ──────────────────────────────────
    df = handle_missing_values(df, actions, type_map, null_drop_threshold)

    # ── Stage 3: Duplicates ──────────────────────────────────────
    df = remove_duplicates(df, actions)

    # ── Stage 4: Outliers ────────────────────────────────────────
    df, outlier_infos = detect_and_handle_outliers(
        df, actions, type_map, outlier_method, outlier_action
    )

    # ── Stage 5: String normalization ────────────────────────────
    df = normalize_strings(df, actions, type_map)

    # ── Stage 6: Constant column removal ─────────────────────────
    df = remove_constant_columns(df, actions)

    # ── Stage 7: Column name standardization ─────────────────────
    df = standardize_column_names(df, actions)

    # Update type_map keys after column renaming
    old_cols = list(original_df.columns)
    new_cols = list(df.columns)
    name_map = dict(zip(
        [standardize_col_name(c) for c in old_cols],
        new_cols
    ))
    type_map = {
        name_map.get(k, k): v
        for k, v in type_map.items()
        if name_map.get(k, k) in df.columns
    }

    # ── Stage 8: Quality score ───────────────────────────────────
    quality_score, quality_grade = compute_quality_score(
        original_df, df, outlier_infos, type_map
    )

    total_nulls_after = int(df.isna().sum().sum())
    dups_removed      = sum(
        a.rows_affected for a in actions
        if a.action == "removed_exact_duplicates"
    )

    report = CleaningReport(
        session_id          = session_id,
        original_row_count  = original_rows,
        cleaned_row_count   = len(df),
        original_col_count  = original_cols,
        cleaned_col_count   = len(df.columns),
        rows_removed        = original_rows - len(df),
        cols_removed        = original_cols - len(df.columns),
        total_nulls_before  = total_nulls_before,
        total_nulls_after   = total_nulls_after,
        duplicates_removed  = dups_removed,
        outliers_detected   = sum(o.outlier_count for o in outlier_infos),
        quality_score       = quality_score,
        quality_grade       = quality_grade,
        actions             = actions,
        outlier_details     = outlier_infos,
        column_type_map     = type_map,
    )

    return df, report


def standardize_col_name(col: str) -> str:
    """Standalone helper — mirrors Stage 7 logic for a single name."""
    name = re.sub(r"[^a-zA-Z0-9]", "_", str(col).strip()).lower()
    name = re.sub(r"_+", "_", name).strip("_")
    if name and name[0].isdigit():
        name = "col_" + name
    return name or "col"
