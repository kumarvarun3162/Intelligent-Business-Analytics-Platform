# backend/api/routes/report.py

import json
import pandas as pd
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.narrator      import generate_narrative
from core.report_builder import build_data_passport, assemble_report
from core.pdf_generator  import build_html_report, generate_pdf
from models.schemas      import ReportResponse, CleaningReport, EngineeringReport, InsightsReport
from core.paths import REPORTS_DIR
from storage.database    import get_connection

router = APIRouter(prefix="/api", tags=["report"])

REPORTS_DIR = Path("uploads") / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


class ReportRequest(BaseModel):
    session_id: str


# ── Helper: load all reports for a session ───────────────────────

def _load_session_reports(session_id: str):
    """Load cleaning, engineering, and analysis reports from SQLite."""
    conn = get_connection()
    cur  = conn.cursor()

    cleaning_report    = None
    engineering_report = None
    insights_report    = None
    dataset_name       = session_id[:12]

    cur.execute("SELECT original_name FROM sessions WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    if row:
        dataset_name = row["original_name"]

    cur.execute("SELECT report_json FROM cleaning_reports WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    if row:
        cleaning_report = CleaningReport(**json.loads(row["report_json"]))

    cur.execute("SELECT report_json FROM engineering_reports WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    if row:
        engineering_report = EngineeringReport(**json.loads(row["report_json"]))

    cur.execute("SELECT report_json FROM analysis_reports WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    if row:
        insights_report = InsightsReport(**json.loads(row["report_json"]))

    conn.close()
    return dataset_name, cleaning_report, engineering_report, insights_report


@router.post(
    "/report/generate",
    response_model=ReportResponse,
    summary="Generate full LLM-narrated report for a session",
)
async def generate_report(req: ReportRequest):
    """
    Orchestrates the full Phase 6 pipeline:
    1. Load all prior phase reports
    2. Call Groq LLM to generate narrative sections
    3. Build data passport
    4. Assemble final ReportConfig
    5. Generate PDF
    6. Persist everything
    """

    dataset_name, cleaning_report, engineering_report, insights_report = \
        _load_session_reports(req.session_id)

    if not cleaning_report:
        raise HTTPException(
            status_code=404,
            detail="No cleaning report found. Run /api/clean first."
        )

    # ── 1. Generate LLM narrative ────────────────────────────────
    try:
        narrative = generate_narrative(
            insights_report    = insights_report,
            cleaning_report    = cleaning_report,
            engineering_report = engineering_report,
            dataset_name       = dataset_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Narrative generation failed: {e}")

    # ── 2. Build data passport ───────────────────────────────────
    passport = build_data_passport(
        session_id          = req.session_id,
        dataset_name        = dataset_name,
        cleaning_report     = cleaning_report,
        engineering_report  = engineering_report,
        insights_report     = insights_report,
    )

    # ── 3. Assemble report config ────────────────────────────────
    report_config = assemble_report(
        session_id   = req.session_id,
        dataset_name = dataset_name,
        narrative    = narrative,
        data_passport = passport,
    )

    # ── 4. Generate PDF ──────────────────────────────────────────
    pdf_path = REPORTS_DIR / f"{req.session_id}_report.pdf"
    try:
        html = build_html_report(report_config, insights_report)
        generate_pdf(html, pdf_path)
    except Exception as e:
        # PDF failure shouldn't block the JSON response
        pdf_path = None
        print(f"PDF generation failed (non-fatal): {e}")

    # ── 5. Persist report ────────────────────────────────────────
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            session_id   TEXT PRIMARY KEY,
            report_json  TEXT,
            pdf_path     TEXT,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute(
        "INSERT OR REPLACE INTO reports (session_id, report_json, pdf_path) VALUES (?, ?, ?)",
        (req.session_id, report_config.model_dump_json(),
         str(pdf_path) if pdf_path else None)
    )
    conn.commit()
    conn.close()

    n_sections = len(narrative)
    return ReportResponse(
        success = True,
        message = (
            f"Report generated: {n_sections} narrative sections, "
            f"PDF {'ready' if pdf_path else 'unavailable'}."
        ),
        report  = report_config,
    )


@router.get("/report/{session_id}", summary="Retrieve stored report")
async def get_report(session_id: str):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT report_json FROM reports WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No report found.")
    return json.loads(row["report_json"])


# ── Download endpoints ───────────────────────────────────────────

@router.get("/download/{session_id}/pdf", summary="Download PDF report")
async def download_pdf(session_id: str):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT pdf_path FROM reports WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()

    if not row or not row["pdf_path"]:
        raise HTTPException(status_code=404, detail="PDF not found. Generate report first.")

    pdf_path = Path(row["pdf_path"])
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file missing from disk.")

    return FileResponse(
        path     = str(pdf_path),
        filename = f"report_{session_id[:8]}.pdf",
        media_type = "application/pdf",
    )


@router.get("/download/{session_id}/csv", summary="Download ML-ready CSV")
async def download_csv(session_id: str):
    conn = get_connection()
    cur  = conn.cursor()

    # Try engineered first, then cleaned
    cur.execute("SELECT engineered_path FROM engineering_reports WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    file_path = None

    if row:
        p = Path(row["engineered_path"])
        if p.exists():
            file_path = p

    if not file_path:
        cur.execute("SELECT cleaned_path FROM cleaning_reports WHERE session_id = ?", (session_id,))
        row = cur.fetchone()
        if row:
            p = Path(row["cleaned_path"])
            if p.exists():
                file_path = p

    conn.close()

    if not file_path:
        raise HTTPException(status_code=404, detail="No processed CSV found.")

    return FileResponse(
        path       = str(file_path),
        filename   = f"ml_ready_{session_id[:8]}.csv",
        media_type = "text/csv",
    )


@router.get("/download/{session_id}/passport", summary="Download data passport JSON")
async def download_passport(session_id: str):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT report_json FROM reports WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="No report found.")

    report = json.loads(row["report_json"])
    passport = report.get("data_passport", {})

    # Return as downloadable JSON file
    from fastapi.responses import Response
    return Response(
        content      = json.dumps(passport, indent=2),
        media_type   = "application/json",
        headers      = {
            "Content-Disposition":
                f'attachment; filename="passport_{session_id[:8]}.json"'
        },
    )