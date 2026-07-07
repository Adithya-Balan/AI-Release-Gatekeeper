"""Verdict Aggregation Engine — computes deployment confidence from agent reports."""

from __future__ import annotations

import logging
from orchestrator.schemas import (
    AgentReport,
    ReleaseVerdict,
    RiskLevel,
    ShipRecommendation,
)

logger = logging.getLogger(__name__)


# Agent weights for confidence scoring
AGENT_WEIGHTS = {
    "security_scanner": 0.35,   # Security is highest priority
    "repo_doctor": 0.20,
    "pr_describer": 0.20,
    "dependency_auditor": 0.25,
}


def score_to_grade(score: int) -> str:
    """Convert a 0-100 score to a letter grade."""
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 85:
        return "B+"
    if score >= 80:
        return "B"
    if score >= 75:
        return "C+"
    if score >= 70:
        return "C"
    if score >= 65:
        return "D+"
    if score >= 60:
        return "D"
    return "F"


def compute_verdict(
    analysis_id: str,
    pr_url: str,
    agent_reports: dict[str, AgentReport],
    total_duration_ms: int,
) -> ReleaseVerdict:
    """Aggregate all agent reports into a final release verdict.

    Algorithm:
    1. Extract risk signals from each agent
    2. Compute weighted deployment confidence
    3. Estimate rollback probability
    4. Determine blast radius
    5. Produce ship recommendation
    """

    blocking_issues: list[str] = []
    warnings: list[str] = []
    affected_areas: list[str] = []

    # Collect agent-level scores
    agent_scores: dict[str, float] = {}

    # ─── Security Scanner ───
    sec_output = _get_output(agent_reports, "security_scanner")
    sec_risk = sec_output.get("risk_level", "MEDIUM")
    sec_findings = sec_output.get("findings", [])
    sec_confidence = sec_output.get("confidence", 0.5)

    sec_score = _risk_to_score(sec_risk)
    agent_scores["security_scanner"] = sec_score * sec_confidence

    # Process security findings
    for finding in sec_findings:
        severity = finding.get("severity", "INFO")
        desc = finding.get("description", "Unknown security issue")
        if severity in ("CRITICAL", "HIGH"):
            blocking_issues.append(f"🔒 {desc}")
        else:
            warnings.append(f"🔒 {desc}")

    # ─── Repo Doctor ───
    repo_output = _get_output(agent_reports, "repo_doctor")
    repo_health = repo_output.get("health_score", 50)
    repo_confidence = repo_output.get("confidence", 0.5)
    repo_recommendations = repo_output.get("recommendations", [])

    agent_scores["repo_doctor"] = repo_health * repo_confidence / 100

    for rec in repo_recommendations:
        warnings.append(f"🏥 {rec}")

    # ─── PR Describer ───
    pr_output = _get_output(agent_reports, "pr_describer")
    pr_classification = pr_output.get("classification", "chore")
    pr_breaking = pr_output.get("breaking_changes", False)
    pr_migration = pr_output.get("migration_detected", False)
    pr_tags = pr_output.get("semantic_tags", [])
    pr_confidence = pr_output.get("confidence", 0.5)

    pr_score = 1.0
    if pr_breaking:
        pr_score -= 0.3
        blocking_issues.append("⚠️ Breaking changes detected")
    if pr_migration:
        pr_score -= 0.15
        warnings.append("🔄 Database migration detected — verify rollback strategy")
    if pr_classification == "security_patch":
        warnings.append("🛡️ Security patch — prioritize review")

    agent_scores["pr_describer"] = pr_score * pr_confidence
    affected_areas.extend(pr_tags)

    # ─── Dependency Auditor ───
    dep_output = _get_output(agent_reports, "dependency_auditor")
    dep_risk = dep_output.get("risk_level", "NONE")
    dep_findings = dep_output.get("findings", [])
    dep_confidence = dep_output.get("confidence", 0.5)

    dep_score = _risk_to_score(dep_risk)
    agent_scores["dependency_auditor"] = dep_score * dep_confidence

    for finding in dep_findings:
        pkg = finding.get("package", "unknown")
        action = finding.get("action", "")
        vulns = finding.get("known_vulnerabilities", 0)
        status = finding.get("maintenance_status", "UNKNOWN")

        if vulns > 0:
            blocking_issues.append(f"📦 {pkg}: {vulns} known vulnerabilities")
        if status in ("ABANDONED", "STALE"):
            warnings.append(f"📦 {pkg}: {status.lower()} maintenance status")

    # ─── Compute Weighted Confidence ───
    weighted_sum = 0.0
    weight_total = 0.0

    for agent_name, weight in AGENT_WEIGHTS.items():
        if agent_name in agent_scores:
            weighted_sum += agent_scores[agent_name] * weight
            weight_total += weight

    # Normalize to 0-100
    if weight_total > 0:
        deployment_confidence = int((weighted_sum / weight_total) * 100)
    else:
        deployment_confidence = 50  # no data = uncertain

    # Clamp
    deployment_confidence = max(0, min(100, deployment_confidence))

    # ─── Rollback Probability ───
    rollback_probability = _estimate_rollback_probability(
        deployment_confidence, pr_breaking, pr_migration, sec_risk, dep_risk
    )

    # ─── Blast Radius ───
    blast_radius = _estimate_blast_radius(affected_areas, pr_breaking, pr_migration)

    # ─── Ship Recommendation ───
    ship_recommendation = _determine_ship_recommendation(
        deployment_confidence, blocking_issues, rollback_probability
    )

    grade = score_to_grade(deployment_confidence)

    return ReleaseVerdict(
        analysis_id=analysis_id,
        pr_url=pr_url,
        deployment_confidence=deployment_confidence,
        grade=grade,
        ship_recommendation=ship_recommendation,
        rollback_probability=round(rollback_probability, 2),
        blast_radius=blast_radius,
        affected_areas=list(set(affected_areas)),
        blocking_issues=blocking_issues,
        warnings=warnings,
        agent_reports={
            name: report for name, report in agent_reports.items()
        },
        total_duration_ms=total_duration_ms,
    )


def _get_output(reports: dict[str, AgentReport], agent_name: str) -> dict:
    """Safely extract agent output."""
    report = reports.get(agent_name)
    if report and report.status == "completed":
        return report.output
    return {}


def _risk_to_score(risk_level: str) -> float:
    """Convert risk level string to a 0-1 score (higher = safer)."""
    mapping = {
        "NONE": 1.0,
        "LOW": 0.85,
        "MEDIUM": 0.65,
        "HIGH": 0.35,
        "CRITICAL": 0.1,
    }
    return mapping.get(risk_level, 0.5)


def _estimate_rollback_probability(
    confidence: int,
    breaking: bool,
    migration: bool,
    sec_risk: str,
    dep_risk: str,
) -> float:
    """Estimate the probability that this release will need a rollback."""
    base = 1.0 - (confidence / 100.0)

    if breaking:
        base += 0.15
    if migration:
        base += 0.10
    if sec_risk in ("CRITICAL", "HIGH"):
        base += 0.10
    if dep_risk in ("CRITICAL", "HIGH"):
        base += 0.05

    return min(1.0, max(0.0, base))


def _estimate_blast_radius(
    affected_areas: list[str],
    breaking: bool,
    migration: bool,
) -> RiskLevel:
    """Estimate how much of the system may be affected."""
    critical_areas = {
        "authentication", "auth", "payments", "payment", "billing",
        "database", "db", "security", "encryption", "api",
        "infrastructure", "deployment", "core",
    }

    touched_critical = sum(
        1 for area in affected_areas
        if area.lower() in critical_areas
    )

    if breaking and touched_critical >= 2:
        return RiskLevel.CRITICAL
    if breaking or (migration and touched_critical >= 1):
        return RiskLevel.HIGH
    if touched_critical >= 1 or migration:
        return RiskLevel.MEDIUM
    if len(affected_areas) > 3:
        return RiskLevel.LOW
    return RiskLevel.NONE


def _determine_ship_recommendation(
    confidence: int,
    blocking_issues: list[str],
    rollback_probability: float,
) -> ShipRecommendation:
    """Determine the final ship recommendation."""
    if blocking_issues:
        if confidence < 50:
            return ShipRecommendation.BLOCK
        return ShipRecommendation.NEEDS_ATTENTION

    if confidence >= 85 and rollback_probability < 0.15:
        return ShipRecommendation.READY
    if confidence >= 65:
        return ShipRecommendation.SAFE_WITH_MONITORING
    if confidence >= 45:
        return ShipRecommendation.NEEDS_ATTENTION

    return ShipRecommendation.BLOCK
