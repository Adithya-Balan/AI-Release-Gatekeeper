"""Debug script — tests the full analysis pipeline and shows raw data at each stage."""

import asyncio
import json
import os
import sys

from dotenv import load_dotenv
load_dotenv()

async def main():
    pr_url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/fastapi/fastapi/pull/13672"

    print("=" * 70)
    print("  AI Release Gatekeeper — Debug Analysis")
    print("=" * 70)

    # ─── Step 1: Check env vars ───
    print("\n📋 Environment Check:")
    gh_token = os.getenv("GITHUB_TOKEN", "")
    llm_key = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    llm_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    print(f"  GITHUB_TOKEN: {'✅ Set (' + gh_token[:8] + '...)' if gh_token else '❌ MISSING'}")
    print(f"  LLM_API_KEY:  {'✅ Set (' + llm_key[:8] + '...)' if llm_key else '❌ MISSING'}")
    print(f"  LLM_BASE_URL: {llm_url}")
    print(f"  LLM_MODEL:    {llm_model}")

    # ─── Step 2: Fetch GitHub data ───
    print(f"\n📡 Fetching data for: {pr_url}")
    from services.github import GitHubService
    github = GitHubService()
    try:
        pr_data, repo_data = await github.fetch_analysis_input(pr_url)
    finally:
        await github.close()

    print(f"\n  PR: {pr_data.owner}/{pr_data.repo}#{pr_data.pr_number}")
    print(f"  Title: {pr_data.title}")
    print(f"  Author: {pr_data.author}")
    print(f"  Files changed: {pr_data.changed_files_count}")
    print(f"  Additions: +{pr_data.additions}, Deletions: -{pr_data.deletions}")
    print(f"  Diff length: {len(pr_data.diff)} chars")
    print(f"  Files list: {len(pr_data.files_changed)} files")
    for f in pr_data.files_changed[:5]:
        print(f"    - {f.get('filename')} ({f.get('status')}): +{f.get('additions', 0)} -{f.get('deletions', 0)}, patch={len(f.get('patch', ''))} chars")
    if len(pr_data.files_changed) > 5:
        print(f"    ... and {len(pr_data.files_changed) - 5} more files")

    print(f"\n  Repo: {repo_data.owner}/{repo_data.name}")
    print(f"  Description: {repo_data.description[:100]}")
    print(f"  Stars: {repo_data.stars}, Forks: {repo_data.forks}")
    print(f"  Language: {repo_data.language}")
    print(f"  Has CI: {repo_data.has_ci}")
    print(f"  Has README: {repo_data.has_readme} ({len(repo_data.readme_content)} chars)")
    print(f"  License: {repo_data.license}")
    print(f"  Recent commits: {len(repo_data.recent_commits)}")

    # ─── Step 3: Test one agent directly ───
    print("\n" + "=" * 70)
    print("🤖 Testing Security Scanner Agent directly...")
    print("=" * 70)

    from orchestrator.schemas import AnalysisInput
    input_data = AnalysisInput(pr=pr_data, repo=repo_data).model_dump()

    from agents.security_scanner import SecurityScannerAgent
    agent = SecurityScannerAgent()

    result = await agent.analyze(input_data)

    print(f"\n  Raw LLM output:")
    print(json.dumps(result, indent=2, default=str)[:3000])

    # ─── Step 4: Test Repo Doctor ───
    print("\n" + "=" * 70)
    print("🏥 Testing Repo Doctor Agent directly...")
    print("=" * 70)

    from agents.repo_doctor import RepoDoctorAgent
    agent2 = RepoDoctorAgent()
    result2 = await agent2.analyze(input_data)

    print(f"\n  Raw LLM output:")
    print(json.dumps(result2, indent=2, default=str)[:3000])

    print("\n✅ Debug complete.")

if __name__ == "__main__":
    asyncio.run(main())
