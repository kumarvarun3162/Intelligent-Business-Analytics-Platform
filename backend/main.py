# backend/main.py

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

# ── Import paths BEFORE anything else so dirs exist at startup ───
from core.paths import ensure_dirs, DISK_ROOT, STORAGE_DIR
from storage.database import init_db, DB_PATH

from api.routes.upload        import router as upload_router
from api.routes.clean         import router as clean_router
from api.routes.engineer      import router as engineer_router
from api.routes.analyze       import router as analyze_router
from api.routes.charts        import router as charts_router
from api.routes.report        import router as report_router
from api.routes.report_stream import router as report_stream_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting IBAP backend...")

    # Create all storage directories first
    ensure_dirs()

    # Then initialize DB (DB_PATH directory must exist first)
    init_db()

    debug = os.getenv("DEBUG", "true").lower() == "true"

    if not debug:
        if not os.getenv("GROQ_API_KEY", ""):
            print("⚠️  WARNING: GROQ_API_KEY not set — report generation will fail")
        if not os.getenv("RENDER_DISK_PATH", ""):
            print("⚠️  WARNING: RENDER_DISK_PATH not set — files won't persist on Render")

    print(f"✅ Database initialized at {DB_PATH}")
    print(f"📁 Storage root: {DISK_ROOT}")
    print(f"🔧 Debug mode: {debug}")
    yield
    print("🛑 Shutting down IBAP backend...")


app = FastAPI(
    title       = "IBAP — Intelligent Business Analytics Platform",
    description = "Upload raw data → clean → engineer → analyse → visualise → report.",
    version     = "0.1.0",
    lifespan    = lifespan,
    docs_url    = "/docs" if os.getenv("DEBUG", "true").lower() == "true" else None,
    redoc_url   = None,
)

# ── CORS ─────────────────────────────────────────────────────────
# Reads from .env — covers both Vite dev port (5173) and any custom port
_origins_env = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173"
)
ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ALLOWED_ORIGINS,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── API routers ───────────────────────────────────────────────────
app.include_router(upload_router)
app.include_router(clean_router)
app.include_router(engineer_router)
app.include_router(analyze_router)
app.include_router(charts_router)
app.include_router(report_router)
app.include_router(report_stream_router)


# ── Health check ──────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health_check():
    return {
        "status":   "healthy",
        "version":  "0.1.0",
        "db_path":  str(DB_PATH),
        "disk_root": str(DISK_ROOT),
    }


# ── Serve React SPA (production only) ────────────────────────────
STATIC_DIR = Path(__file__).parent / "static"

if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(STATIC_DIR / "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        return FileResponse(str(STATIC_DIR / "index.html"))