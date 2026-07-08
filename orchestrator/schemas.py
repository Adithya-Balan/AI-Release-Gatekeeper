"""Pydantic models for all agent inputs and outputs."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─── Enums ───


class RiskLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class ShipRecommendation(str, Enum):
    READY = "READY"
    SAFE_WITH_MONITORING = "SAFE_WITH_MONITORING"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    BLOCK = "BLOCK"


class PRClassification(str, Enum):
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    SECURITY_PATCH = "security_patch"
    MIGRATION = "migration"
    BREAKING_CHANGE = "breaking_change"
    DOCS = "docs"
    CHORE = "chore"


class ReadmeQuality(str, Enum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    MISSING = "MISSING"


class CommitFrequency(str, Enum):
    VERY_ACTIVE = "VERY_ACTIVE"
    ACTIVE = "ACTIVE"
    MODERATE = "MODERATE"
    LOW = "LOW"
    INACTIVE = "INACTIVE"


class FindingSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class DependencyAction(str, Enum):
    ADD = "ADD"
    REMOVE = "REMOVE"
    UPDATE = "UPDATE"


class MaintenanceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MAINTAINED = "MAINTAINED"
    STALE = "STALE"
    ABANDONED = "ABANDONED"
    UNKNOWN = "UNKNOWN"


# ─── GitHub Data Models ───


class PRData(BaseModel):
    """Raw PR data fetched from GitHub."""

    owner: str
    repo: str
    pr_number: int
    title: str
    body: str = ""
    state: str = "open"
    author: str = ""
    created_at: str = ""
    updated_at: str = ""
    diff: str = ""
    files_changed: list[dict] = Field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    changed_files_count: int = 0
    labels: list[str] = Field(default_factory=list)


class RepoData(BaseModel):
    """Raw repository data fetched from GitHub."""

    owner: str
    name: str
    description: str = ""
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    has_readme: bool = False
    readme_content: str = ""
    default_branch: str = "main"
    created_at: str = ""
    updated_at: str = ""
    pushed_at: str = ""
    language: str = ""
    topics: list[str] = Field(default_factory=list)
    has_ci: bool = False
    license: str = ""
    recent_commits: list[dict] = Field(default_factory=list)


class AnalysisInput(BaseModel):
    """Combined input sent to each agent for analysis."""

    pr: PRData
    repo: RepoData


# ─── Agent Output Schemas ───


class RepoHealthSignals(BaseModel):
    readme_quality: ReadmeQuality = ReadmeQuality.FAIR
    commit_frequency: CommitFrequency = CommitFrequency.MODERATE
    test_presence: bool = False
    stale_branches: int = 0
    open_issues: int = 0
    ci_configured: bool = False
    license_present: bool = False


class RepoDoctorOutput(BaseModel):
    """Output from the Repo Doctor agent."""

    reasoning: str = Field(description="Step-by-step reasoning for the assigned score based on specific repository signals.")
    health_score: int = Field(ge=0, le=100)
    grade: str = Field(pattern=r"^[A-F][+-]?$")
    signals: RepoHealthSignals
    recommendations: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class SecurityFinding(BaseModel):
    type: str
    severity: FindingSeverity
    file: str = ""
    line: Optional[int] = None
    description: str


class SecurityScannerOutput(BaseModel):
    """Output from the Security Scanner agent."""

    reasoning: str = Field(description="Detailed explanation of why the risk level was chosen and analysis of specific code changes.")
    risk_level: RiskLevel
    findings: list[SecurityFinding] = Field(default_factory=list)
    scan_coverage: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)


class PRChangeStats(BaseModel):
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0


class PRDescriberOutput(BaseModel):
    """Output from the PR Describer agent."""

    reasoning: str = Field(description="Explanation of the classification and any breaking changes or migrations detected.")
    classification: PRClassification
    title: str
    summary: str
    changes: PRChangeStats
    semantic_tags: list[str] = Field(default_factory=list)
    breaking_changes: bool = False
    migration_detected: bool = False
    confidence: float = Field(ge=0.0, le=1.0)


class DependencyFinding(BaseModel):
    package: str
    action: DependencyAction
    from_version: str = ""
    to_version: str = ""
    known_vulnerabilities: int = 0
    maintenance_status: MaintenanceStatus = MaintenanceStatus.UNKNOWN


class DependencyAuditorOutput(BaseModel):
    """Output from the Dependency Auditor agent."""

    reasoning: str = Field(description="Explanation of dependency risk analysis based on the specific packages modified.")
    risk_level: RiskLevel
    dependencies_changed: int = 0
    findings: list[DependencyFinding] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


# ─── Verdict / Aggregation ───


class AgentReport(BaseModel):
    agent_name: str
    status: str = "completed"
    duration_ms: int = 0
    output: dict = Field(default_factory=dict)
    error: Optional[str] = None


class ReleaseVerdict(BaseModel):
    """Final aggregated release verdict."""

    analysis_id: str
    pr_url: str
    deployment_confidence: int = Field(ge=0, le=100)
    grade: str
    ship_recommendation: ShipRecommendation
    rollback_probability: float = Field(ge=0.0, le=1.0)
    blast_radius: RiskLevel
    affected_areas: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    agent_reports: dict[str, AgentReport] = Field(default_factory=dict)
    timestamp: str = ""
    total_duration_ms: int = 0


# ─── API Models ───


class AnalyzeRequest(BaseModel):
    pr_url: str = Field(description="Full GitHub PR URL, e.g. https://github.com/owner/repo/pull/123")


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    FETCHING = "fetching"
    ANALYZING = "analyzing"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisResponse(BaseModel):
    analysis_id: str
    status: AnalysisStatus
    pr_url: str
    verdict: Optional[ReleaseVerdict] = None
    error: Optional[str] = None
    created_at: str = ""
