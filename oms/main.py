"""
GHFM OMS — FastAPI application.

Entry point: uvicorn oms.main:app --reload
API docs:    http://localhost:8000/docs
"""

from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from oms.config import settings
from oms.database import Base, async_session_factory, engine
from oms.routers import orders, positions, reports
from oms.services.execution_service import process_execution_report
from oms.venue_simulator import VenueSimulator


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Wire venue simulator -> execution service callback
    callback = partial(process_execution_report, async_session_factory)
    venue = VenueSimulator(
        execution_callback=callback,
        fill_probability=settings.venue_fill_probability,
        partial_fill_probability=settings.venue_partial_fill_probability,
        min_latency_ms=settings.venue_min_latency_ms,
        max_latency_ms=settings.venue_max_latency_ms,
    )
    app.state.venue = venue

    yield

    await engine.dispose()


app = FastAPI(
    title="GHFM OMS",
    description="Order Management System prototype for Golden Horse Fund Management",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orders.router, prefix="/orders", tags=["Orders"])
app.include_router(positions.router, prefix="/positions", tags=["Positions"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])

# Serve dashboard
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "system": settings.app_name, "version": settings.app_version}


@app.get("/", include_in_schema=False)
async def root():
    """Serve the trading dashboard at root URL."""
    dashboard = Path(__file__).parent.parent / "static" / "index.html"
    if dashboard.exists():
        return FileResponse(str(dashboard))
    return {"message": "GHFM OMS API", "docs": "/docs"}
