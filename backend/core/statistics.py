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