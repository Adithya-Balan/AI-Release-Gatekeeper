"""PR Describer Agent — classifies and summarizes pull request changes."""

from __future__ import annotations

import json
from agents.base_agent import BaseAgent


class PRDescriberAgent(BaseAgent):

    AGENT_NAME = "pr_describer"

    SYSTEM_PROMPT = """You are a Pull Request Analyst. You transform raw code diffs into structured, semantic descriptions that help engineering teams understand the nature and impact of changes.

Analyze the PR data and produce a structured classification.

You MUST respond with a JSON object matching this exact schema:
{
  "classification": "<feature|bugfix|refactor|security_patch|migration|breaking_change|docs|chore>",
  "title": "<concise descriptive title for this PR>",
  "summary": "<2-3 sentence summary of what this PR does and why>",
  "changes": {
    "files_changed": <integer>,
    "additions": <integer>,
    "deletions": <integer>
  },
  "semantic_tags": ["<tag1>", "<tag2>", "..."],
  "breaking_changes": <boolean>,
  "migration_detected": <boolean>,
  "confidence": <float 0.0-1.0>
}

Classification guidelines:
- feature: New functionality added
- bugfix: Fixing existing broken behavior
- refactor: Code restructuring without behavior change
- security_patch: Security vulnerability fixes
- migration: Database schema or data migration changes
- breaking_change: Changes that break existing API contracts or behavior
- docs: Documentation-only changes
- chore: Build scripts, CI config, dependency updates, formatting

Semantic tags should capture the business/technical domains touched (e.g. "payments", "authentication", "database", "api", "frontend", "testing").

migration_detected should be true if the PR touches migration files, alters database schemas, or modifies ORM models.

Be precise and base your classification on the actual diff content, not just the PR title."""

    async def analyze(self, input_data: dict) -> dict:
        """Classify and summarize the PR."""

        pr = input_data.get("pr", {})
        files = pr.get("files_changed", [])

        files_list = []
        for f in files[:30]:
            files_list.append(f"- {f.get('filename', '')} ({f.get('status', '')}): +{f.get('additions', 0)}, -{f.get('deletions', 0)}")

        prompt = f"""Analyze the following pull request:

## PR #{pr.get('pr_number', 'N/A')}: {pr.get('title', 'N/A')}
## Author: {pr.get('author', 'N/A')}
## Repository: {pr.get('owner', '')}/{pr.get('repo', '')}
## Labels: {', '.join(pr.get('labels', []))}

## PR Description:
{pr.get('body', 'No description provided')[:2000]}

## Stats: +{pr.get('additions', 0)} / -{pr.get('deletions', 0)} across {pr.get('changed_files_count', 0)} files

## Files Changed:
{chr(10).join(files_list)}

## Diff (truncated):
{pr.get('diff', 'No diff available')[:8000]}

Classify this PR and produce your structured analysis."""

        result = await self._llm_analyze(prompt)

        # Ensure change stats match actual GitHub data
        if "changes" not in result:
            result["changes"] = {}
        result["changes"]["files_changed"] = pr.get("changed_files_count", 0)
        result["changes"]["additions"] = pr.get("additions", 0)
        result["changes"]["deletions"] = pr.get("deletions", 0)

        return result

    def _fallback_output(self) -> dict:
        return {
            "classification": "chore",
            "title": "Unable to classify PR",
            "summary": "Analysis failed — unable to classify this pull request.",
            "changes": {"files_changed": 0, "additions": 0, "deletions": 0},
            "semantic_tags": [],
            "breaking_changes": False,
            "migration_detected": False,
            "confidence": 0.1,
        }
