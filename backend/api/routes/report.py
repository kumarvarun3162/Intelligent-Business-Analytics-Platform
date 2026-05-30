# backend/api/routes/report.py

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from core.narrator       import generate_narrative
from core.report_builder import build_data_passport, assemble_report
from core.pdf_generator  import build_html_report, generate_pdf
from models.schemas      import ReportResponse, CleaningReport, EngineeringReport, InsightsReport
from core.paths          import REPORTS_DIR          # ← use this, don't overwrite
from storage.database    import get_connection

router = APIRouter(prefix="/api", tags=["report"])

# ── DO NOT redefine REPORTS_DIR here — use the one from core.paths ──


class ReportRequest(BaseModel):
    session_id: str


def _load_session_reports(session_id: str):
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

    dataset_name, cleaning_report, engineering_report, insights_report = \
        _load_session_reports(req.session_id)

    # Check session exists
    if not cleaning_report:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute("SELECT session_id FROM sessions WHERE session_id = ?",
                    (req.session_id,))
        exists = cur.fetchone()
        conn.close()

        if not exists:
            raise HTTPException(
                status_code=404,
                detail=f"Session '{req.session_id}' not found. Upload a file first."
            )
        raise HTTPException(
            status_code=400,
            detail="No cleaning report found. Run POST /api/clean before generating a report."
        )

    # Generate LLM narrative
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
        raise HTTPException(status_code=500, detail=f"Narrative generation failed: {str(e)}")

    # Build data passport
    passport = build_data_passport(
        session_id         = req.session_id,
        dataset_name       = dataset_name,
        cleaning_report    = cleaning_report,
        engineering_report = engineering_report,
        insights_report    = insights_report,
    )

    # Assemble report config
    report_config = assemble_report(
        session_id    = req.session_id,
        dataset_name  = dataset_name,
        narrative     = narrative,
        data_passport = passport,
    )

    # Generate PDF (non-fatal if it fails)
    pdf_path = None
    try:
        pdf_path = REPORTS_DIR / f"{req.session_id}_report.pdf"
        html     = build_html_report(report_config, insights_report)
        generate_pdf(html, pdf_path)
    except Exception as e:
        pdf_path = None
        print(f"⚠️  PDF generation failed (non-fatal): {e}")

    # Persist report
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

    return ReportResponse(
        success = True,
        message = (
            f"Report generated: {len(narrative)} sections, "
            f"PDF {'ready' if pdf_path else 'skipped'}."
        ),
        report = report_config,
    )


@router.get("/report/debug/{session_id}", summary="Debug: show what reports exist")
async def debug_session(session_id: str):
    conn = get_connection()
    cur  = conn.cursor()
    result = {"session_id": session_id}
    for table in ["sessions", "cleaning_reports", "engineering_reports",
                  "analysis_reports", "dashboards", "reports"]:
        try:
            cur.execute(f"SELECT COUNT(*) as c FROM {table} WHERE session_id = ?",
                        (session_id,))
            row = cur.fetchone()
            result[table] = "found" if row and row["c"] > 0 else "missing"
        except Exception:
            result[table] = "table_not_exists"
    conn.close()
    return result


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


@router.get("/download/{session_id}/pdf")
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
        path       = str(pdf_path),
        filename   = f"report_{session_id[:8]}.pdf",
        media_type = "application/pdf",
    )


@router.get("/download/{session_id}/csv")
async def download_csv(session_id: str):
    conn = get_connection()
    cur  = conn.cursor()

    file_path = None
    cur.execute("SELECT engineered_path FROM engineering_reports WHERE session_id = ?",
                (session_id,))
    row = cur.fetchone()
    if row:
        p = Path(row["engineered_path"])
        if p.exists():
            file_path = p

    if not file_path:
        cur.execute("SELECT cleaned_path FROM cleaning_reports WHERE session_id = ?",
                    (session_id,))
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


@router.get("/download/{session_id}/passport")
async def download_passport(session_id: str):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT report_json FROM reports WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="No report found.")

    report   = json.loads(row["report_json"])
    passport = report.get("data_passport", {})

    return Response(
        content    = json.dumps(passport, indent=2),
        media_type = "application/json",
        headers    = {
            "Content-Disposition":
                f'attachment; filename="passport_{session_id[:8]}.json"'
        },
    )