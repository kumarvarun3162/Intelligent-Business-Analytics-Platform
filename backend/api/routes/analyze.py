# backend/api/routes/analyze.py

import json
import pandas as pd
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.statistics import run_analysis_pipeline
from models.schemas import AnalysisResponse
from storage.database import get_connection

router = APIRouter(prefix="/api", tags=["analysis"])


class AnalyzeRequest(BaseModel):
    session_id:  str
    use_engineered: bool = True   # False = use cleaned data instead


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    summary="Run full statistical analysis on a processed dataset",
)
async def analyze_dataset(req: AnalyzeRequest):
    """
    Runs all 6 statistical modules on either the engineered
    or cleaned DataFrame for a session.

    Precedence: engineered → cleaned → raw (first available)
    """
    conn = get_connection()
    cur  = conn.cursor()

    # Try to get engineered path first
    file_path = None
    if req.use_engineered:
        cur.execute(
            "SELECT engineered_path FROM engineering_reports WHERE session_id = ?",
            (req.session_id,)
        )
        row = cur.fetchone()
        if row:
            file_path = Path(row["engineered_path"])

    # Fall back to cleaned
    if not file_path or not file_path.exists():
        cur.execute(
            "SELECT cleaned_path FROM cleaning_reports WHERE session_id = ?",
            (req.session_id,)
        )
        row = cur.fetchone()
        if row:
            file_path = Path(row["cleaned_path"])

    conn.close()

    if not file_path or not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No processed file found. Run /api/clean (and optionally /api/engineer) first."
        )

    # Load DataFrame
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read file: {e}")

    # Run analysis
    try:
        report = run_analysis_pipeline(df, req.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

    # Persist report
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS analysis_reports (
            session_id  TEXT PRIMARY KEY,
            report_json TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute(
        "INSERT OR REPLACE INTO analysis_reports (session_id, report_json) VALUES (?, ?)",
        (req.session_id, report.model_dump_json())
    )
    conn.commit()
    conn.close()

    n_insights = len(report.key_insights)
    n_warnings = len(report.warnings)

    return AnalysisResponse(
        success = True,
        message = (
            f"Analysis complete: {len(report.descriptive)} numeric columns analysed, "
            f"{len(report.correlations)} significant correlations found, "
            f"{n_insights} insights, {n_warnings} warnings."
        ),
        report  = report,
    )


@router.get("/analyze/{session_id}", summary="Retrieve stored analysis report")
async def get_analysis_report(session_id: str):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT report_json FROM analysis_reports WHERE session_id = ?",
        (session_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No analysis report found.")
    return json.loads(row["report_json"])