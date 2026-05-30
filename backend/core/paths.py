# backend/core/paths.py
"""
Centralised file path management.
All file I/O imports paths from here.
"""

import os
from pathlib import Path

# ── Determine storage root ────────────────────────────────────────
# RENDER_DISK_PATH is set to /data on Render.
# Locally it is empty ("") so we fall back to backend/
_render_disk = os.getenv("RENDER_DISK_PATH", "").strip()

if _render_disk:
    # Production: use Render Disk
    DISK_ROOT = Path(_render_disk)
else:
    # Local dev: store everything inside the backend folder
    DISK_ROOT = Path(__file__).parent.parent

# ── Derived paths ─────────────────────────────────────────────────
UPLOAD_DIR     = DISK_ROOT / "uploads"
CLEANED_DIR    = DISK_ROOT / "uploads" / "cleaned"
ENGINEERED_DIR = DISK_ROOT / "uploads" / "engineered"
REPORTS_DIR    = DISK_ROOT / "uploads" / "reports"
STORAGE_DIR    = DISK_ROOT / "storage"


def ensure_dirs() -> None:
    """Create all required directories if they don't exist."""
    for d in [UPLOAD_DIR, CLEANED_DIR, ENGINEERED_DIR, REPORTS_DIR, STORAGE_DIR]:
        d.mkdir(parents=True, exist_ok=True)