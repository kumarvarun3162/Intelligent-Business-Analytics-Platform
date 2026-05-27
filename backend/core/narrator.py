# backend/core/narrator.py

import os
import json
from typing import List, Optional
from groq import Groq

from models.schemas import NarrativeSection


# ── Groq client (lazy init — only created when needed) ───────────
_client: Optional[Groq] = None

def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not set. Add it to your .env file. "
                "Get a free key at console.groq.com"
            )
        _client = Groq(api_key=api_key)
    return _client


# ── Build compressed context (keeps tokens under limit) ──────────

def _build_context(
    insights_report,
    cleaning_report,
    engineering_report,
    dataset_name: str,
) -> str:
    """
    Build a compact, structured text summary of all pipeline reports.
    This is what we send to the LLM as context.

    Why compressed? The free Groq tier has ~6000 tokens/minute.
    A full InsightsReport can be 10,000+ tokens as JSON.
    We extract only the most useful parts for narration.
    """
    lines = [f"Dataset: {dataset_name}"]

    if cleaning_report:
        lines += [
            "\n## Data Quality",
            f"Quality score: {cleaning_report.quality_score}/100 (Grade {cleaning_report.quality_grade})",
            f"Rows: {cleaning_report.original_row_count} → {cleaning_report.cleaned_row_count} ({cleaning_report.rows_removed} removed)",
            f"Columns: {cleaning_report.original_col_count} → {cleaning_report.cleaned_col_count}",
            f"Nulls filled: {cleaning_report.total_nulls_before - cleaning_report.total_nulls_after}",
            f"Duplicates removed: {cleaning_report.duplicates_removed}",
            f"Outliers handled: {cleaning_report.outliers_detected}",
        ]

    if engineering_report:
        lines += [
            "\n## Feature Engineering",
            f"New features created: {engineering_report.new_cols_created}",
            f"ML-ready: {engineering_report.ml_ready}",
            f"Transforms applied: {len(engineering_report.transforms)}",
        ]
        # Top 5 transforms
        for t in engineering_report.transforms[:5]:
            lines.append(f"  - {t.transform} on '{t.column}': {t.note}")

    if insights_report:
        lines.append("\n## Statistical Insights")

        # Descriptive stats summary
        for s in insights_report.descriptive[:6]:
            lines.append(
                f"  {s.column}: mean={s.mean:.2f}, std={s.std:.2f}, "
                f"skew={s.skewness:.2f}, normal={s.is_normal}"
            )

        # Top correlations
        if insights_report.correlations:
            lines.append("\nTop correlations:")
            for c in insights_report.correlations[:5]:
                lines.append(
                    f"  {c.col_a} ↔ {c.col_b}: r={c.pearson:.3f} ({c.strength} {c.direction})"
                )

        # Significant hypothesis tests
        sig = [h for h in insights_report.hypothesis_tests if h.significant]
        if sig:
            lines.append("\nSignificant findings:")
            for h in sig[:4]:
                lines.append(f"  - {h.interpretation}")

        # PCA
        if insights_report.pca:
            lines.append(
                f"\nPCA: {insights_report.pca.components_for_90pct} components "
                f"explain 90% of variance"
            )

        # Existing rule-based insights
        if insights_report.key_insights:
            lines.append("\nAuto-detected insights:")
            for ins in insights_report.key_insights[:6]:
                lines.append(f"  - {ins}")

        # Warnings
        if insights_report.warnings:
            lines.append("\nWarnings:")
            for w in insights_report.warnings[:4]:
                lines.append(f"  - {w}")

        # Category frequencies
        for cf in insights_report.category_freqs[:3]:
            lines.append(
                f"\n'{cf.column}': {cf.unique_count} unique values, "
                f"top value covers {cf.top1_pct}%, entropy={cf.entropy:.2f}"
            )

    return "\n".join(lines)


# ── Section definitions ───────────────────────────────────────────

SECTIONS = [
    {
        "key":   "executive_summary",
        "title": "Executive summary",
        "emoji": "📋",
        "prompt": (
            "Write a 3–4 sentence executive summary of this dataset for a business audience. "
            "Mention the dataset size, overall data quality grade, and the single most "
            "important finding. Use plain English — no jargon, no bullet points, no markdown. "
            "Write as flowing prose."
        ),
        "max_tokens": 250,
    },
    {
        "key":   "data_quality",
        "title": "Data quality assessment",
        "emoji": "🧹",
        "prompt": (
            "Describe the data quality of this dataset in 3–4 sentences. "
            "Explain what issues were found (nulls, duplicates, outliers), "
            "what was done to fix them, and what the quality score means practically. "
            "Be specific about numbers. Write as flowing prose, no bullet points."
        ),
        "max_tokens": 280,
    },
    {
        "key":   "key_findings",
        "title": "Key findings",
        "emoji": "🔍",
        "prompt": (
            "Identify and explain the 3 most important analytical findings from this dataset. "
            "Focus on correlations, patterns, anomalies, or business-relevant insights. "
            "For each finding explain WHY it matters, not just what the number is. "
            "Write as flowing prose with natural paragraph breaks. No bullet points."
        ),
        "max_tokens": 400,
    },
    {
        "key":   "statistical_highlights",
        "title": "Statistical highlights",
        "emoji": "📊",
        "prompt": (
            "Summarise the most interesting statistical characteristics of the numeric columns. "
            "Mention distribution shapes (normal vs skewed), any surprising ranges or spreads, "
            "and what these characteristics imply for further analysis or model selection. "
            "Write as 3–4 sentences of flowing prose."
        ),
        "max_tokens": 280,
    },
    {
        "key":   "recommendations",
        "title": "Recommendations",
        "emoji": "💡",
        "prompt": (
            "Based on the data analysis, provide 3 specific, actionable recommendations. "
            "These could be: additional data to collect, features to investigate, "
            "ML models best suited to this data, business decisions suggested by the patterns, "
            "or data quality improvements. "
            "Write as flowing prose. Be concrete — reference actual column names and statistics."
        ),
        "max_tokens": 350,
    },
    {
        "key":   "ml_readiness",
        "title": "ML readiness",
        "emoji": "🤖",
        "prompt": (
            "Assess how ready this dataset is for machine learning. "
            "Mention: whether the data is fully numeric, whether class imbalance exists, "
            "which ML algorithm families are most appropriate given the distributions, "
            "and any remaining concerns before training. "
            "Write as 3–4 sentences of flowing prose."
        ),
        "max_tokens": 280,
    },
]


# ── Main narrator function ────────────────────────────────────────

def generate_narrative(
    insights_report,
    cleaning_report,
    engineering_report,
    dataset_name: str,
) -> List[NarrativeSection]:
    """
    Generate all narrative sections using the Groq LLM.

    Strategy: one API call per section with a focused prompt.
    This is more reliable than one large call asking for everything —
    if one section fails, the rest still succeed.

    Each call sends: system role + compressed context + section prompt.
    Total tokens per call ≈ 600 context + 100 prompt + 300 response = ~1000.
    6 sections = ~6000 tokens — fits in one minute on the free tier.
    """
    client  = _get_client()
    model   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    context = _build_context(
        insights_report, cleaning_report, engineering_report, dataset_name
    )

    system_prompt = (
        "You are a senior data scientist writing a professional business analytics report. "
        "You receive statistical analysis results and write clear, insightful narrative. "
        "Rules: write in flowing prose only — no bullet points, no markdown headers, "
        "no backticks, no asterisks. Be specific, cite actual numbers from the data. "
        "Write for a business audience that understands data but not statistics jargon."
    )

    sections: List[NarrativeSection] = []

    for sec in SECTIONS:
        try:
            user_message = (
                f"Here is the data analysis context:\n\n{context}\n\n"
                f"Task: {sec['prompt']}"
            )

            response = client.chat.completions.create(
                model      = model,
                messages   = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
                max_tokens  = sec["max_tokens"],
                temperature = 0.4,  # slightly creative but mostly factual
            )

            content = response.choices[0].message.content.strip()

            sections.append(NarrativeSection(
                section = sec["key"],
                title   = sec["title"],
                content = content,
                emoji   = sec["emoji"],
            ))

        except Exception as e:
            # Graceful fallback — don't fail the whole report for one section
            sections.append(NarrativeSection(
                section = sec["key"],
                title   = sec["title"],
                content = f"This section could not be generated: {str(e)}",
                emoji   = sec["emoji"],
            ))

    return sections