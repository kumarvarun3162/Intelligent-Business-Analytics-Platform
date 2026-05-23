# backend/core/statistics.py

import warnings
import numpy as np
import pandas as pd
from math import log2
from typing import List, Dict, Any, Optional, Tuple

from scipy import stats as scipy_stats

from models.schemas import (
    DescriptiveStats, CorrelationPair, VIFResult,
    DistributionInfo, HypothesisResult, PCAResult,
    CategoryFrequency, InsightsReport,
)

# Suppress scipy warnings for small samples
warnings.filterwarnings("ignore", category=RuntimeWarning)


# ══════════════════════════════════════════════════════════════════
# MODULE 1 — Descriptive statistics
# ══════════════════════════════════════════════════════════════════

def compute_descriptive_stats(
    df: pd.DataFrame,
) -> List[DescriptiveStats]:
    """
    Compute the full statistical portrait for every numeric column.

    Shapiro-Wilk test for normality:
    H0: the data is normally distributed.
    We reject H0 (flag is_normal=False) when p < 0.05.
    Limitation: Shapiro-Wilk is unreliable for n > 5000 — it will
    almost always reject normality for large samples even when the
    data is approximately normal. We handle this with a sample.
    """
    results = []
    numeric_cols = df.select_dtypes(include=[np.number]).columns

    for col in numeric_cols:
        series = df[col].dropna()
        n = len(series)
        if n < 3:
            continue

        q1  = float(series.quantile(0.25))
        q3  = float(series.quantile(0.75))
        iqr = q3 - q1
        mean = float(series.mean())
        std  = float(series.std())

        # Shapiro-Wilk on a sample (max 5000 points)
        sample  = series.sample(min(n, 5000), random_state=42)
        sw_stat, sw_p = scipy_stats.shapiro(sample)

        results.append(DescriptiveStats(
            column   = col,
            count    = n,
            mean     = round(mean, 6),
            median   = round(float(series.median()), 6),
            std      = round(std, 6),
            variance = round(float(series.var()), 6),
            min      = round(float(series.min()), 6),
            max      = round(float(series.max()), 6),
            range    = round(float(series.max() - series.min()), 6),
            q1       = round(q1, 6),
            q3       = round(q3, 6),
            iqr      = round(iqr, 6),
            skewness = round(float(series.skew()), 4),
            kurtosis = round(float(series.kurtosis()), 4),
            cv       = round(std / mean, 4) if mean != 0 else 0.0,
            is_normal = bool(sw_p > 0.05),
        ))

    return results

# ══════════════════════════════════════════════════════════════════
# MODULE 2 — Correlation analysis
# ══════════════════════════════════════════════════════════════════

def _correlation_strength(r: float) -> Tuple[str, str]:
    """Convert a correlation coefficient to human-readable labels."""
    abs_r = abs(r)
    strength = (
        "strong"     if abs_r >= 0.7 else
        "moderate"   if abs_r >= 0.4 else
        "weak"       if abs_r >= 0.2 else
        "negligible"
    )
    direction = (
        "positive" if r > 0.05 else
        "negative" if r < -0.05 else
        "none"
    )
    return strength, direction


def compute_correlations(
    df: pd.DataFrame,
    threshold: float = 0.2,
) -> List[CorrelationPair]:
    """
    Compute Pearson and Spearman correlation for all numeric column pairs.
    Only returns pairs where |pearson| >= threshold to keep output focused.

    We compute both because:
    - Pearson can miss non-linear relationships that Spearman catches
    - When they diverge significantly, it signals non-linearity or outliers
    """
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) < 2:
        return []

    results = []
    # Only upper triangle to avoid duplicates (col_a, col_b) and (col_b, col_a)
    for i in range(len(numeric_cols)):
        for j in range(i + 1, len(numeric_cols)):
            col_a = numeric_cols[i]
            col_b = numeric_cols[j]

            # Drop rows where either column is null
            pair = df[[col_a, col_b]].dropna()
            if len(pair) < 5:
                continue

            try:
                pearson_r,  _ = scipy_stats.pearsonr(pair[col_a], pair[col_b])
                spearman_r, _ = scipy_stats.spearmanr(pair[col_a], pair[col_b])
            except Exception:
                continue

            # Skip near-zero correlations
            if abs(pearson_r) < threshold and abs(spearman_r) < threshold:
                continue

            strength, direction = _correlation_strength(pearson_r)

            results.append(CorrelationPair(
                col_a     = col_a,
                col_b     = col_b,
                pearson   = round(float(pearson_r), 4),
                spearman  = round(float(spearman_r), 4),
                strength  = strength,
                direction = direction,
            ))

    # Sort by absolute Pearson descending — strongest first
    results.sort(key=lambda x: abs(x.pearson), reverse=True)
    return results


def compute_vif(df: pd.DataFrame) -> List[VIFResult]:
    """
    Compute Variance Inflation Factor for each numeric column.

    VIF for column X = 1 / (1 - R²) where R² is the coefficient
    of determination when X is regressed on all other numeric columns.

    Interpretation:
    VIF = 1   → no correlation with other columns
    VIF 1–5   → low multicollinearity (ok)
    VIF 5–10  → moderate (worth investigating)
    VIF > 10  → severe — this column is nearly redundant
    """
    from sklearn.linear_model import LinearRegression

    numeric_df = df.select_dtypes(include=[np.number]).dropna()
    cols = numeric_df.columns.tolist()

    if len(cols) < 2:
        return []

    results = []
    for col in cols:
        y = numeric_df[col].values
        X = numeric_df.drop(columns=[col]).values

        try:
            model = LinearRegression().fit(X, y)
            r2    = model.score(X, y)
            # Clamp r2 to [0, 0.9999] to avoid division by zero / infinity
            r2    = max(0.0, min(r2, 0.9999))
            vif   = 1.0 / (1.0 - r2)
        except Exception:
            vif = 1.0

        flag = (
            "severe"   if vif > 10 else
            "moderate" if vif > 5  else
            "ok"
        )
        results.append(VIFResult(
            column = col,
            vif    = round(vif, 2),
            flag   = flag,
        ))

    results.sort(key=lambda x: x.vif, reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════
# MODULE 3 — Distribution analysis
# ══════════════════════════════════════════════════════════════════

def analyze_distributions(
    df: pd.DataFrame,
) -> List[DistributionInfo]:
    """
    Characterise the distribution shape of each numeric column and
    recommend a transformation if appropriate.

    Transformation recommendations:
    - Right-skewed (skew > 1) + all positive values → log transform
    - Right-skewed + zeros present → sqrt transform (log(0) = undefined)
    - Left-skewed (skew < -1) → reflect + log (or Yeo-Johnson)
    - Non-normal but symmetric → Yeo-Johnson (handles neg values)
    - Normal → no transform needed

    Skewness interpretation:
    |skew| < 0.5  → approximately symmetric
    0.5–1.0       → moderately skewed
    > 1.0         → highly skewed
    """
    results = []
    numeric_cols = df.select_dtypes(include=[np.number]).columns

    for col in numeric_cols:
        series = df[col].dropna()
        n = len(series)
        if n < 5:
            continue

        skew = float(series.skew())
        kurt = float(series.kurtosis())  # excess kurtosis (normal=0)

        # Shapiro-Wilk (sample if large)
        sample = series.sample(min(n, 5000), random_state=42)
        try:
            sw_stat, sw_p = scipy_stats.shapiro(sample)
        except Exception:
            sw_stat, sw_p = 0.0, 0.0

        # Classify skew
        if skew > 0.5:
            skew_type = "right-skewed"
        elif skew < -0.5:
            skew_type = "left-skewed"
        else:
            skew_type = "symmetric"

        # Classify tails (excess kurtosis: normal=0, heavy>1, light<-1)
        if kurt > 1.0:
            tail_type = "heavy-tailed"
        elif kurt < -1.0:
            tail_type = "light-tailed"
        else:
            tail_type = "normal-tailed"

        # Recommend transform
        if sw_p > 0.05:
            transform = "none"
        elif skew > 1.0 and series.min() > 0:
            transform = "log"
        elif skew > 1.0 and series.min() >= 0:
            transform = "sqrt"
        elif skew < -1.0:
            transform = "yeo-johnson"
        else:
            transform = "yeo-johnson"

        results.append(DistributionInfo(
            column         = col,
            shapiro_stat   = round(float(sw_stat), 4),
            shapiro_p      = round(float(sw_p), 4),
            is_normal      = bool(sw_p > 0.05),
            skew_type      = skew_type,
            tail_type      = tail_type,
            recommended_transform = transform,
        ))

    return results