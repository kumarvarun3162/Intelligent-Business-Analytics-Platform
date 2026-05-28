"""
Centralised file path management.
All file I/O in the app should import paths from here.
This makes switching between local dev and Render Disk trivial.
"""

import os
from pathlib import Path

# Root of persistent storage:
# - local dev:   backend/uploads/
# - Render:      /data/  (Render Disk mounted at /data)
DISK_ROOT = Path(os.getenv("RENDER_DISK_PATH", str(Path(__file__).parent.parent)))

UPLOAD_DIR     = DISK_ROOT / "uploads"
CLEANED_DIR    = DISK_ROOT / "uploads" / "cleaned"
ENGINEERED_DIR = DISK_ROOT / "uploads" / "engineered"
REPORTS_DIR    = DISK_ROOT / "uploads" / "reports"
STORAGE_DIR    = DISK_ROOT / "storage"

def ensure_dirs():
    """Create all required directories if they don't exist."""
    for d in [UPLOAD_DIR, CLEANED_DIR, ENGINEERED_DIR, REPORTS_DIR, STORAGE_DIR]:
        d.mkdir(parents=True, exist_ok=True)
