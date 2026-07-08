"""API routes for analysis submission and retrieval."""

from __future__ import annotations

import asyncio
import logging
import time
import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from pydantic import BaseModel
from orchestrator.aggregator import compute_verdict
from orchestrator.schemas import (
    AnalyzeRequest,
    AnalysisResponse,
    AnalysisStatus,
)
from services.github import GitHubService, parse_pr_url

logger = logging.getLogger(__name__)

router = APIRouter()

HISTORY_FILE = "data/history.json"
_analyses: dict[str, AnalysisResponse] = {}

def _load_history():
    global _analyses
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                for k, v in data.items():
                    _analyses[k] = AnalysisResponse(**v)
        except Exception as e:
            logger.error(f"Failed to load history: {e}")

def _save_history():
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w") as f:
            json.dump({k: v.model_dump(mode="json") for k, v in _analyses.items()}, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save history: {e}")

_load_history()


def _get_orchestrator():
    """Get the global orchestrator instance from app state."""
    from api.app import orchestrator

    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return orchestrator


@router.post("/analyze", response_model=AnalysisResponse)
async def submit_analysis(request: AnalyzeRequest):
    """Submit a GitHub PR URL for release risk analysis.

    Returns an analysis ID that can be used to poll for results.
    The analysis runs asynchronously in the background.
    """
    # Validate PR URL
    try:
        owner, repo, pr_number = parse_pr_url(request.pr_url)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid GitHub PR URL. Expected format: https://github.com/owner/repo/pull/123",
        )

    analysis_id = str(uuid.uuid4())[:12]
    now = datetime.now(timezone.utc).isoformat()

    response = AnalysisResponse(
        analysis_id=analysis_id,
        status=AnalysisStatus.PENDING,
        pr_url=request.pr_url,
        created_at=now,
    )
    _analyses[analysis_id] = response
    _save_history()

    # Start analysis in background
    asyncio.create_task(_run_analysis(analysis_id, request.pr_url))

    return response


@router.get("/analysis/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(analysis_id: str):
    """Get the status and results of an analysis."""
    if analysis_id not in _analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _analyses[analysis_id]


@router.get("/analyses", response_model=list[AnalysisResponse])
async def list_analyses():
    """List all analyses, most recent first."""
    return sorted(
        _analyses.values(),
        key=lambda a: a.created_at,
        reverse=True,
    )


@router.get("/health")
async def health_check():
    """System health check."""
    orchestrator = _get_orchestrator()
    return {
        "status": "healthy",
        "mode": "croo" if orchestrator.use_croo else "local",
        "analyses_count": len(_analyses),
    }


class SettingsUpdate(BaseModel):
    github_token: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None


@router.get("/settings")
async def get_settings():
    """Get non-sensitive parts of settings."""
    return {
        "github_token_set": bool(os.getenv("GITHUB_TOKEN")),
        "llm_api_key_set": bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")),
        "llm_model": os.getenv("LLM_MODEL", "gemini-2.5-flash"),
    }


@router.post("/settings")
async def update_settings(settings: SettingsUpdate):
    """Update settings in .env file (very simple implementation)."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    
    # Read current
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
            
    # Helper to update
    def update_key(key: str, val: str):
        if not val:
            return
        os.environ[key] = val
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={val}\n"
                return
        lines.append(f"{key}={val}\n")

    update_key("GITHUB_TOKEN", settings.github_token)
    update_key("LLM_API_KEY", settings.llm_api_key)
    update_key("LLM_MODEL", settings.llm_model)

    with open(env_path, "w") as f:
        f.writelines(lines)

    return {"status": "success"}


async def _run_analysis(analysis_id: str, pr_url: str):
    """Background task: fetch data, run agents, aggregate verdict."""
    orchestrator = _get_orchestrator()
    start_time = time.time()

    try:
        # Step 1: Fetch GitHub data
        _analyses[analysis_id].status = AnalysisStatus.FETCHING
        logger.info(f"[{analysis_id}] Fetching PR data from GitHub...")

        github = GitHubService()
        try:
            pr_data, repo_data = await github.fetch_analysis_input(pr_url)
        finally:
            await github.close()

        logger.info(
            f"[{analysis_id}] Fetched: {pr_data.owner}/{pr_data.repo}#{pr_data.pr_number} "
            f"({pr_data.changed_files_count} files, +{pr_data.additions}/-{pr_data.deletions})"
        )

        # Step 2: Run agents
        _analyses[analysis_id].status = AnalysisStatus.ANALYZING
        logger.info(f"[{analysis_id}] Running agent analysis...")

        agent_reports = await orchestrator.run_analysis(pr_data, repo_data)

        completed = sum(1 for r in agent_reports.values() if r.status == "completed")
        logger.info(f"[{analysis_id}] {completed}/{len(agent_reports)} agents completed")

        # Step 3: Aggregate verdict
        _analyses[analysis_id].status = AnalysisStatus.AGGREGATING
        logger.info(f"[{analysis_id}] Aggregating verdict...")

        total_duration_ms = int((time.time() - start_time) * 1000)
        verdict = compute_verdict(analysis_id, pr_url, agent_reports, total_duration_ms)
        verdict.timestamp = datetime.now(timezone.utc).isoformat()

        # Step 4: Store result
        _analyses[analysis_id].status = AnalysisStatus.COMPLETED
        _analyses[analysis_id].verdict = verdict
        _save_history()

        logger.info(
            f"[{analysis_id}] ✅ Analysis complete: "
            f"confidence={verdict.deployment_confidence}, "
            f"grade={verdict.grade}, "
            f"ship={verdict.ship_recommendation.value}"
        )

    except Exception as e:
        logger.error(f"[{analysis_id}] ❌ Analysis failed: {e}", exc_info=True)
        _analyses[analysis_id].status = AnalysisStatus.FAILED
        _analyses[analysis_id].error = str(e)
        _save_history()
