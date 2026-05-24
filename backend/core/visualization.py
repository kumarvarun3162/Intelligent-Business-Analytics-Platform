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

# ══════════════════════════════════════════════════════════════════
# SCATTER PLOT — relationship between two numeric columns
# ══════════════════════════════════════════════════════════════════

def make_scatter(
    df: pd.DataFrame,
    col_x: str,
    col_y: str,
    color_col: Optional[str] = None,
    priority: int = 4,
) -> ChartConfig:
    """
    Scatter plot for two numeric columns.
    Optionally colour-codes points by a categorical column.

    For large datasets (>5000 rows) we sample to keep the JSON
    payload manageable without losing the distributional shape.
    """
    MAX_POINTS = 2000
    subset = df[[col_x, col_y] + ([color_col] if color_col else [])].dropna()

    if len(subset) > MAX_POINTS:
        subset = subset.sample(MAX_POINTS, random_state=42)

    traces = []
    if color_col and color_col in subset.columns:
        for i, grp in enumerate(subset[color_col].unique()):
            mask = subset[color_col] == grp
            traces.append({
                "type":   "scatter",
                "mode":   "markers",
                "x":      _safe_values(subset.loc[mask, col_x]),
                "y":      _safe_values(subset.loc[mask, col_y]),
                "name":   str(grp),
                "marker": {"color": COLORS[i % len(COLORS)],
                           "size": 5, "opacity": 0.7},
                "hovertemplate": f"{col_x}: %{{x}}<br>{col_y}: %{{y}}<extra>{grp}</extra>",
            })
        show_legend = True
    else:
        # Compute Pearson r for the insight line
        corr = subset[[col_x, col_y]].corr().iloc[0, 1]
        traces.append({
            "type":   "scatter",
            "mode":   "markers",
            "x":      _safe_values(subset[col_x]),
            "y":      _safe_values(subset[col_y]),
            "name":   f"{col_x} vs {col_y}",
            "marker": {"color": COLORS[0], "size": 5, "opacity": 0.6},
            "hovertemplate": f"{col_x}: %{{x}}<br>{col_y}: %{{y}}<extra></extra>",
        })
        show_legend = False

    corr_val = subset[[col_x, col_y]].corr().iloc[0, 1]
    strength = (
        "strong" if abs(corr_val) >= 0.7 else
        "moderate" if abs(corr_val) >= 0.4 else
        "weak"
    )
    direction = "positive" if corr_val > 0 else "negative"

    layout = _base_layout(
        f"{col_x} vs {col_y}",
        {"showlegend": show_legend,
         "xaxis": {"title": col_x},
         "yaxis": {"title": col_y}},
    )

    return ChartConfig(
        chart_id      = f"scatter_{col_x}_{col_y}",
        title         = f"{col_x} vs {col_y}",
        chart_type    = "scatter",
        columns       = [col_x, col_y] + ([color_col] if color_col else []),
        plotly_data   = traces,
        plotly_layout = layout,
        insight       = f"{strength.capitalize()} {direction} correlation (r={corr_val:.3f})",
        priority      = priority,
    )


# ══════════════════════════════════════════════════════════════════
# LINE CHART — time series
# ══════════════════════════════════════════════════════════════════

def make_line_chart(
    df: pd.DataFrame,
    time_col: str,
    value_cols: List[str],
    priority: int = 2,
) -> ChartConfig:
    """
    Line chart for time-series data.

    We sort by the time column before plotting — unsorted time data
    produces jagged zig-zag lines that look like noise.

    Multiple value columns become multiple traces with shared x-axis.
    """
    sorted_df = df[[time_col] + value_cols].dropna(subset=[time_col])
    sorted_df = sorted_df.sort_values(time_col)

    # Sample if too large (keep every Nth row)
    MAX_POINTS = 1000
    if len(sorted_df) > MAX_POINTS:
        step = len(sorted_df) // MAX_POINTS
        sorted_df = sorted_df.iloc[::step]

    traces = []
    for i, col in enumerate(value_cols[:5]):
        traces.append({
            "type":   "scatter",
            "mode":   "lines",
            "x":      [str(v) for v in sorted_df[time_col]],
            "y":      _safe_values(sorted_df[col]),
            "name":   col,
            "line":   {"color": COLORS[i % len(COLORS)], "width": 2},
            "hovertemplate": f"%{{x}}<br>{col}: %{{y}}<extra></extra>",
        })

    title_str = f"Time series — {', '.join(value_cols[:3])}"
    layout = _base_layout(
        title_str,
        {"showlegend": len(traces) > 1,
         "xaxis": {"title": time_col, "type": "date"},
         "yaxis": {"title": "value"}},
    )

    return ChartConfig(
        chart_id      = f"line_{time_col}",
        title         = title_str,
        chart_type    = "line",
        columns       = [time_col] + value_cols,
        plotly_data   = traces,
        plotly_layout = layout,
        insight       = f"Trends over time for {len(value_cols)} numeric variable(s)",
        priority      = priority,
    )


# ══════════════════════════════════════════════════════════════════
# CORRELATION HEATMAP
# ══════════════════════════════════════════════════════════════════

def make_correlation_heatmap(
    df: pd.DataFrame,
    correlations: List,          # List[CorrelationPair] from Phase 4
    priority: int = 1,
) -> Optional[ChartConfig]:
    """
    Full correlation matrix as an annotated heatmap.

    This is the most information-dense chart in the dashboard —
    it shows ALL pairwise correlations in one view.

    We use Pearson r values. The matrix is symmetric (r(A,B) = r(B,A))
    so we only need to compute it once and mirror it.

    Annotations: each cell shows the r value, coloured for readability.
    Strong correlations (|r| > 0.7) get bold text in the annotation.
    """
    numeric_df = df.select_dtypes(include=[np.number])
    if len(numeric_df.columns) < 2:
        return None

    # Cap at 15 columns — beyond that the heatmap becomes unreadable
    cols = numeric_df.columns[:15].tolist()
    corr_matrix = numeric_df[cols].corr(method="pearson")

    # Round for display
    z_values = corr_matrix.round(2).values.tolist()

    # Annotation text for each cell
    annotations = []
    for i, row_col in enumerate(cols):
        for j, col_col in enumerate(cols):
            val = corr_matrix.iloc[i, j]
            annotations.append({
                "x":        col_col,
                "y":        row_col,
                "text":     f"{val:.2f}",
                "font":     {"size": 9,
                             "color": "white" if abs(val) > 0.5 else "#9ca3af"},
                "showarrow": False,
            })

    trace = {
        "type":        "heatmap",
        "z":           z_values,
        "x":           cols,
        "y":           cols,
        "colorscale":  HEATMAP_COLORSCALE,
        "zmid":        0,
        "zmin":        -1,
        "zmax":        1,
        "colorbar": {
            "title":     "r",
            "thickness": 12,
            "len":       0.8,
            "tickvals":  [-1, -0.5, 0, 0.5, 1],
            "tickfont":  {"size": 10, "color": "#9ca3af"},
        },
        "hovertemplate": "%{y} × %{x}<br>r = %{z:.3f}<extra></extra>",
    }

    # Find the strongest off-diagonal correlation
    max_pair = ("", "", 0.0)
    for cp in correlations:
        if abs(cp.pearson) > abs(max_pair[2]):
            max_pair = (cp.col_a, cp.col_b, cp.pearson)

    layout = _base_layout(
        "Correlation heatmap",
        {"annotations": annotations,
         "height": max(350, len(cols) * 35),
         "xaxis": {"side": "bottom", "tickangle": -35, "automargin": True},
         "yaxis": {"automargin": True}},
    )

    insight = (
        f"Strongest correlation: '{max_pair[0]}' ↔ '{max_pair[1]}' "
        f"(r={max_pair[2]:.2f})"
        if max_pair[0] else
        "No strong correlations detected in this dataset."
    )

    return ChartConfig(
        chart_id      = "heatmap_correlation",
        title         = "Correlation heatmap",
        chart_type    = "heatmap",
        columns       = cols,
        plotly_data   = [trace],
        plotly_layout = layout,
        insight       = insight,
        priority      = priority,
    )