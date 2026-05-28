# backend/api/routes/upload.py

import os
import aiofiles
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse

from models.schemas import UploadResponse, ErrorResponse
from core.ingestion import ingest_file
from storage.database import save_session

from core.paths import UPLOAD_DIR, ensure_dirs


ensure_dirs()


router = APIRouter(prefix="/api", tags=["upload"])

# UPLOAD_DIR    = Path("uploads")
MAX_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTS  = {"csv", "xlsx", "xls", "json"}

# UPLOAD_DIR.mkdir(exist_ok=True)


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Upload a raw data file",
    description="Accepts CSV, Excel, or JSON. Returns metadata and a 10-row preview.",
)
async def upload_file(file: UploadFile = File(...)):
    """
    The main upload endpoint.

    Flow:
    1. Validate file extension and size
    2. Read bytes into memory
    3. Run ingestion pipeline (detect encoding → parse → profile)
    4. Save raw file to disk
    5. Persist session to SQLite
    6. Return metadata + preview to frontend
    """

    # ── 1. Extension check ──────────────────────────────────────
    filename = file.filename or "upload"
    ext = Path(filename).suffix.lower().lstrip(".")

    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '.{ext}' is not supported. "
                   f"Allowed: {', '.join(ALLOWED_EXTS)}",
        )

    # ── 2. Read file bytes ───────────────────────────────────────
    file_bytes = await file.read()
    file_size  = len(file_bytes)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if file_size > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size {file_size / (1024*1024):.1f} MB exceeds the 50 MB limit.",
        )

    # ── 3. Run ingestion pipeline ────────────────────────────────
    try:
        df, metadata, preview = ingest_file(file_bytes, filename, file_size)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse file: {str(e)}",
        )

    # ── 4. Save raw file to disk ─────────────────────────────────
    save_path = UPLOAD_DIR / f"{metadata.session_id}_{filename}"
    async with aiofiles.open(save_path, "wb") as f:
        await f.write(file_bytes)

    # ── 5. Persist session ───────────────────────────────────────
    save_session(
        session_id    = metadata.session_id,
        original_name = metadata.original_name,
        file_type     = metadata.file_type.value,
        file_size_kb  = metadata.file_size_kb,
        row_count     = metadata.row_count,
        column_count  = metadata.column_count,
        encoding      = metadata.encoding,
        upload_path   = str(save_path),
        metadata_dict = metadata.model_dump(),
    )

    # ── 6. Return response ───────────────────────────────────────
    return UploadResponse(
        success  = True,
        message  = f"Successfully parsed '{filename}': "
                   f"{metadata.row_count} rows × {metadata.column_count} columns.",
        metadata = metadata,
        preview  = preview,
    )


@router.get(
    "/sessions",
    summary="List recent upload sessions",
)
async def list_sessions_route():
    from storage.database import list_sessions
    return {"sessions": list_sessions()}


@router.get(
    "/sessions/{session_id}",
    summary="Get details for a specific session",
)
async def get_session_route(session_id: str):
    from storage.database import get_session
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session