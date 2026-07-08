# 🛡️ AI Release Gatekeeper

**The Multi-Agent Release Risk Orchestration Platform**

> *"Is this release safe to ship?"*

**AI Release Gatekeeper** is a production-focused multi-agent orchestration platform built on the **[CROO Network](https://croo.network)** and powered by **CAP (CROO Agent Protocol)**. Instead of relying on a single AI model or static CI checks, it coordinates **four independently deployed specialized agents** that collaborate, negotiate, analyze, score, and aggregate release intelligence into a final deployment verdict.

This project was built for the **CROO Agent Hackathon**, specifically targeting the **Developer Tooling Agents** and **Open – Any A2A Agents** tracks.

---

## Highlights:

### 1. A2A Composability at Scale
This isn't a simple chatbot. AI Release Gatekeeper proves the power of **Agent-to-Agent (A2A) composability**. 
- **1 Requester Agent** (The Orchestrator) automatically hires **4 distinct Provider Agents** (Repo Doctor, Security Scanner, PR Describer, Dependency Auditor).
- Each provider agent is a completely isolated service, hired dynamically via CAP to perform a specialized intelligence task.

### 2. Deep CAP & On-Chain Commerce Integration
The Orchestrator uses the official `croo-sdk` to execute real financial transactions for intelligence.
- **Negotiation:** The orchestrator discovers and negotiates pricing with each of the 4 agents.
- **Escrow:** USDC is locked on-chain via CAPVault for each task.
- **Delivery:** The agents run their respective LLM-powered analyses and deliver structured JSON schema outputs back to the orchestrator.
- **Settlement:** The orchestrator aggregates the intelligence into a final deployment confidence score and settles the USDC payments.

### 3. Real Operational Utility
It solves a massive engineering pain point: passing CI tests doesn't mean a release is safe. By computing **Rollback Probability**, **Blast Radius**, and a **Deployment Confidence Score**, this platform serves as actual Release Intelligence Infrastructure, not just a toy.

---

## 🏗️ Architecture

```text
GitHub PR URL
      ↓
FastAPI Orchestrator (CROO Requester)
      ↓
─────────────────────────────────
  Parallel CAP Agent Execution (A2A)
─────────────────────────────────
│ 🏥 Repo Doctor Agent          │
│ 🔒 Security Scanner Agent     │
│ 📝 PR Describer Agent         │
│ 📦 Dependency Auditor Agent   │
─────────────────────────────────
      ↓
Verdict Aggregation Engine (JSON Delivery)
      ↓
Final Release Verdict
      ↓
READY / SAFE_WITH_MONITORING / NEEDS_ATTENTION / BLOCK
```

---

## 💻 CROO SDK Methods Used

The platform deeply integrates with the `croo-sdk`. Key methods utilized across the Orchestrator and Agents include:

**Requester (Orchestrator):**
- `AgentClient.negotiate_order()`: Initiates hiring of the 4 sub-agents.
- `AgentClient.pay_order()`: Locks USDC on-chain for the tasks.
- `AgentClient.get_delivery()`: Retrieves the structured JSON schemas once agents finish.
- WebSocket Event Listeners: Listens for `ORDER_CREATED` and `ORDER_COMPLETED` to maintain parallel execution state.

**Providers (Specialized Agents):**
- `AgentClient.accept_negotiation()`: Automatically accepts incoming jobs.
- `AgentClient.get_order()` & `get_negotiation()`: Extracts the PR data requirements.
- `AgentClient.deliver_order()`: Returns the completed AI analysis wrapped in a `DeliverableType.SCHEMA`.
- WebSocket Event Listeners: Listens for `NEGOTIATION_CREATED` and `ORDER_PAID`.

---

## 🚀 Quick Start (Local & CROO Modes)

The system is built to fallback gracefully to **Local Mode** for easy testing without deploying 5 agents to the CROO dashboard, but natively supports **CROO Mode** for full A2A commerce.

### 1. Install Dependencies
```bash
git clone https://github.com/your-username/AI_Release_Gatekeeper.git
cd AI_Release_Gatekeeper
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
```
Edit `.env` and add:
- `GITHUB_TOKEN`: A read-only classic token (required to fetch PR diffs).
- `LLM_API_KEY`: Your Groq or OpenAI API key.
- *For CROO Mode:* Add your `CROO_ORCHESTRATOR_KEY` and the 4 `SERVICE_ID`s from the CROO dashboard.

### 3. Run the Platform
```bash
python run_orchestrator.py
```
Open **http://localhost:8000** to access the premium, hackathon-ready dashboard!

### 4. (Optional) Run CROO Provider Agents
If running in full CROO mode, start the provider agents in a separate terminal to listen for orders:
```bash
python run_agents.py
```

---

## 🤖 The Agents

| Agent | Responsibility | CAP Output Delivery |
|-------|---------------|--------|
| **Repo Doctor** | Repository operational health | Health score, grade, recommendations |
| **Security Scanner** | Vulnerability detection in diffs | Risk level, findings with severity |
| **PR Describer** | Semantic PR classification | Type, summary, breaking changes, migration detection |
| **Dependency Auditor** | Dependency risk analysis | Risk level, package findings |

---

## 📄 License
This project is open-source and licensed under the **MIT License**.
