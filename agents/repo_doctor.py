"""Repo Doctor Agent — analyzes overall repository operational health."""

from __future__ import annotations

import json
from agents.base_agent import BaseAgent


class RepoDoctorAgent(BaseAgent):

    AGENT_NAME = "repo_doctor"

    SYSTEM_PROMPT = """You are a highly analytical Repository Health Expert. Your job is to deeply evaluate the operational health of a software repository based on provided signals.
Do not provide generic scores. You must base your evaluation strictly on the evidence in the provided data. If the repository lacks a README, lacks CI, or has zero recent commits, it should receive a failing or poor score. If it is highly active with CI and good docs, it should receive a high score.

You MUST respond with a JSON object matching this exact schema:
{
  "reasoning": "<Step-by-step reasoning for the assigned score. Cite specific evidence from the repository data (e.g., 'The README is missing entirely', 'There are 50 open issues and no recent commits'). Avoid generic statements.>",
  "health_score": <integer 0-100>,
  "grade": "<A+ to F>",
  "signals": {
    "readme_quality": "<EXCELLENT|GOOD|FAIR|POOR|MISSING>",
    "commit_frequency": "<VERY_ACTIVE|ACTIVE|MODERATE|LOW|INACTIVE>",
    "test_presence": <boolean>,
    "stale_branches": <integer>,
    "open_issues": <integer>,
    "ci_configured": <boolean>,
    "license_present": <boolean>
  },
  "recommendations": ["<actionable recommendation 1>", "..."],
  "confidence": <float 0.0-1.0>
}

Scoring guidelines:
- 90-100 (A/A+): Excellent repo health, active maintenance, good docs, CI present, tests present
- 80-89 (B/B+): Good health, minor improvements needed
- 70-79 (C/C+): Acceptable but notable gaps (missing tests, stale issues, etc.)
- 60-69 (D): Below average, significant maintenance gaps
- 0-59 (F): Poor health, abandoned or severely undermaintained

Be brutally precise and evidence-based. Do not hallucinate signals. Do not default to a 'C' or 50 if the evidence points to a much higher or lower score."""

    async def analyze(self, input_data: dict) -> dict:
        """Analyze repository health from PR and repo data."""

        repo = input_data.get("repo", {})
        pr = input_data.get("pr", {})

        prompt = f"""Analyze the following repository for operational health:

## Repository Info
- Name: {repo.get('owner', '')}/{repo.get('name', '')}
- Description: {repo.get('description', 'N/A')}
- Language: {repo.get('language', 'N/A')}
- Stars: {repo.get('stars', 0)}
- Forks: {repo.get('forks', 0)}
- Open Issues: {repo.get('open_issues', 0)}
- License: {repo.get('license', 'None')}
- Created: {repo.get('created_at', 'N/A')}
- Last Push: {repo.get('pushed_at', 'N/A')}
- Has CI: {repo.get('has_ci', False)}
- Topics: {', '.join(repo.get('topics', []))}

## README Present: {repo.get('has_readme', False)}
## README Content (truncated):
{repo.get('readme_content', 'No README found')[:2000]}

## Recent Commits:
{json.dumps(repo.get('recent_commits', []), indent=2)[:2000]}

## Current PR Context
- PR #{pr.get('pr_number', 'N/A')}: {pr.get('title', 'N/A')}
- Files Changed: {pr.get('changed_files_count', 0)}
- Additions: {pr.get('additions', 0)}, Deletions: {pr.get('deletions', 0)}

Produce your health assessment."""

        result = await self._llm_analyze(prompt)
        return result

    def _fallback_output(self) -> dict:
        return {
            "reasoning": "Analysis failed — unable to evaluate repository health.",
            "health_score": 50,
            "grade": "C",
            "signals": {
                "readme_quality": "FAIR",
                "commit_frequency": "MODERATE",
                "test_presence": False,
                "stale_branches": 0,
                "open_issues": 0,
                "ci_configured": False,
                "license_present": False,
            },
            "recommendations": ["Unable to fully analyze repository health"],
            "confidence": 0.1,
        }
