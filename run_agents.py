"""Start all CROO provider agents.

Each agent runs as an independent CROO provider, listening for
negotiation requests and delivering analysis results.
"""

import asyncio
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


AGENT_CONFIGS = [
    {
        "name": "Repo Doctor",
        "module": "agents.repo_doctor",
        "class": "RepoDoctorAgent",
        "key_env": "CROO_REPO_DOCTOR_KEY",
    },
    {
        "name": "Security Scanner",
        "module": "agents.security_scanner",
        "class": "SecurityScannerAgent",
        "key_env": "CROO_SECURITY_SCANNER_KEY",
    },
    {
        "name": "PR Describer",
        "module": "agents.pr_describer",
        "class": "PRDescriberAgent",
        "key_env": "CROO_PR_DESCRIBER_KEY",
    },
    {
        "name": "Dependency Auditor",
        "module": "agents.dependency_auditor",
        "class": "DependencyAuditorAgent",
        "key_env": "CROO_DEPENDENCY_AUDITOR_KEY",
    },
]


async def start_agent(config: dict):
    """Start a single agent as a CROO provider."""
    import importlib

    api_key = os.getenv(config["key_env"], "")
    
    if not api_key or not api_key.startswith("croo_sk_"):
        logger.error(f"CRITICAL: Missing valid CROO key for {config['name']}.")
        raise RuntimeError(f"Missing mandatory CROO key for {config['name']}. CAP protocol integration cannot be bypassed for CROO Agent Store.")

    module = importlib.import_module(config["module"])
    agent_class = getattr(module, config["class"])
    agent = agent_class()

    logger.info(f"[{config['name']}] Starting as CROO provider...")
    await agent.start_provider(api_key)


async def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║         AI Release Gatekeeper — Provider Agents         ║
║              CROO Network Provider Agents               ║
╠══════════════════════════════════════════════════════════╣
║  Agents:                                                ║
║    • Repo Doctor                                        ║
║    • Security Scanner                                   ║
║    • PR Describer                                       ║
║    • Dependency Auditor                                 ║
╚══════════════════════════════════════════════════════════╝
    """)

    tasks = [start_agent(cfg) for cfg in AGENT_CONFIGS]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
