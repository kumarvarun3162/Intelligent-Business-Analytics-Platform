import json
import pandas as pd
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.cleaning import run_cleaning_pipeline
from core.ingestion import get_preview
from models.schemas import CleaningResponse
from storage.database import get_session, get_connection

from core.paths import CLEANED_DIR


router = APIRouter(prefix="/api", tags=["cleaning"])


class CleanRequest(BaseModel):
    session_id:          str
    outlier_method:      str   = "iqr"    # "iqr" or "zscore"
    outlier_action:      str   = "cap"    # "cap", "flag", "drop"
    null_drop_threshold: float = 0.5      # drop col if null% > this


@router.post(
    "/clean",
    response_model=CleaningResponse,
    summary="Run the automated cleaning pipeline on an uploaded file",
)
async def clean_dataset(req: CleanRequest):
    """
    Trigger the 8-stage cleaning pipeline for a previously uploaded file.

    Flow:
    1. Load session from SQLite → get file path
    2. Re-read raw file into DataFrame
    3. Run cleaning pipeline
    4. Save cleaned file to disk
    5. Store cleaning report in SQLite
    6. Return report + cleaned preview
    """

    # ── 1. Load session ──────────────────────────────────────────
    session = get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404,
                            detail=f"Session '{req.session_id}' not found.")

    upload_path = Path(session["upload_path"])
    if not upload_path.exists():
        raise HTTPException(status_code=404,
                            detail="Original file not found on disk.")

    # ── 2. Re-read raw file ──────────────────────────────────────
    file_bytes = upload_path.read_bytes()
    file_type  = session["file_type"]

    from io import BytesIO
    buf = BytesIO(file_bytes)
    try:
        if file_type == "csv":
            df = pd.read_csv(buf, encoding=session.get("encoding", "utf-8"))
        elif file_type in ("xlsx", "xls"):
            df = pd.read_excel(buf, engine="openpyxl")
        elif file_type == "json":
            df = pd.read_json(buf)
        else:
            raise HTTPException(status_code=400,
                                detail=f"Unsupported file type: {file_type}")
    except Exception as e:
        raise HTTPException(status_code=422,
                            detail=f"Could not re-parse file: {e}")

    # ── 3. Run cleaning pipeline ─────────────────────────────────
    try:
        cleaned_df, report = run_cleaning_pipeline(
            df                  = df,
            session_id          = req.session_id,
            outlier_method      = req.outlier_method,
            outlier_action      = req.outlier_action,
            null_drop_threshold = req.null_drop_threshold,
        )
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Cleaning pipeline failed: {e}")

    # ── 4. Save cleaned file ─────────────────────────────────────
    cleaned_path = CLEANED_DIR / f"{req.session_id}_cleaned.csv"
    cleaned_df.to_csv(cleaned_path, index=False)

    # ── 5. Persist cleaning report ───────────────────────────────
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cleaning_reports (
            session_id    TEXT PRIMARY KEY,
            report_json   TEXT,
            cleaned_path  TEXT,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        INSERT OR REPLACE INTO cleaning_reports
            (session_id, report_json, cleaned_path)
        VALUES (?, ?, ?)
    """, (req.session_id, report.model_dump_json(), str(cleaned_path)))
    conn.commit()
    conn.close()

    # ── 6. Return response ───────────────────────────────────────
    preview = get_preview(cleaned_df, n=10)
    return CleaningResponse(
        success = True,
        message = (
            f"Cleaning complete. Quality score: {report.quality_score}/100 "
            f"(Grade {report.quality_grade}). "
            f"{report.rows_removed} rows removed, "
            f"{report.total_nulls_before - report.total_nulls_after} nulls filled."
        ),
        report  = report,
        preview = preview,
    )


@router.get(
    "/clean/{session_id}",
    summary="Retrieve a stored cleaning report",
)
async def get_cleaning_report(session_id: str):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT report_json FROM cleaning_reports WHERE session_id = ?",
        (session_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No cleaning report found.")
    return json.loads(row["report_json"])
