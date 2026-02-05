"""
Emergence - AI Civilization Experiment
Main FastAPI Application
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from app.core.config import settings
from app.api.agents import router as agents_router
from app.api.events import router as events_router
from app.api.laws import router as laws_router
from app.api.messages import router as messages_router
from app.api.proposals import router as proposals_router
from app.api.resources import router as resources_router
from app.api.analytics import router as analytics_router
from app.services.sse import router as sse_router, event_polling_task
from app.api.twitter import router as twitter_router
from app.api.predictions import router as predictions_router

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper()))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Emergence API...")
    logger.info(
        "LLM config: provider=%s groq=%s openrouter=%s groq_default_model=%s",
        getattr(settings, "LLM_PROVIDER", "auto"),
        bool(getattr(settings, "GROQ_API_KEY", "")),
        bool(getattr(settings, "OPENROUTER_API_KEY", "")),
        getattr(settings, "GROQ_DEFAULT_MODEL", ""),
    )
    poller = asyncio.create_task(event_polling_task())
    yield
    poller.cancel()
    logger.info("Shutting down Emergence API...")


app = FastAPI(
    title="Emergence API",
    description="AI Civilization Experiment - Watch 100 AI agents build their own society",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(agents_router, prefix="/api/agents", tags=["agents"])
app.include_router(messages_router, prefix="/api/messages", tags=["messages"])
app.include_router(proposals_router, prefix="/api/proposals", tags=["proposals"])
app.include_router(laws_router, prefix="/api/laws", tags=["laws"])
app.include_router(resources_router, prefix="/api/resources", tags=["resources"])
app.include_router(events_router, prefix="/api/events", tags=["events"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["analytics"])
app.include_router(sse_router, prefix="/api/events", tags=["sse"])
app.include_router(twitter_router, prefix="/api", tags=["twitter"])
app.include_router(predictions_router, prefix="/api/predictions", tags=["predictions"])


@app.get("/health")
async def health_check():
    """Liveness check (should be fast and not depend on external services)."""
    return {
        "status": "ok",
        "service": "emergence-backend",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/ready")
async def readiness_check():
    """Readiness check (verifies critical dependencies like the database)."""
    try:
        from sqlalchemy import text

        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()

        return {"status": "ready"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not_ready", "error": str(e)})


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Emergence API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
