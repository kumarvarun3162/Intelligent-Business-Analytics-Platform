import json
import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional

from models.schemas import ChartConfig, DashboardConfig


# ── Plotly theme constants ────────────────────────────────────────
# Dark-mode first palette — these render well on both dark and light
COLORS = [
    "#5DCAA5", "#7F77DD", "#D85A30", "#378ADD",
    "#EF9F27", "#D4537E", "#639922", "#E24B4A",
]
HEATMAP_COLORSCALE = [
    [0.0,  "#3C3489"],   # dark purple — strong negative
    [0.25, "#AFA9EC"],   # light purple
    [0.5,  "#F1EFE8"],   # near-white neutral
    [0.75, "#9FE1CB"],   # light teal
    [1.0,  "#085041"],   # dark teal — strong positive
]

BASE_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor":  "rgba(0,0,0,0)",
    "font":          {"family": "Inter, sans-serif", "size": 12, "color": "#9ca3af"},
    "margin":        {"l": 50, "r": 20, "t": 50, "b": 50},
    "showlegend":    False,
    "xaxis": {
        "gridcolor":    "rgba(255,255,255,0.06)",
        "linecolor":    "rgba(255,255,255,0.1)",
        "zerolinecolor":"rgba(255,255,255,0.1)",
    },
    "yaxis": {
        "gridcolor":    "rgba(255,255,255,0.06)",
        "linecolor":    "rgba(255,255,255,0.1)",
        "zerolinecolor":"rgba(255,255,255,0.1)",
    },
}


def _base_layout(title: str, extra: Dict = None) -> Dict:
    """Merge BASE_LAYOUT with a title and any chart-specific overrides."""
    layout = {**BASE_LAYOUT, "title": {"text": title, "font": {"size": 14, "color": "#e5e7eb"}}}
    if extra:
        for k, v in extra.items():
            if isinstance(v, dict) and k in layout:
                layout[k] = {**layout[k], **v}
            else:
                layout[k] = v
    return layout


def _safe_values(series: pd.Series) -> list:
    """Convert a pandas Series to a JSON-safe Python list."""
    result = []
    for v in series:
        if isinstance(v, (np.integer,)):
            result.append(int(v))
        elif isinstance(v, (np.floating,)):
            result.append(None if np.isnan(v) else float(v))
        elif pd.isna(v):
            result.append(None)
        else:
            result.append(v)
    return result


# ══════════════════════════════════════════════════════════════════
# HISTOGRAM — numeric distribution
# ══════════════════════════════════════════════════════════════════

def make_histogram(
    df: pd.DataFrame,
    col: str,
    priority: int = 5,
) -> ChartConfig:
    """
    Distribution histogram for one numeric column.

    Uses Plotly's autobinning — it picks the optimal bin count
    using the Sturges/Scott formula based on data size.

    The overlay of a KDE (kernel density estimate) curve would
    require scipy — we skip it here to keep the response payload
    small and add it as an enhancement later.
    """
    series  = df[col].dropna()
    skew    = float(series.skew())
    mean_v  = float(series.mean())
    median_v = float(series.median())

    trace = {
        "type":    "histogram",
        "x":       _safe_values(series),
        "name":    col,
        "marker":  {"color": COLORS[0], "opacity": 0.8},
        "nbinsx":  min(50, max(10, int(len(series) ** 0.5))),
        "hovertemplate": f"{col}: %{{x}}<br>Count: %{{y}}<extra></extra>",
    }

    # Vertical lines for mean and median
    shapes = [
        {"type": "line", "x0": mean_v,   "x1": mean_v,
         "y0": 0, "y1": 1, "yref": "paper",
         "line": {"color": "#EF9F27", "width": 1.5, "dash": "dot"}},
        {"type": "line", "x0": median_v, "x1": median_v,
         "y0": 0, "y1": 1, "yref": "paper",
         "line": {"color": "#5DCAA5", "width": 1.5, "dash": "dash"}},
    ]
    annotations = [
        {"x": mean_v,   "y": 1, "yref": "paper", "text": "mean",
         "showarrow": False, "font": {"size": 10, "color": "#EF9F27"},
         "xanchor": "left", "yanchor": "bottom"},
        {"x": median_v, "y": 0.9, "yref": "paper", "text": "median",
         "showarrow": False, "font": {"size": 10, "color": "#5DCAA5"},
         "xanchor": "left", "yanchor": "bottom"},
    ]

    layout = _base_layout(
        f"Distribution of {col}",
        {"shapes": shapes, "annotations": annotations,
         "xaxis": {"title": col}, "yaxis": {"title": "count"}},
    )

    skew_label = (
        f"Right-skewed (skew={skew:.2f}) — consider log transform"
        if skew > 1 else
        f"Left-skewed (skew={skew:.2f})"
        if skew < -1 else
        f"Approximately symmetric (skew={skew:.2f})"
    )

    return ChartConfig(
        chart_id     = f"hist_{col}",
        title        = f"Distribution — {col}",
        chart_type   = "histogram",
        columns      = [col],
        plotly_data  = [trace],
        plotly_layout = layout,
        insight      = skew_label,
        priority     = priority,
    )


# ══════════════════════════════════════════════════════════════════
# BOX PLOT — spread and outliers
# ══════════════════════════════════════════════════════════════════

def make_box_plot(
    df: pd.DataFrame,
    numeric_cols: List[str],
    group_col: Optional[str] = None,
    priority: int = 4,
) -> ChartConfig:
    """
    Box plot for multiple numeric columns side by side,
    optionally grouped by a categorical column.

    Box plot anatomy (in case the user asks):
    - Centre line = median
    - Box edges   = Q1 (25th) and Q3 (75th) percentile
    - Whiskers    = 1.5 × IQR beyond Q1/Q3
    - Points      = outliers beyond whiskers
    """
    traces = []

    if group_col and group_col in df.columns:
        # One trace per category group, for the first numeric col
        col  = numeric_cols[0]
        groups = df[group_col].dropna().unique()
        for i, grp in enumerate(groups):
            subset = df.loc[df[group_col] == grp, col].dropna()
            traces.append({
                "type":    "box",
                "y":       _safe_values(subset),
                "name":    str(grp),
                "marker":  {"color": COLORS[i % len(COLORS)]},
                "boxmean": True,
                "hovertemplate": f"{grp}<br>%{{y}}<extra></extra>",
            })
        title_str = f"{col} by {group_col}"
        insight   = f"Comparing '{col}' distribution across '{group_col}' groups"
        cols_used = [col, group_col]
    else:
        # Side-by-side boxes for all numeric columns
        for i, col in enumerate(numeric_cols[:8]):  # cap at 8
            series = df[col].dropna()
            traces.append({
                "type":    "box",
                "y":       _safe_values(series),
                "name":    col,
                "marker":  {"color": COLORS[i % len(COLORS)]},
                "boxmean": True,
                "hovertemplate": f"{col}<br>%{{y}}<extra></extra>",
            })
        title_str = "Spread overview — all numeric columns"
        insight   = "Compare spread and outliers across all numeric features at a glance"
        cols_used = numeric_cols[:8]

    layout = _base_layout(
        title_str,
        {"showlegend": len(traces) > 1,
         "yaxis": {"title": "value"}},
    )

    return ChartConfig(
        chart_id      = f"box_{'_'.join(numeric_cols[:2])}",
        title         = title_str,
        chart_type    = "box",
        columns       = cols_used,
        plotly_data   = traces,
        plotly_layout = layout,
        insight       = insight,
        priority      = priority,
    )


# ══════════════════════════════════════════════════════════════════
# BAR CHART — categorical frequency
# ══════════════════════════════════════════════════════════════════

def make_bar_chart(
    df: pd.DataFrame,
    col: str,
    top_n: int = 15,
    priority: int = 5,
) -> ChartConfig:
    """
    Horizontal bar chart showing top-N value frequencies.

    Horizontal orientation is better for categorical data because:
    1. Category labels are readable without rotation
    2. Long category names don't overlap
    3. Human eyes scan frequency bars left-to-right naturally

    Sorted descending so the most frequent category is always on top.
    """
    vc     = df[col].value_counts().head(top_n)
    labels = [str(v) for v in vc.index]
    values = list(vc.values)

    # Color gradient: most frequent = most saturated
    max_v  = max(values) if values else 1
    opacities = [0.4 + 0.6 * (v / max_v) for v in values]
    colors = [f"rgba(93,202,165,{round(op, 2)})" for op in opacities]

    trace = {
        "type":        "bar",
        "x":           values,
        "y":           labels,
        "orientation": "h",
        "marker":      {"color": colors},
        "hovertemplate": "%{y}: %{x} rows<extra></extra>",
    }

    top_val   = labels[0] if labels else "?"
    top_pct   = round(values[0] / len(df) * 100, 1) if values else 0
    n_unique  = df[col].nunique()

    layout = _base_layout(
        f"Top values — {col}",
        {"xaxis": {"title": "count"},
         "yaxis": {"automargin": True},
         "margin": {"l": 140, "r": 20, "t": 50, "b": 40}},
    )

    return ChartConfig(
        chart_id      = f"bar_{col}",
        title         = f"Top values — {col}",
        chart_type    = "bar",
        columns       = [col],
        plotly_data   = [trace],
        plotly_layout = layout,
        insight       = f"'{top_val}' is most frequent ({top_pct}% of rows). {n_unique} unique values total.",
        priority      = priority,
    )