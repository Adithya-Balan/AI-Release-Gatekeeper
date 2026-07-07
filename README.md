# AI Release Gatekeeper

### Multi-Agent Release Risk Orchestration Platform

> **"Is this release safe to ship?"**

AI Release Gatekeeper is a production-focused multi-agent orchestration platform built on the [CROO Network](https://croo.network) and powered through CAP (CROO Agent Protocol). Instead of relying on a single AI model or static CI checks, it coordinates **four independently deployed specialized agents** that collaborate, analyze, score, and aggregate release intelligence into a final deployment verdict.

---

## Architecture

```
GitHub PR URL
      ↓
FastAPI Orchestrator (CROO Requester)
      ↓
─────────────────────────────────
  Parallel CAP Agent Execution
─────────────────────────────────
│ 🏥 Repo Doctor Agent          │
│ 🔒 Security Scanner Agent     │
│ 📝 PR Describer Agent         │
│ 📦 Dependency Auditor Agent   │
─────────────────────────────────
      ↓
Verdict Aggregation Engine
      ↓
Final Release Verdict
      ↓
READY / SAFE_WITH_MONITORING / NEEDS_ATTENTION / BLOCK
```

## Quick Start

### 1. Install Dependencies

```bash
cd AI_Release_Gatekeeper
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your keys:
#   - GITHUB_TOKEN (required)
#   - OPENAI_API_KEY (required)
#   - CROO keys (optional — runs in local mode without them)
```

### 3. Run the Orchestrator

```bash
python run_orchestrator.py
```

Open **http://localhost:8000** to access the dashboard.

### 4. (Optional) Run CROO Provider Agents

```bash
# In a separate terminal
python run_agents.py
```

---

## Operating Modes

### Local Mode (Default)
If CROO keys are not configured, agents run **in-process**. All analysis happens locally via OpenAI API. Great for development and demos.

### CROO Mode
With CROO keys configured, the orchestrator uses the **CAP protocol** for real A2A transactions:
- Negotiation → Payment → Delivery → Settlement
- On-chain USDC escrow via CAPVault
- WebSocket-based real-time event streaming

---

## CROO Setup (for CROO Mode)

1. **Register 5 agents** on [agent.croo.network](https://agent.croo.network):
   - 1 Orchestrator (requester)
   - 4 Provider agents (Repo Doctor, Security Scanner, PR Describer, Dependency Auditor)

2. **Configure services** for each provider agent with Schema deliverable type

3. **Deposit USDC** to the orchestrator's AA wallet

4. **Copy API keys and service IDs** into `.env`

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/analyze` | Submit a PR URL for analysis |
| `GET` | `/api/analysis/{id}` | Get analysis results |
| `GET` | `/api/analyses` | List all analyses |
| `GET` | `/api/health` | System health check |

---

## Agent Descriptions

| Agent | Responsibility | Output |
|-------|---------------|--------|
| **Repo Doctor** | Repository operational health | Health score, grade, recommendations |
| **Security Scanner** | Vulnerability detection in diffs | Risk level, findings with severity |
| **PR Describer** | Semantic PR classification | Type, summary, breaking changes, migration detection |
| **Dependency Auditor** | Dependency risk analysis | Risk level, package findings |

---

## Tech Stack

- **Backend**: Python, FastAPI, Uvicorn
- **AI**: OpenAI GPT-4o-mini (structured JSON outputs)
- **Protocol**: CROO Network (CAP — CROO Agent Protocol)
- **Integrations**: GitHub REST API
- **Frontend**: Vanilla HTML/CSS/JS (no framework)

---

## License

MIT
