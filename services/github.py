"""GitHub API integration — fetches PR data and repository metadata."""

from __future__ import annotations

import os
import re
import logging
from typing import Optional

import httpx

from orchestrator.schemas import PRData, RepoData

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    """Extract owner, repo, and PR number from a GitHub PR URL.

    Supports:
        https://github.com/owner/repo/pull/123
    """
    pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.search(pattern, pr_url)
    if not match:
        raise ValueError(f"Invalid GitHub PR URL: {pr_url}")
    return match.group(1), match.group(2), int(match.group(3))


class GitHubService:
    """Lightweight GitHub REST API client."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AI-Release-Gatekeeper",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.client = httpx.AsyncClient(
            base_url=GITHUB_API,
            headers=headers,
            timeout=30.0,
            follow_redirects=True,
        )

    async def close(self):
        await self.client.aclose()

    async def fetch_pr(self, owner: str, repo: str, pr_number: int) -> PRData:
        """Fetch pull request metadata, diff, and changed files."""

        # PR metadata
        resp = await self.client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
        resp.raise_for_status()
        pr = resp.json()

        # PR diff (plain text)
        diff_resp = await self.client.get(
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            headers={"Accept": "application/vnd.github.v3.diff"},
        )
        diff = diff_resp.text if diff_resp.status_code == 200 else ""

        # Truncate very large diffs to avoid LLM context overflow
        max_diff_chars = 15000
        if len(diff) > max_diff_chars:
            diff = diff[:max_diff_chars] + "\n\n... [diff truncated] ..."

        # Changed files
        files_resp = await self.client.get(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
            params={"per_page": 100},
        )
        files = files_resp.json() if files_resp.status_code == 200 else []

        # Simplify file objects for agent consumption
        simplified_files = []
        for f in files:
            simplified_files.append({
                "filename": f.get("filename", ""),
                "status": f.get("status", ""),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "patch": (f.get("patch", "") or "")[:3000],  # truncate large patches
            })

        return PRData(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            title=pr.get("title", ""),
            body=pr.get("body", "") or "",
            state=pr.get("state", "open"),
            author=pr.get("user", {}).get("login", ""),
            created_at=pr.get("created_at", ""),
            updated_at=pr.get("updated_at", ""),
            diff=diff,
            files_changed=simplified_files,
            additions=pr.get("additions", 0),
            deletions=pr.get("deletions", 0),
            changed_files_count=pr.get("changed_files", 0),
            labels=[l.get("name", "") for l in pr.get("labels", [])],
        )

    async def fetch_repo(self, owner: str, repo: str) -> RepoData:
        """Fetch repository metadata including README and recent commits."""

        # Repo metadata
        resp = await self.client.get(f"/repos/{owner}/{repo}")
        resp.raise_for_status()
        data = resp.json()

        # README
        has_readme = False
        readme_content = ""
        readme_resp = await self.client.get(
            f"/repos/{owner}/{repo}/readme",
            headers={"Accept": "application/vnd.github.v3.raw"},
        )
        if readme_resp.status_code == 200:
            has_readme = True
            readme_content = readme_resp.text[:5000]  # truncate

        # Recent commits (last 10)
        commits_resp = await self.client.get(
            f"/repos/{owner}/{repo}/commits",
            params={"per_page": 10},
        )
        recent_commits = []
        if commits_resp.status_code == 200:
            for c in commits_resp.json():
                recent_commits.append({
                    "sha": c.get("sha", "")[:8],
                    "message": (c.get("commit", {}).get("message", "") or "")[:200],
                    "date": c.get("commit", {}).get("committer", {}).get("date", ""),
                    "author": c.get("commit", {}).get("author", {}).get("name", ""),
                })

        # Check for CI config files
        has_ci = False
        ci_paths = [
            ".github/workflows",
            ".circleci/config.yml",
            ".travis.yml",
            "Jenkinsfile",
        ]
        for ci_path in ci_paths:
            ci_resp = await self.client.get(
                f"/repos/{owner}/{repo}/contents/{ci_path}"
            )
            if ci_resp.status_code == 200:
                has_ci = True
                break

        return RepoData(
            owner=owner,
            name=repo,
            description=data.get("description", "") or "",
            stars=data.get("stargazers_count", 0),
            forks=data.get("forks_count", 0),
            open_issues=data.get("open_issues_count", 0),
            has_readme=has_readme,
            readme_content=readme_content,
            default_branch=data.get("default_branch", "main"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            pushed_at=data.get("pushed_at", ""),
            language=data.get("language", "") or "",
            topics=data.get("topics", []),
            has_ci=has_ci,
            license=data.get("license", {}).get("spdx_id", "") if data.get("license") else "",
            recent_commits=recent_commits,
        )

    async def fetch_analysis_input(self, pr_url: str):
        """Parse a PR URL and fetch all data needed for analysis."""
        owner, repo, pr_number = parse_pr_url(pr_url)
        pr_data = await self.fetch_pr(owner, repo, pr_number)
        repo_data = await self.fetch_repo(owner, repo)
        return pr_data, repo_data
