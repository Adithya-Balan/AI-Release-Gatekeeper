"""API routes for analysis submission and retrieval."""

from __future__ import annotations

import asyncio
import logging
import time
import json
import os
import uuid
from datetime import datetime, timezone

import collections
from fastapi import APIRouter, HTTPException, Header

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

_analyses: dict[str, dict[str, AnalysisResponse]] = collections.defaultdict(dict)

def _get_history_file(user_id: str) -> str:
    safe_id = "".join(c for c in user_id if c.isalnum() or c in "-_") or "default"
    return f"data/history_{safe_id}.json"

def _load_history(user_id: str):
    file_path = _get_history_file(user_id)
    if os.path.exists(file_path) and not _analyses.get(user_id):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                for k, v in data.items():
                    _analyses[user_id][k] = AnalysisResponse(**v)
        except Exception as e:
            logger.error(f"Failed to load history for {user_id}: {e}")

def _save_history(user_id: str):
    try:
        os.makedirs("data", exist_ok=True)
        file_path = _get_history_file(user_id)
        with open(file_path, "w") as f:
            json.dump({k: v.model_dump(mode="json") for k, v in _analyses[user_id].items()}, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save history for {user_id}: {e}")

def _get_settings_file(user_id: str) -> str:
    safe_id = "".join(c for c in user_id if c.isalnum() or c in "-_") or "default"
    return f"data/settings_{safe_id}.json"

def _get_user_settings(user_id: str) -> dict:
    file_path = _get_settings_file(user_id)
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_user_settings(user_id: str, settings: dict):
    os.makedirs("data", exist_ok=True)
    with open(_get_settings_file(user_id), "w") as f:
        json.dump(settings, f, indent=2)


def _get_orchestrator():
    """Get the global orchestrator instance from app state."""
    from api.app import orchestrator

    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return orchestrator


@router.post("/analyze", response_model=AnalysisResponse)
async def submit_analysis(request: AnalyzeRequest, x_user_id: str = Header(default="anonymous")):
    _load_history(x_user_id)
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
    _analyses[x_user_id][analysis_id] = response
    _save_history(x_user_id)

    # Start analysis in background
    asyncio.create_task(_run_analysis(x_user_id, analysis_id, request.pr_url))

    return response


@router.get("/analysis/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(analysis_id: str, x_user_id: str = Header(default="anonymous")):
    """Get the status and results of an analysis."""
    _load_history(x_user_id)
    if analysis_id not in _analyses[x_user_id]:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _analyses[x_user_id][analysis_id]


@router.get("/analyses", response_model=list[AnalysisResponse])
async def list_analyses(x_user_id: str = Header(default="anonymous")):
    """List all analyses, most recent first."""
    _load_history(x_user_id)
    return sorted(
        _analyses[x_user_id].values(),
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
        "analyses_count": sum(len(user_analyses) for user_analyses in _analyses.values()),
    }


class SettingsUpdate(BaseModel):
    github_token: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None


@router.get("/settings")
async def get_settings(x_user_id: str = Header(default="anonymous")):
    """Get non-sensitive parts of settings."""
    user_settings = _get_user_settings(x_user_id)
    return {
        "github_token_set": bool(user_settings.get("github_token") or os.getenv("GITHUB_TOKEN")),
        "llm_api_key_set": bool(user_settings.get("llm_api_key") or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")),
        "llm_model": user_settings.get("llm_model") or os.getenv("LLM_MODEL", "gemini-2.5-flash"),
    }


@router.post("/settings")
async def update_settings(settings: SettingsUpdate, x_user_id: str = Header(default="anonymous")):
    """Update user-specific settings."""
    current = _get_user_settings(x_user_id)
    if settings.github_token is not None:
        current["github_token"] = settings.github_token
    if settings.llm_api_key is not None:
        current["llm_api_key"] = settings.llm_api_key
    if settings.llm_model is not None:
        current["llm_model"] = settings.llm_model
        
    _save_user_settings(x_user_id, current)
    return {"status": "success"}


async def _run_analysis(user_id: str, analysis_id: str, pr_url: str):
    """Background task: fetch data, run agents, aggregate verdict."""
    orchestrator = _get_orchestrator()
    start_time = time.time()
    
    settings = _get_user_settings(user_id)
    github_token = settings.get("github_token") or os.getenv("GITHUB_TOKEN", "")

    try:
        # Step 1: Fetch GitHub data
        _analyses[user_id][analysis_id].status = AnalysisStatus.FETCHING
        logger.info(f"[{analysis_id}] Fetching PR data from GitHub for user {user_id}...")

        github = GitHubService(token=github_token)
        try:
            pr_data, repo_data = await github.fetch_analysis_input(pr_url)
        finally:
            await github.close()

        logger.info(
            f"[{analysis_id}] Fetched: {pr_data.owner}/{pr_data.repo}#{pr_data.pr_number} "
            f"({pr_data.changed_files_count} files, +{pr_data.additions}/-{pr_data.deletions})"
        )

        # Step 2: Run agents
        _analyses[user_id][analysis_id].status = AnalysisStatus.ANALYZING
        logger.info(f"[{analysis_id}] Running agent analysis...")

        agent_reports = await orchestrator.run_analysis(pr_data, repo_data)

        completed = sum(1 for r in agent_reports.values() if r.status == "completed")
        logger.info(f"[{analysis_id}] {completed}/{len(agent_reports)} agents completed")

        # Step 3: Aggregate verdict
        _analyses[user_id][analysis_id].status = AnalysisStatus.AGGREGATING
        logger.info(f"[{analysis_id}] Aggregating verdict...")

        total_duration_ms = int((time.time() - start_time) * 1000)
        verdict = compute_verdict(analysis_id, pr_url, agent_reports, total_duration_ms)
        verdict.timestamp = datetime.now(timezone.utc).isoformat()

        # Step 4: Store result
        _analyses[user_id][analysis_id].status = AnalysisStatus.COMPLETED
        _analyses[user_id][analysis_id].verdict = verdict
        _save_history(user_id)

        logger.info(
            f"[{analysis_id}] ✅ Analysis complete: "
            f"confidence={verdict.deployment_confidence}, "
            f"grade={verdict.grade}, "
            f"ship={verdict.ship_recommendation.value}"
        )

    except Exception as e:
        logger.error(f"[{analysis_id}] ❌ Analysis failed: {e}", exc_info=True)
        _analyses[user_id][analysis_id].status = AnalysisStatus.FAILED
        _analyses[user_id][analysis_id].error = str(e)
        _save_history(user_id)
