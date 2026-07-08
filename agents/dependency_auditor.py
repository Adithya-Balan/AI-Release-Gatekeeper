"""Dependency Auditor Agent — checks dependency changes for risk."""

from __future__ import annotations

import json
from agents.base_agent import BaseAgent


class DependencyAuditorAgent(BaseAgent):

    AGENT_NAME = "dependency_auditor"

    SYSTEM_PROMPT = """You are an elite Dependency Security Auditor. You deeply analyze dependency changes in pull requests to identify risks from vulnerable, abandoned, or malicious packages.
Do not provide generic or default risk levels. If the PR does not change any dependencies, you MUST return a 'NONE' risk level. If it does, you must list the exact packages added or updated and logically deduce the risk based on the specific version bumps and ecosystem context.

Analyze the PR diff focusing strictly on dependency file changes (package.json, requirements.txt, Pipfile, Gemfile, go.mod, Cargo.toml, pom.xml, build.gradle, etc.).

You MUST respond with a JSON object matching this exact schema:
{
  "reasoning": "<Provide a step-by-step breakdown of your dependency audit. Which files changed? Which packages were added/updated? Explain why the assigned risk level is appropriate based strictly on these specific package changes.>",
  "risk_level": "<CRITICAL|HIGH|MEDIUM|LOW|NONE>",
  "dependencies_changed": <integer>,
  "findings": [
    {
      "package": "<package name>",
      "action": "<ADD|REMOVE|UPDATE>",
      "from_version": "<previous version or empty>",
      "to_version": "<new version or empty>",
      "known_vulnerabilities": <integer, known CVEs if any>,
      "maintenance_status": "<ACTIVE|MAINTAINED|STALE|ABANDONED|UNKNOWN>"
    }
  ],
  "confidence": <float 0.0-1.0>
}

Risk level guidelines:
- CRITICAL: Known critical CVEs in added/updated dependencies, or adding packages known to be malicious
- HIGH: Adding unmaintained/abandoned packages, large version jumps in security-critical packages
- MEDIUM: Adding multiple new dependencies, updating packages with known medium-severity issues
- LOW: Minor version updates to well-maintained packages
- NONE: No dependency changes detected

If no dependency files are changed, return risk_level: "NONE" with empty findings.

Be factual and highly specific. Do not hallucinate dependency changes that aren't in the diff. If you're not sure about a package's vulnerability status, set known_vulnerabilities to 0 and note UNKNOWN maintenance status."""

    async def analyze(self, input_data: dict) -> dict:
        """Audit dependency changes in the PR."""

        pr = input_data.get("pr", {})
        files = pr.get("files_changed", [])

        # Filter for dependency-related files
        dep_patterns = [
            "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
            "requirements.txt", "Pipfile", "Pipfile.lock", "pyproject.toml", "poetry.lock", "setup.py", "setup.cfg",
            "go.mod", "go.sum",
            "Cargo.toml", "Cargo.lock",
            "Gemfile", "Gemfile.lock",
            "pom.xml", "build.gradle", "build.gradle.kts",
            "composer.json", "composer.lock",
        ]

        dep_files = []
        dep_patches = []
        for f in files:
            filename = f.get("filename", "")
            if any(filename.endswith(p) or p in filename for p in dep_patterns):
                dep_files.append(f"- {filename} ({f.get('status', '')}): +{f.get('additions', 0)}, -{f.get('deletions', 0)}")
                patch = f.get("patch", "")
                if patch:
                    dep_patches.append(f"### {filename}\n```\n{patch}\n```")

        if not dep_files:
            # No dependency files changed
            return {
                "reasoning": "No dependency files were modified in this PR.",
                "risk_level": "NONE",
                "dependencies_changed": 0,
                "findings": [],
                "confidence": 0.95,
            }

        prompt = f"""Analyze the following dependency changes in this pull request:

## PR: {pr.get('title', 'N/A')}
## Repository: {pr.get('owner', '')}/{pr.get('repo', '')}

## Dependency Files Changed:
{chr(10).join(dep_files)}

## Dependency File Diffs:
{chr(10).join(dep_patches)[:10000]}

## Full PR Diff (for context):
{pr.get('diff', '')[:3000]}

Identify all dependency additions, removals, and updates. Assess risk for each change.

Produce your dependency audit."""

        result = await self._llm_analyze(prompt)
        return result

    def _fallback_output(self) -> dict:
        return {
            "reasoning": "Analysis failed — unable to audit dependencies.",
            "risk_level": "MEDIUM",
            "dependencies_changed": 0,
            "findings": [],
            "confidence": 0.1,
        }
