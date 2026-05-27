# backend/core/report_builder.py

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from models.schemas import DataPassport, ReportConfig, NarrativeSection


def build_data_passport(
    session_id:          str,
    dataset_name:        str,
    cleaning_report,
    engineering_report,
    insights_report,
) -> DataPassport:
    """
    Assemble the complete pipeline audit trail into a DataPassport.

    Column lineage: tracks what happened to each original column.
    Pipeline stages: ordered summary of every phase that ran.
    """
    pipeline_stages = []
    column_lineage: Dict[str, str] = {}
    total_transforms = 0
    cleaning_actions = 0
    new_features     = 0

    # ── Stage: Upload ────────────────────────────────────────────
    pipeline_stages.append({
        "phase":   1,
        "name":    "File ingestion",
        "status":  "completed",
        "summary": f"Uploaded '{dataset_name}'",
    })

    # ── Stage: Cleaning ──────────────────────────────────────────
    if cleaning_report:
        cleaning_actions = len(cleaning_report.actions)
        pipeline_stages.append({
            "phase":    2,
            "name":     "Data cleaning",
            "status":   "completed",
            "summary":  (
                f"Removed {cleaning_report.rows_removed} rows, "
                f"filled {cleaning_report.total_nulls_before - cleaning_report.total_nulls_after} nulls, "
                f"handled {cleaning_report.outliers_detected} outliers"
            ),
            "quality_score": cleaning_report.quality_score,
            "quality_grade": cleaning_report.quality_grade,
            "actions_taken": cleaning_actions,
        })

    # ── Stage: Engineering ───────────────────────────────────────
    if engineering_report:
        new_features     = engineering_report.new_cols_created
        total_transforms = len(engineering_report.transforms)

        pipeline_stages.append({
            "phase":      3,
            "name":       "Feature engineering",
            "status":     "completed",
            "summary":    (
                f"Applied {total_transforms} transforms, "
                f"created {new_features} new features, "
                f"ML-ready: {engineering_report.ml_ready}"
            ),
            "transforms": [
                {"column": t.column, "transform": t.transform, "note": t.note}
                for t in engineering_report.transforms[:20]  # cap for size
            ],
        })

        # Build column lineage from transform records
        for transform in engineering_report.transforms:
            for new_col in transform.new_columns:
                column_lineage[new_col] = (
                    f"Derived from '{transform.column}' via {transform.transform}"
                )

    # ── Stage: Analysis ──────────────────────────────────────────
    if insights_report:
        pipeline_stages.append({
            "phase":    4,
            "name":     "Statistical analysis",
            "status":   "completed",
            "summary":  (
                f"Analysed {len(insights_report.descriptive)} numeric columns, "
                f"found {len(insights_report.correlations)} significant correlations"
            ),
            "top_insights": insights_report.key_insights[:3],
            "warnings":     insights_report.warnings[:3],
        })

    return DataPassport(
        session_id       = session_id,
        original_file    = dataset_name,
        generated_at     = datetime.utcnow().isoformat(),
        pipeline_stages  = pipeline_stages,
        column_lineage   = column_lineage,
        quality_score    = cleaning_report.quality_score if cleaning_report else None,
        quality_grade    = cleaning_report.quality_grade if cleaning_report else None,
        ml_ready         = engineering_report.ml_ready if engineering_report else False,
        total_transforms = total_transforms,
        cleaning_actions = cleaning_actions,
        new_features     = new_features,
    )


def assemble_report(
    session_id:          str,
    dataset_name:        str,
    narrative:           list,
    data_passport:       DataPassport,
    base_url:            str = "http://localhost:8080",
) -> ReportConfig:
    """
    Combine narrative + passport into the final ReportConfig.
    Download URLs point to the /api/download endpoints we'll create next.
    """
    import os
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    return ReportConfig(
        session_id    = session_id,
        dataset_name  = dataset_name,
        generated_at  = datetime.utcnow().isoformat(),
        narrative     = narrative,
        data_passport = data_passport,
        download_urls = {
            "csv":      f"{base_url}/api/download/{session_id}/csv",
            "passport": f"{base_url}/api/download/{session_id}/passport",
            "pdf":      f"{base_url}/api/download/{session_id}/pdf",
        },
        model_used    = model,
    )