"""FastAPI application — main entry point for the AI Release Gatekeeper API."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import router
from orchestrator.client import OrchestratorClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Global orchestrator instance
orchestrator: OrchestratorClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    global orchestrator

    logger.info("🚀 Starting AI Release Gatekeeper...")

    orchestrator = OrchestratorClient()
    await orchestrator.initialize()

    mode = "CROO" if orchestrator.use_croo else "LOCAL"
    logger.info(f"✅ Orchestrator ready [{mode} mode]")

    yield

    logger.info("🛑 Shutting down...")
    if orchestrator:
        await orchestrator.close()


app = FastAPI(
    title="AI Release Gatekeeper",
    description="Multi-Agent Release Risk Orchestration Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(router, prefix="/api")

# Serve dashboard static files
dashboard_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard")
if os.path.exists(dashboard_dir):
    app.mount("/", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")
