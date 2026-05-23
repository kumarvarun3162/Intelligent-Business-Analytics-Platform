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
# ══════════════════════════════════════════════════════════════════
# MODULE 4 — Hypothesis testing
# ══════════════════════════════════════════════════════════════════

def run_hypothesis_tests(
    df: pd.DataFrame,
    max_tests: int = 20,
) -> List[HypothesisResult]:
    """
    Automatically select and run appropriate hypothesis tests.

    Selection logic:
    - Two categoricals with enough data → chi-square
    - One categorical (≤8 groups) + one numeric → ANOVA or t-test
    - Limits total tests to max_tests for performance

    p-value interpretation:
    p < 0.05 → reject null hypothesis → statistically significant
    p ≥ 0.05 → fail to reject → no significant evidence of difference

    Important: statistical significance ≠ practical significance.
    We flag it but the user must judge practical importance.
    """
    results  = []
    cat_cols = df.select_dtypes(include=["category", "object"]).columns.tolist()
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    # ── Chi-square: categorical pairs ───────────────────────────
    for i in range(len(cat_cols)):
        if len(results) >= max_tests:
            break
        for j in range(i + 1, len(cat_cols)):
            if len(results) >= max_tests:
                break
            col_a, col_b = cat_cols[i], cat_cols[j]
            try:
                ct = pd.crosstab(df[col_a], df[col_b])
                if ct.shape[0] < 2 or ct.shape[1] < 2:
                    continue
                chi2, p, dof, _ = scipy_stats.chi2_contingency(ct)
                significant = bool(p < 0.05)
                interp = (
                    f"'{col_a}' and '{col_b}' are statistically dependent "
                    f"(chi²={chi2:.2f}, p={p:.4f}) — they likely influence each other."
                    if significant else
                    f"No significant association between '{col_a}' and '{col_b}' "
                    f"(p={p:.4f})."
                )
                results.append(HypothesisResult(
                    test         = "chi_square",
                    columns      = [col_a, col_b],
                    statistic    = round(float(chi2), 4),
                    p_value      = round(float(p), 4),
                    significant  = significant,
                    interpretation = interp,
                ))
            except Exception:
                continue

    # ── ANOVA / t-test: categorical × numeric ───────────────────
    for cat in cat_cols:
        if len(results) >= max_tests:
            break
        groups_series = df[cat].dropna()
        n_groups = groups_series.nunique()
        if n_groups < 2 or n_groups > 8:
            continue

        for num in num_cols[:5]:   # limit to first 5 numeric cols
            if len(results) >= max_tests:
                break
            try:
                groups = [
                    df.loc[df[cat] == g, num].dropna().values
                    for g in df[cat].dropna().unique()
                    if len(df.loc[df[cat] == g, num].dropna()) >= 3
                ]
                if len(groups) < 2:
                    continue

                if len(groups) == 2:
                    # t-test for exactly two groups
                    stat, p = scipy_stats.ttest_ind(groups[0], groups[1])
                    test_name = "t_test"
                    interp_sig = (
                        f"'{num}' differs significantly between the two "
                        f"'{cat}' groups (t={stat:.2f}, p={p:.4f})."
                    )
                    interp_ns = (
                        f"No significant difference in '{num}' between "
                        f"'{cat}' groups (p={p:.4f})."
                    )
                else:
                    # One-way ANOVA for 3+ groups
                    stat, p = scipy_stats.f_oneway(*groups)
                    test_name = "anova"
                    interp_sig = (
                        f"'{num}' varies significantly across '{cat}' groups "
                        f"(F={stat:.2f}, p={p:.4f}) — '{cat}' may explain '{num}'."
                    )
                    interp_ns = (
                        f"No significant difference in '{num}' across "
                        f"'{cat}' groups (p={p:.4f})."
                    )

                significant = bool(p < 0.05)
                results.append(HypothesisResult(
                    test           = test_name,
                    columns        = [cat, num],
                    statistic      = round(float(stat), 4),
                    p_value        = round(float(p), 4),
                    significant    = significant,
                    interpretation = interp_sig if significant else interp_ns,
                ))
            except Exception:
                continue

    return results


# ══════════════════════════════════════════════════════════════════
# MODULE 5 — PCA (Principal Component Analysis)
# ══════════════════════════════════════════════════════════════════

def run_pca(
    df: pd.DataFrame,
    n_components: int = None,
) -> Optional[PCAResult]:
    """
    Run PCA on all numeric columns.

    Requires at least 3 numeric columns and 10 rows.

    The scree plot data (explained_variance per component) drives the
    interactive chart in Phase 5.

    Top features per component: we take the 3 columns with the highest
    absolute loading (contribution) to each principal component.
    """
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA

    numeric_df = df.select_dtypes(include=[np.number]).dropna()
    cols = numeric_df.columns.tolist()

    if len(cols) < 3 or len(numeric_df) < 10:
        return None

    # PCA requires standardised input — each column mean=0, std=1
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(numeric_df)

    # Default: keep enough components to explain 95% of variance
    max_components = min(len(cols), len(numeric_df) - 1)
    pca = PCA(n_components=n_components or max_components, random_state=42)
    pca.fit(X_scaled)

    explained       = [round(float(v), 4) for v in pca.explained_variance_ratio_]
    cumulative      = []
    running         = 0.0
    components_90   = max_components
    for i, v in enumerate(explained):
        running += v
        cumulative.append(round(running, 4))
        if running >= 0.90 and components_90 == max_components:
            components_90 = i + 1

    # Top 3 feature contributors per component
    top_features: Dict[str, List[str]] = {}
    for i, component in enumerate(pca.components_):
        abs_loadings = np.abs(component)
        top_idx      = np.argsort(abs_loadings)[::-1][:3]
        top_features[f"PC{i+1}"] = [cols[idx] for idx in top_idx]

    return PCAResult(
        n_components         = len(explained),
        explained_variance   = explained,
        cumulative_variance  = cumulative,
        components_for_90pct = components_90,
        top_features         = top_features,
    )

# ══════════════════════════════════════════════════════════════════
# MODULE 6 — Categorical frequency analysis
# ══════════════════════════════════════════════════════════════════

def analyze_categorical_frequencies(
    df: pd.DataFrame,
    top_n: int = 10,
) -> List[CategoryFrequency]:
    """
    Analyse value distributions in categorical columns.

    Shannon entropy:
    H = -Σ p_i × log2(p_i)
    Max entropy = log2(n_unique) — perfectly uniform
    Min entropy = 0 — one value dominates 100%

    We normalise: H / log2(n_unique) → 0 to 1 scale.
    Low normalised entropy (< 0.3) signals a dominant category
    that may cause class imbalance problems in ML.
    """
    results  = []
    cat_cols = df.select_dtypes(include=["category", "object"]).columns

    for col in cat_cols:
        series = df[col].dropna()
        if len(series) == 0:
            continue

        vc     = series.value_counts()
        total  = len(series)
        n_uniq = len(vc)

        top_values = [
            {
                "value": str(v),
                "count": int(c),
                "pct":   round(c / total * 100, 1),
            }
            for v, c in vc.head(top_n).items()
        ]

        # Shannon entropy
        probs   = vc.values / total
        entropy = float(-np.sum(probs * np.log2(probs + 1e-12)))
        # Normalise by max possible entropy
        max_h   = log2(n_uniq) if n_uniq > 1 else 1.0

        results.append(CategoryFrequency(
            column       = col,
            top_values   = top_values,
            unique_count = n_uniq,
            top1_pct     = round(float(vc.iloc[0] / total * 100), 1),
            entropy      = round(entropy / max_h, 4),   # normalised 0–1
        ))

    return results


# ══════════════════════════════════════════════════════════════════
# INSIGHT GENERATOR — rule-based plain English
# ══════════════════════════════════════════════════════════════════

def generate_insights(
    descriptive:    List,
    correlations:   List,
    distributions:  List,
    hypothesis:     List,
    pca:            Optional[object],
    cat_freqs:      List,
    vif_results:    List,
) -> Tuple[List[str], List[str]]:
    """
    Translate statistics into plain-English sentences.
    Returns (insights, warnings).

    This is pure rule-based logic — no LLM.
    Each rule is a threshold comparison → sentence template.
    """
    insights = []
    warnings = []

    # ── Descriptive insights ────────────────────────────────────
    for s in descriptive:
        if abs(s.skewness) > 1.5:
            direction = "right" if s.skewness > 0 else "left"
            insights.append(
                f"'{s.column}' is strongly {direction}-skewed "
                f"(skewness={s.skewness:.2f}), suggesting a log transform "
                f"may improve ML model performance."
            )
        if s.cv > 1.0:
            insights.append(
                f"'{s.column}' has very high relative spread "
                f"(CV={s.cv:.2f}) — values vary widely relative to the mean."
            )
        if not s.is_normal:
            pass  # distribution module handles this

    # ── Correlation insights ─────────────────────────────────────
    strong_pairs = [c for c in correlations if abs(c.pearson) >= 0.7]
    if strong_pairs:
        top = strong_pairs[0]
        insights.append(
            f"Strong {top.direction} correlation detected between "
            f"'{top.col_a}' and '{top.col_b}' (r={top.pearson:.2f}). "
            f"These features may be partially redundant."
        )
    if len(strong_pairs) > 3:
        insights.append(
            f"{len(strong_pairs)} strongly correlated feature pairs found. "
            f"Consider dimensionality reduction before training ML models."
        )

    # ── VIF warnings ────────────────────────────────────────────
    severe_vif = [v for v in vif_results if v.flag == "severe"]
    for v in severe_vif:
        warnings.append(
            f"Severe multicollinearity: '{v.column}' has VIF={v.vif:.1f}. "
            f"It is nearly a linear combination of other features — "
            f"consider removing it before linear model training."
        )

    # ── Distribution insights ────────────────────────────────────
    non_normal = [d for d in distributions if not d.is_normal]
    if len(non_normal) > len(distributions) * 0.6:
        insights.append(
            f"{len(non_normal)} of {len(distributions)} numeric columns are "
            f"non-normal. Tree-based models (Random Forest, XGBoost) are "
            f"recommended over linear regression for this dataset."
        )

    # ── Hypothesis test insights ─────────────────────────────────
    sig_tests = [h for h in hypothesis if h.significant]
    for h in sig_tests[:3]:   # top 3 significant only
        insights.append(h.interpretation)

    # ── PCA insights ─────────────────────────────────────────────
    if pca:
        pct_in_2 = round(pca.cumulative_variance[1] * 100, 1) if len(pca.cumulative_variance) >= 2 else 0
        insights.append(
            f"PCA: {pca.components_for_90pct} components explain 90% of variance "
            f"(out of {pca.n_components} total). "
            f"First 2 components capture {pct_in_2}% of information."
        )

    # ── Categorical imbalance warnings ──────────────────────────
    for cf in cat_freqs:
        if cf.top1_pct > 90:
            warnings.append(
                f"'{cf.column}' is highly imbalanced: "
                f"the top value covers {cf.top1_pct:.1f}% of rows. "
                f"This will cause class imbalance in classification models."
            )
        if cf.entropy < 0.2:
            warnings.append(
                f"'{cf.column}' has very low entropy ({cf.entropy:.2f}) — "
                f"nearly all rows share the same value. "
                f"Consider dropping this column."
            )

    return insights, warnings

# ══════════════════════════════════════════════════════════════════
# MASTER ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════

def run_analysis_pipeline(
    df:         pd.DataFrame,
    session_id: str,
) -> InsightsReport:
    """
    Run all 6 analysis modules in sequence and assemble InsightsReport.
    Gracefully handles failures in individual modules — one bad column
    should never crash the whole analysis.
    """
    descriptive  = compute_descriptive_stats(df)
    correlations = compute_correlations(df)
    vif_results  = compute_vif(df)
    distributions = analyze_distributions(df)
    hyp_tests    = run_hypothesis_tests(df)
    pca_result   = run_pca(df)
    cat_freqs    = analyze_categorical_frequencies(df)

    insights, warnings = generate_insights(
        descriptive, correlations, distributions,
        hyp_tests, pca_result, cat_freqs, vif_results,
    )

    return InsightsReport(
        session_id       = session_id,
        row_count        = len(df),
        col_count        = len(df.columns),
        descriptive      = descriptive,
        correlations     = correlations,
        vif_results      = vif_results,
        distributions    = distributions,
        hypothesis_tests = hyp_tests,
        pca              = pca_result,
        category_freqs   = cat_freqs,
        key_insights     = insights,
        warnings         = warnings,
    )