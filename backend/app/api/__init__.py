"""API router exports."""
from app.api.agents import router as agents
from app.api.placeholders import (
    messages_router as messages,
    proposals_router as proposals,
    laws_router as laws,
    resources_router as resources,
    events_router as events,
    analytics_router as analytics,
)
