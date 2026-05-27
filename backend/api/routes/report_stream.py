# backend/api/routes/report_stream.py

import os
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from groq import Groq

from storage.database import get_connection
from models.schemas import CleaningReport, EngineeringReport, InsightsReport
from core.narrator import _build_context, SECTIONS, _get_client

router = APIRouter(prefix="/api", tags=["report"])


class StreamRequest(BaseModel):
    session_id: str


@router.post("/report/stream", summary="Stream narrative generation section by section")
async def stream_report(req: StreamRequest):
    """
    SSE endpoint — yields JSON lines as each section is generated.
    The frontend listens with EventSource / fetch + ReadableStream.

    Each yielded line is:
    data: {"section": "executive_summary", "title": "...", "emoji": "...",
            "content": "...", "done": false}

    Final line:
    data: {"done": true}
    """

    # Load reports
    conn = get_connection()
    cur  = conn.cursor()
    cleaning_report = engineering_report = insights_report = None
    dataset_name = req.session_id[:12]

    cur.execute("SELECT original_name FROM sessions WHERE session_id = ?", (req.session_id,))
    row = cur.fetchone()
    if row: dataset_name = row["original_name"]

    for table, model_cls, attr in [
        ("cleaning_reports",    CleaningReport,    "cleaning_report"),
        ("engineering_reports", EngineeringReport, "engineering_report"),
        ("analysis_reports",    InsightsReport,    "insights_report"),
    ]:
        cur.execute(f"SELECT report_json FROM {table} WHERE session_id = ?", (req.session_id,))
        r = cur.fetchone()
        if r:
            if attr == "cleaning_report":    cleaning_report    = CleaningReport(**json.loads(r["report_json"]))
            elif attr == "engineering_report": engineering_report = EngineeringReport(**json.loads(r["report_json"]))
            elif attr == "insights_report":  insights_report    = InsightsReport(**json.loads(r["report_json"]))
    conn.close()

    context = _build_context(insights_report, cleaning_report, engineering_report, dataset_name)
    client  = _get_client()
    model   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    system  = (
        "You are a senior data scientist writing a professional business analytics report. "
        "Write in flowing prose only — no bullet points, no markdown, no backticks. "
        "Be specific, cite numbers, write for a business audience."
    )

    async def event_generator():
        for sec in SECTIONS:
            content_chunks = []
            try:
                stream = client.chat.completions.create(
                    model    = model,
                    messages = [
                        {"role": "system", "content": system},
                        {"role": "user",   "content":
                            f"Data context:\n{context}\n\nTask: {sec['prompt']}"},
                    ],
                    max_tokens  = sec["max_tokens"],
                    temperature = 0.4,
                    stream      = True,
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    content_chunks.append(delta)
                    # Stream each token chunk
                    yield f"data: {json.dumps({'section': sec['key'], 'title': sec['title'], 'emoji': sec['emoji'], 'chunk': delta, 'done': False})}\n\n"

            except Exception as e:
                content_chunks = [f"Section unavailable: {e}"]

            # Emit completed section
            yield f"data: {json.dumps({'section': sec['key'], 'title': sec['title'], 'emoji': sec['emoji'], 'content': ''.join(content_chunks), 'section_done': True})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type = "text/event-stream",
        headers    = {
            "Cache-Control":              "no-cache",
            "X-Accel-Buffering":          "no",
            "Access-Control-Allow-Origin": "*",
        },
    )