# backend/main.py  ← complete replacement

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from storage.database import init_db
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
    init_db()
    print("✅ Database initialized")
    yield
    print("🛑 Shutting down IBAP backend...")


app = FastAPI(
    title       = "IBAP — Intelligent Business Analytics Platform",
    description = "Upload raw data → clean → engineer → analyse → visualise → report.",
    version     = "0.1.0",
    lifespan    = lifespan,
    # Hide docs in production
    docs_url    = "/docs" if os.getenv("DEBUG", "true").lower() == "true" else None,
    redoc_url   = None,
)

# ── CORS ──────────────────────────────────────────────────────────
# In production on Render, the frontend is served from the same
# origin so CORS isn't needed. We still allow localhost for dev.
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173"
).split(",")

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
    return {"status": "healthy", "version": "0.1.0"}


# ── Serve React SPA ───────────────────────────────────────────────
# The dist/ folder is built by `npm run build` and copied here.
# In production on Render, the build step runs before the server starts.
STATIC_DIR = Path(__file__).parent / "static"

if STATIC_DIR.exists():
    # Serve JS/CSS/image assets
    app.mount(
        "/assets",
        StaticFiles(directory=STATIC_DIR / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """
        SPA catch-all: return index.html for every non-API path.
        The React router handles client-side navigation.
        """
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"error": "Frontend not built. Run: npm run build"}