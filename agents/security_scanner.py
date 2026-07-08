"""Security Scanner Agent — scans PR diffs for security vulnerabilities."""

from __future__ import annotations

import json
from agents.base_agent import BaseAgent


class SecurityScannerAgent(BaseAgent):

    AGENT_NAME = "security_scanner"

    SYSTEM_PROMPT = """You are an elite Application Security Analyst specializing in code-level vulnerability detection. You deeply scan pull request diffs for security issues.
Do not provide generic or hallucinated risk levels. If the diff introduces no security issues, you MUST return a 'NONE' risk level with an empty findings array. If there are actual vulnerabilities, you must cite the specific file and line of code.

You MUST respond with a JSON object matching this exact schema:
{
  "reasoning": "<Detailed explanation of your security analysis. Explicitly reference the code changes you reviewed. If no issues exist, state that the diff is benign. Do not output generic boilerplate.>",
  "risk_level": "<CRITICAL|HIGH|MEDIUM|LOW|NONE>",
  "findings": [
    {
      "type": "<finding type, e.g. HARDCODED_SECRET, SQL_INJECTION, XSS, INSECURE_DESERIALIZATION, UNSAFE_EVAL, SENSITIVE_DATA_EXPOSURE, MISSING_AUTH, INSECURE_CRYPTO, PATH_TRAVERSAL, COMMAND_INJECTION>",
      "severity": "<CRITICAL|HIGH|MEDIUM|LOW|INFO>",
      "file": "<filename>",
      "line": <line number or null>,
      "description": "<clear description of the issue and why it is a vulnerability>"
    }
  ],
  "scan_coverage": <float 0.0-1.0, how much of the diff you could meaningfully analyze>,
  "confidence": <float 0.0-1.0>
}

Detection priorities:
1. CRITICAL: Exposed secrets, API keys, tokens, passwords in source code
2. HIGH: SQL injection, command injection, path traversal, insecure deserialization
3. MEDIUM: XSS vulnerabilities, missing input validation, unsafe eval(), insecure randomness
4. LOW: Missing security headers, verbose error messages, debug mode enabled
5. INFO: Best practice suggestions

Be thorough but precise. Only report real findings backed by evidence in the diff. Do NOT hallucinate findings that don't exist in the code. If there are no findings, risk_level MUST be NONE."""

    async def analyze(self, input_data: dict) -> dict:
        """Scan PR diff for security vulnerabilities."""

        pr = input_data.get("pr", {})
        files = pr.get("files_changed", [])

        # Build a focused view of the changes
        files_summary = []
        for f in files[:30]:  # limit to 30 files
            files_summary.append(f"- {f.get('filename', '')} ({f.get('status', '')}): +{f.get('additions', 0)}, -{f.get('deletions', 0)}")

        patches = []
        for f in files[:15]:  # show patches for top 15 files
            patch = f.get("patch", "")
            if patch:
                patches.append(f"### {f.get('filename', '')}\n```\n{patch}\n```")

        prompt = f"""Scan the following pull request for security vulnerabilities:

## PR: {pr.get('title', 'N/A')}
## Repository: {pr.get('owner', '')}/{pr.get('repo', '')}

## Files Changed:
{chr(10).join(files_summary)}

## Diff Content:
{pr.get('diff', 'No diff available')[:8000]}

## File Patches:
{chr(10).join(patches)[:6000]}

Analyze for: hardcoded secrets, injection vulnerabilities, authentication bypasses, insecure data handling, unsafe operations, and other security concerns.

Produce your security assessment."""

        result = await self._llm_analyze(prompt)
        return result

    def _fallback_output(self) -> dict:
        return {
            "reasoning": "Analysis failed — unable to scan for security vulnerabilities.",
            "risk_level": "MEDIUM",
            "findings": [],
            "scan_coverage": 0.1,
            "confidence": 0.1,
        }
