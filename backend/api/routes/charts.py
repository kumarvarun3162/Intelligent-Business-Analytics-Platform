# backend/api/routes/charts.py

import json
import pandas as pd
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.visualization import build_dashboard
from models.schemas import DashboardResponse
from storage.database import get_connection

router = APIRouter(prefix="/api", tags=["visualization"])


class ChartsRequest(BaseModel):
    session_id: str


@router.post(
    "/charts",
    response_model=DashboardResponse,
    summary="Generate interactive dashboard config for a session",
)
async def generate_charts(req: ChartsRequest):
    """
    Loads the engineered (or cleaned) data + analysis report,
    builds all chart configs, and returns the full dashboard JSON.
    """
    conn = get_connection()
    cur  = conn.cursor()

    # Load all available reports for this session
    cur.execute(
        "SELECT engineered_path FROM engineering_reports WHERE session_id = ?",
        (req.session_id,)
    )
    eng_row = cur.fetchone()

    cur.execute(
        "SELECT cleaned_path, report_json FROM cleaning_reports WHERE session_id = ?",
        (req.session_id,)
    )
    clean_row = cur.fetchone()

    cur.execute(
        "SELECT report_json FROM analysis_reports WHERE session_id = ?",
        (req.session_id,)
    )
    analysis_row = cur.fetchone()

    cur.execute(
        "SELECT original_name FROM sessions WHERE session_id = ?",
        (req.session_id,)
    )
    session_row = cur.fetchone()
    conn.close()

    # Choose the best available file
    file_path = None
    if eng_row:
        p = Path(eng_row["engineered_path"])
        if p.exists():
            file_path = p
    if not file_path and clean_row:
        p = Path(clean_row["cleaned_path"])
        if p.exists():
            file_path = p

    if not file_path:
        raise HTTPException(
            status_code=404,
            detail="No processed data found. Run /api/clean first."
        )

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read file: {e}")

    # Parse reports
    cleaning_report  = None
    insights_report  = None
    type_map         = {}
    dataset_name     = req.session_id[:12]

    if clean_row:
        from models.schemas import CleaningReport
        cleaning_report = CleaningReport(
            **json.loads(clean_row["report_json"])
        )
        type_map = cleaning_report.column_type_map or {}

    if analysis_row:
        from models.schemas import InsightsReport
        insights_report = InsightsReport(
            **json.loads(analysis_row["report_json"])
        )

    if session_row:
        dataset_name = session_row["original_name"]

    # Build dashboard
    try:
        dashboard = build_dashboard(
            df             = df,
            session_id     = req.session_id,
            dataset_name   = dataset_name,
            insights_report = insights_report,
            cleaning_report = cleaning_report,
            type_map       = type_map,
        )
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Dashboard generation failed: {e}")

    # Persist dashboard
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dashboards (
            session_id     TEXT PRIMARY KEY,
            dashboard_json TEXT,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute(
        "INSERT OR REPLACE INTO dashboards (session_id, dashboard_json) VALUES (?, ?)",
        (req.session_id, dashboard.model_dump_json())
    )
    conn.commit()
    conn.close()

    return DashboardResponse(
        success   = True,
        message   = f"Dashboard ready: {len(dashboard.charts)} charts generated.",
        dashboard = dashboard,
    )


@router.get("/charts/{session_id}", summary="Retrieve stored dashboard config")
async def get_dashboard(session_id: str):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT dashboard_json FROM dashboards WHERE session_id = ?",
        (session_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No dashboard found.")
    return json.loads(row["dashboard_json"])