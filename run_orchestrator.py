"""Start the AI Release Gatekeeper orchestrator + API server."""

import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    print(f"""
╔══════════════════════════════════════════════════════════╗
║         AI Release Gatekeeper — Orchestrator            ║
║     Multi-Agent Release Risk Orchestration Platform     ║
╠══════════════════════════════════════════════════════════╣
║  API:       http://{host}:{port}/api                         ║
║  Dashboard: http://{host}:{port}/                            ║
║  Docs:      http://{host}:{port}/docs                        ║
╚══════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "api.app:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
    )
