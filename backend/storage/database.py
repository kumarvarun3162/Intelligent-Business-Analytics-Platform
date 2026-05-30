# backend/storage/database.py

import sqlite3
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

# ── DB path — must match STORAGE_DIR from paths.py ───────────────
_render_disk = os.getenv("RENDER_DISK_PATH", "").strip()

if _render_disk:
    _storage_dir = Path(_render_disk) / "storage"
else:
    # Local dev: backend/storage/ibap.sqlite3
    _storage_dir = Path(__file__).parent.parent / "storage"

# Ensure the storage directory exists before defining DB_PATH
_storage_dir.mkdir(parents=True, exist_ok=True)

DB_PATH = _storage_dir / "ibap.sqlite3"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't already exist. Called once at startup."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id    TEXT PRIMARY KEY,
            original_name TEXT NOT NULL,
            file_type     TEXT NOT NULL,
            file_size_kb  REAL,
            row_count     INTEGER,
            column_count  INTEGER,
            encoding      TEXT,
            upload_path   TEXT,
            metadata_json TEXT,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            status        TEXT DEFAULT 'completed'
        )
    """)

    conn.commit()
    conn.close()
    print(f"✅ SQLite ready at {DB_PATH}")


def save_session(
    session_id:    str,
    original_name: str,
    file_type:     str,
    file_size_kb:  float,
    row_count:     int,
    column_count:  int,
    encoding:      str,
    upload_path:   str,
    metadata_dict: Dict[str, Any],
) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (
            session_id, original_name, file_type, file_size_kb,
            row_count, column_count, encoding, upload_path, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id, original_name, file_type, file_size_kb,
        row_count, column_count, encoding, upload_path,
        json.dumps(metadata_dict),
    ))
    conn.commit()
    conn.close()


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    result["metadata"] = json.loads(result.pop("metadata_json", "{}"))
    return result


def list_sessions(limit: int = 20) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT session_id, original_name, file_type,
               file_size_kb, row_count, column_count, created_at, status
        FROM sessions
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows