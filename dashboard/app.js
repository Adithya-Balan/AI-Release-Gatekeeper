/**
 * AI Release Gatekeeper — Dashboard Application Logic
 */

const API_BASE = '/api';
let currentAnalysisId = null;
let pollInterval = null;

// ─── DOM Elements ───

const analyzeForm = document.getElementById('analyzeForm');
const prUrlInput = document.getElementById('prUrlInput');
const analyzeBtn = document.getElementById('analyzeBtn');
const btnText = analyzeBtn.querySelector('.btn-text');
const btnLoader = analyzeBtn.querySelector('.btn-loader');

const heroSection = document.getElementById('heroSection');
const progressSection = document.getElementById('progressSection');
const verdictSection = document.getElementById('verdictSection');
const historySection = document.getElementById('historySection');

const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');

// ─── Initialization ───

document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    loadHistory();
    analyzeForm.addEventListener('submit', handleSubmit);
});

// ─── Health Check ───

async function checkHealth() {
    try {
        const resp = await fetch(`${API_BASE}/health`);
        const data = await resp.json();
        statusDot.classList.add('online');
        statusText.textContent = data.mode === 'croo' ? 'CROO Network' : 'Local Mode';
    } catch {
        statusDot.classList.remove('online');
        statusText.textContent = 'Offline';
    }
}

// ─── Submit Analysis ───

async function handleSubmit(e) {
    e.preventDefault();

    const prUrl = prUrlInput.value.trim();
    if (!prUrl) return;

    // Validate URL
    if (!prUrl.match(/github\.com\/[^/]+\/[^/]+\/pull\/\d+/)) {
        shakeInput();
        return;
    }

    setLoading(true);
    showSection('progress');
    resetProgress();

    try {
        const resp = await fetch(`${API_BASE}/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pr_url: prUrl }),
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Analysis submission failed');
        }

        const data = await resp.json();
        currentAnalysisId = data.analysis_id;

        // Start polling
        startPolling(data.analysis_id);

    } catch (err) {
        console.error('Submit error:', err);
        setLoading(false);
        showSection('hero');
        alert(err.message);
    }
}

// ─── Polling ───

function startPolling(analysisId) {
    pollInterval = setInterval(async () => {
        try {
            const resp = await fetch(`${API_BASE}/analysis/${analysisId}`);
            const data = await resp.json();

            updateProgress(data.status);

            if (data.status === 'completed') {
                stopPolling();
                setLoading(false);
                renderVerdict(data.verdict);
                showSection('verdict');
                loadHistory();
            } else if (data.status === 'failed') {
                stopPolling();
                setLoading(false);
                showSection('hero');
                alert('Analysis failed: ' + (data.error || 'Unknown error'));
            }
        } catch (err) {
            console.error('Poll error:', err);
        }
    }, 1500);
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

// ─── Progress ───

function resetProgress() {
    document.querySelectorAll('.stage').forEach(stage => {
        stage.classList.remove('active', 'complete');
        stage.querySelector('.stage-status').textContent = 'Waiting...';
    });
}

function updateProgress(status) {
    const stageOrder = ['fetching', 'analyzing', 'aggregating'];
    const currentIdx = stageOrder.indexOf(status);

    stageOrder.forEach((stageName, idx) => {
        const el = document.querySelector(`.stage[data-stage="${stageName}"]`);
        if (!el) return;

        if (idx < currentIdx) {
            el.classList.remove('active');
            el.classList.add('complete');
            el.querySelector('.stage-status').textContent = 'Complete ✓';
        } else if (idx === currentIdx) {
            el.classList.add('active');
            el.classList.remove('complete');
            el.querySelector('.stage-status').textContent = 'In progress...';
        } else {
            el.classList.remove('active', 'complete');
            el.querySelector('.stage-status').textContent = 'Waiting...';
        }
    });

    // Animate agent pills during analysis
    if (status === 'analyzing') {
        document.querySelectorAll('.agent-pill').forEach((pill, i) => {
            setTimeout(() => pill.classList.add('active'), i * 400);
        });
    }
}

// ─── Verdict Rendering ───

function renderVerdict(verdict) {
    if (!verdict) return;

    // Confidence gauge animation
    const confidence = verdict.deployment_confidence;
    const circumference = 2 * Math.PI * 85;
    const offset = circumference - (confidence / 100) * circumference;
    const gaugeFill = document.getElementById('gaugeFill');
    const gaugeValue = document.getElementById('gaugeValue');

    // Set gauge color based on confidence
    const gaugeColor = getConfidenceColor(confidence);
    gaugeFill.style.stroke = gaugeColor;
    gaugeValue.style.color = gaugeColor;

    // Animate gauge
    requestAnimationFrame(() => {
        gaugeFill.style.strokeDashoffset = offset;
    });

    // Animate counter
    animateCounter(gaugeValue, 0, confidence, 1200);

    // Grade
    const gradeEl = document.getElementById('verdictGrade');
    gradeEl.textContent = verdict.grade;
    gradeEl.style.color = gaugeColor;

    // Recommendation badge
    const recEl = document.getElementById('verdictRecommendation');
    const recText = verdict.ship_recommendation.replace(/_/g, ' ');
    recEl.textContent = recText;
    recEl.className = `verdict-recommendation ${verdict.ship_recommendation}`;

    // Meta values
    document.getElementById('rollbackRisk').textContent =
        `${Math.round(verdict.rollback_probability * 100)}%`;
    document.getElementById('blastRadius').textContent =
        verdict.blast_radius;
    document.getElementById('analysisDuration').textContent =
        `${(verdict.total_duration_ms / 1000).toFixed(1)}s`;

    // Color the rollback risk
    const rollbackEl = document.getElementById('rollbackRisk');
    if (verdict.rollback_probability > 0.5) {
        rollbackEl.style.color = 'var(--accent-rose)';
    } else if (verdict.rollback_probability > 0.25) {
        rollbackEl.style.color = 'var(--accent-amber)';
    } else {
        rollbackEl.style.color = 'var(--accent-emerald)';
    }

    // Alerts
    renderAlerts(verdict);

    // Agent reports
    renderAgentGrid(verdict.agent_reports);

    // Affected areas
    renderAffectedAreas(verdict.affected_areas);

    // Mark agent pills as complete
    document.querySelectorAll('.agent-pill').forEach(pill => {
        pill.classList.remove('active');
        pill.classList.add('complete');
    });
}

function getConfidenceColor(score) {
    if (score >= 85) return 'var(--accent-emerald)';
    if (score >= 65) return 'var(--accent-primary)';
    if (score >= 45) return 'var(--accent-amber)';
    return 'var(--accent-rose)';
}

function animateCounter(el, start, end, duration) {
    const startTime = performance.now();
    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
        const value = Math.round(start + (end - start) * eased);
        el.textContent = value;
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

// ─── Alerts ───

function renderAlerts(verdict) {
    const container = document.getElementById('alertsContainer');
    const blockingBlock = document.getElementById('blockingIssuesBlock');
    const warningsBlock = document.getElementById('warningsBlock');
    const blockingList = document.getElementById('blockingIssuesList');
    const warningsList = document.getElementById('warningsList');

    blockingList.innerHTML = '';
    warningsList.innerHTML = '';

    const hasBlocking = verdict.blocking_issues && verdict.blocking_issues.length > 0;
    const hasWarnings = verdict.warnings && verdict.warnings.length > 0;

    if (hasBlocking) {
        verdict.blocking_issues.forEach(issue => {
            const li = document.createElement('li');
            li.textContent = issue;
            blockingList.appendChild(li);
        });
        blockingBlock.style.display = '';
    } else {
        blockingBlock.style.display = 'none';
    }

    if (hasWarnings) {
        verdict.warnings.forEach(warning => {
            const li = document.createElement('li');
            li.textContent = warning;
            warningsList.appendChild(li);
        });
        warningsBlock.style.display = '';
    } else {
        warningsBlock.style.display = 'none';
    }

    container.style.display = (hasBlocking || hasWarnings) ? '' : 'none';
}

// ─── Agent Grid ───

const AGENT_META = {
    repo_doctor: { icon: '🏥', name: 'Repo Doctor' },
    security_scanner: { icon: '🔒', name: 'Security Scanner' },
    pr_describer: { icon: '📝', name: 'PR Describer' },
    dependency_auditor: { icon: '📦', name: 'Dependency Auditor' },
};

function renderAgentGrid(reports) {
    const grid = document.getElementById('agentGrid');
    grid.innerHTML = '';

    if (!reports) return;

    for (const [name, report] of Object.entries(reports)) {
        const meta = AGENT_META[name] || { icon: '🤖', name };
        const card = createAgentCard(meta, report);
        grid.appendChild(card);
    }
}

function createAgentCard(meta, report) {
    const card = document.createElement('div');
    card.className = 'agent-card';

    const output = report.output || {};
    const isComplete = report.status === 'completed';
    const confidence = output.confidence ?? 0;

    // Extract key stats based on agent type
    const stats = extractAgentStats(meta.name, output);

    card.innerHTML = `
        <div class="agent-card-header">
            <div class="agent-card-name">
                <span class="agent-card-icon">${meta.icon}</span>
                <span>${meta.name}</span>
            </div>
            <span class="agent-card-badge ${isComplete ? 'badge-completed' : 'badge-failed'}">
                ${isComplete ? 'Complete' : 'Failed'}
            </span>
        </div>
        <div class="agent-card-body">
            ${stats.map(s => `
                <div class="agent-stat">
                    <span class="stat-label">${s.label}</span>
                    <span class="stat-value ${s.className || ''}">${s.value}</span>
                </div>
            `).join('')}
            <div class="confidence-bar">
                <div class="confidence-bar-fill" style="width: ${Math.round(confidence * 100)}%; background: ${getConfidenceColor(confidence * 100)};"></div>
            </div>
        </div>
        <div class="agent-card-footer">
            <span>Confidence: ${Math.round(confidence * 100)}%</span>
            <span>${report.duration_ms}ms</span>
        </div>
    `;

    return card;
}

function extractAgentStats(agentName, output) {
    switch (agentName) {
        case 'Repo Doctor':
            return [
                { label: 'Health Score', value: output.health_score ?? '--' },
                { label: 'Grade', value: output.grade ?? '--' },
                { label: 'README', value: output.signals?.readme_quality ?? '--' },
                { label: 'CI Configured', value: output.signals?.ci_configured ? '✓ Yes' : '✗ No' },
                { label: 'Tests Present', value: output.signals?.test_presence ? '✓ Yes' : '✗ No' },
            ];
        case 'Security Scanner':
            return [
                { label: 'Risk Level', value: output.risk_level ?? '--', className: `risk-${output.risk_level || ''}` },
                { label: 'Findings', value: output.findings?.length ?? 0 },
                { label: 'Scan Coverage', value: output.scan_coverage ? `${Math.round(output.scan_coverage * 100)}%` : '--' },
            ];
        case 'PR Describer':
            return [
                { label: 'Classification', value: output.classification ?? '--' },
                { label: 'Breaking Changes', value: output.breaking_changes ? '⚠ Yes' : '✓ No' },
                { label: 'Migration', value: output.migration_detected ? '⚠ Yes' : '✓ No' },
                { label: 'Tags', value: (output.semantic_tags || []).slice(0, 3).join(', ') || '--' },
            ];
        case 'Dependency Auditor':
            return [
                { label: 'Risk Level', value: output.risk_level ?? '--', className: `risk-${output.risk_level || ''}` },
                { label: 'Deps Changed', value: output.dependencies_changed ?? 0 },
                { label: 'Findings', value: output.findings?.length ?? 0 },
            ];
        default:
            return [{ label: 'Status', value: 'Complete' }];
    }
}

// ─── Affected Areas ───

function renderAffectedAreas(areas) {
    const container = document.getElementById('affectedAreas');
    const tagsEl = document.getElementById('areasTags');

    if (!areas || areas.length === 0) {
        container.style.display = 'none';
        return;
    }

    tagsEl.innerHTML = areas.map(area =>
        `<span class="area-tag">${area}</span>`
    ).join('');
    container.style.display = '';
}

// ─── History ───

async function loadHistory() {
    try {
        const resp = await fetch(`${API_BASE}/analyses`);
        const analyses = await resp.json();

        const container = document.getElementById('historyList');
        const title = document.getElementById('historyTitle');

        const completed = analyses.filter(a => a.status === 'completed');

        if (completed.length === 0) {
            container.innerHTML = '';
            title.style.display = 'none';
            return;
        }

        title.style.display = '';
        container.innerHTML = completed.map(a => {
            const v = a.verdict;
            if (!v) return '';
            const color = getConfidenceColor(v.deployment_confidence);
            const recClass = v.ship_recommendation;
            const recText = v.ship_recommendation.replace(/_/g, ' ');
            const shortUrl = a.pr_url.replace('https://github.com/', '');

            return `
                <div class="history-item" onclick="viewAnalysis('${a.analysis_id}')">
                    <div class="history-grade" style="color: ${color}">${v.grade}</div>
                    <div class="history-info">
                        <div class="history-url">${shortUrl}</div>
                        <div class="history-meta">
                            Confidence: ${v.deployment_confidence}% · Rollback: ${Math.round(v.rollback_probability * 100)}% · ${(v.total_duration_ms / 1000).toFixed(1)}s
                        </div>
                    </div>
                    <span class="history-recommendation verdict-recommendation ${recClass}">${recText}</span>
                </div>
            `;
        }).join('');

    } catch (err) {
        console.error('History load error:', err);
    }
}

async function viewAnalysis(analysisId) {
    try {
        const resp = await fetch(`${API_BASE}/analysis/${analysisId}`);
        const data = await resp.json();

        if (data.verdict) {
            renderVerdict(data.verdict);
            showSection('verdict');
        }
    } catch (err) {
        console.error('View analysis error:', err);
    }
}

// ─── UI Helpers ───

function showSection(section) {
    heroSection.style.display = section === 'hero' ? '' : 'none';
    progressSection.style.display = section === 'progress' ? '' : 'none';
    verdictSection.style.display = section === 'verdict' ? '' : 'none';
}

function setLoading(loading) {
    analyzeBtn.disabled = loading;
    btnText.style.display = loading ? 'none' : '';
    btnLoader.style.display = loading ? '' : 'none';
}

function shakeInput() {
    const input = document.querySelector('.input-group');
    input.style.animation = 'shake 0.4s ease';
    setTimeout(() => input.style.animation = '', 400);
}

// Shake animation (injected dynamically)
const shakeStyle = document.createElement('style');
shakeStyle.textContent = `
@keyframes shake {
    0%, 100% { transform: translateX(0); }
    20% { transform: translateX(-8px); }
    40% { transform: translateX(8px); }
    60% { transform: translateX(-4px); }
    80% { transform: translateX(4px); }
}`;
document.head.appendChild(shakeStyle);
