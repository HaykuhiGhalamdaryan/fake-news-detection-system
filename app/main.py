# main.py

import logging
import os
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.routers import analyze, health, history, analytics, trusted_sources
from app.services.scheduler import start_scheduler, stop_scheduler
from app.database.db import engine
from app.database import models
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Logging — DEBUG in development, WARNING in production
# Set LOG_LEVEL=DEBUG in .env for verbose output during development.
# ---------------------------------------------------------------------------
_LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=getattr(logging, _LOG_LEVEL, logging.WARNING))
logger = logging.getLogger(__name__)

models.Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
_ENV = os.getenv("APP_ENV", "production").lower()

app = FastAPI(
    title="Fake News Detection System",
    description="Social Media Fake News & Credibility Analysis",
    version="1.0",
)

# ---------------------------------------------------------------------------
# CORS — restrict to configured origins in production
# Set ALLOWED_ORIGINS=https://yourdomain.com in .env for production.
# Defaults to "*" only in development mode.
# ---------------------------------------------------------------------------
_raw_origins = os.getenv("ALLOWED_ORIGINS", "")
_allow_origins = (
    [o.strip() for o in _raw_origins.split(",") if o.strip()]
    if _raw_origins
    else (["*"] if _ENV == "development" else [])
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins or ["*"],   # fallback for local dev
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global error handler
# In production: return a safe generic message (no traceback exposed).
# In development: include traceback for easier debugging.
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error("UNHANDLED EXCEPTION on %s\n%s", request.url, tb)

    if _ENV == "development":
        content = {"detail": str(exc), "traceback": tb}
    else:
        content = {"detail": "An internal error occurred. Please try again."}

    return JSONResponse(status_code=500, content=content)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(analyze.router)
app.include_router(health.router)
app.include_router(history.router)
app.include_router(analytics.router)
app.include_router(trusted_sources.router)

# Serve static files (index.html)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.on_event("startup")
def startup_event():
    start_scheduler()

@app.on_event("shutdown")
def shutdown_event():
    stop_scheduler()