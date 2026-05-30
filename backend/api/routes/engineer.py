# backend/api/routes/engineer.py

import json
import pandas as pd
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.engineering import run_engineering_pipeline
from core.ingestion   import get_preview
from models.schemas   import EngineeringResponse
from storage.database import get_connection
from core.paths       import ENGINEERED_DIR

router = APIRouter(prefix="/api", tags=["engineering"])


class EngineerRequest(BaseModel):
    session_id:    str
    scale_method:  str  = "auto"
    n_bins:        int  = 5
    bin_strategy:  str  = "quantile"
    drop_datetime: bool = False


@router.post("/engineer", response_model=EngineeringResponse,
             summary="Run feature engineering pipeline on cleaned data")
async def engineer_dataset(req: EngineerRequest):

    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT report_json, cleaned_path FROM cleaning_reports WHERE session_id = ?",
        (req.session_id,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No cleaning report found for '{req.session_id}'. Run /api/clean first."
        )

    report_data  = json.loads(row["report_json"])
    cleaned_path = Path(row["cleaned_path"])
    type_map     = report_data.get("column_type_map", {})

    if not cleaned_path.exists():
        raise HTTPException(status_code=404, detail="Cleaned file not found on disk.")

    try:
        df = pd.read_csv(cleaned_path)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read cleaned file: {e}")

    try:
        engineered_df, eng_report = run_engineering_pipeline(
            df            = df,
            session_id    = req.session_id,
            type_map      = type_map,
            scale_method  = req.scale_method,
            n_bins        = req.n_bins,
            bin_strategy  = req.bin_strategy,
            drop_datetime = req.drop_datetime,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Engineering pipeline failed: {e}")

    # ── Save engineered file (use ENGINEERED_DIR from paths.py) ──
    eng_path = ENGINEERED_DIR / f"{req.session_id}_engineered.csv"
    engineered_df.to_csv(eng_path, index=False)

    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS engineering_reports (
            session_id       TEXT PRIMARY KEY,
            report_json      TEXT,
            engineered_path  TEXT,
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        INSERT OR REPLACE INTO engineering_reports
            (session_id, report_json, engineered_path)
        VALUES (?, ?, ?)
    """, (req.session_id, eng_report.model_dump_json(), str(eng_path)))
    conn.commit()
    conn.close()

    preview  = get_preview(engineered_df, n=10)
    ml_badge = "ML-ready" if eng_report.ml_ready else "needs review"

    return EngineeringResponse(
        success = True,
        message = (
            f"Engineering complete ({ml_badge}). "
            f"{eng_report.original_col_count} → {eng_report.engineered_col_count} columns "
            f"(+{eng_report.new_cols_created} new). "
            f"{len(eng_report.transforms)} transforms applied."
        ),
        report  = eng_report,
        preview = preview,
    )


@router.get("/engineer/{session_id}", summary="Retrieve stored engineering report")
async def get_engineering_report(session_id: str):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT report_json FROM engineering_reports WHERE session_id = ?",
        (session_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No engineering report found.")
    return json.loads(row["report_json"])