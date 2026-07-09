"""Orchestrator — CROO requester that fans out analysis to provider agents."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Optional

from orchestrator.schemas import (
    AnalysisInput,
    AgentReport,
    PRData,
    RepoData,
)

logger = logging.getLogger(__name__)


# Agent service configuration
AGENT_SERVICES = {
    "repo_doctor": {
        "key_env": "CROO_ORCHESTRATOR_KEY",
        "service_id_env": "CROO_REPO_DOCTOR_SERVICE_ID",
    },
    "security_scanner": {
        "key_env": "CROO_ORCHESTRATOR_KEY",
        "service_id_env": "CROO_SECURITY_SCANNER_SERVICE_ID",
    },
    "pr_describer": {
        "key_env": "CROO_ORCHESTRATOR_KEY",
        "service_id_env": "CROO_PR_DESCRIBER_SERVICE_ID",
    },
    "dependency_auditor": {
        "key_env": "CROO_ORCHESTRATOR_KEY",
        "service_id_env": "CROO_DEPENDENCY_AUDITOR_SERVICE_ID",
    },
}


class OrchestratorClient:
    """CROO Requester that coordinates multi-agent analysis.

    In CROO mode: Negotiates, pays, and collects deliveries from on-chain agents.
    In local mode: Runs agents directly in-process (for development/demo).
    """

    def __init__(self):
        self.use_croo = self._check_croo_config()
        self.croo_client = None
        self.stream = None

        # Local agent instances (used when CROO is not configured)
        self._local_agents = {}

    def _check_croo_config(self) -> bool:
        """Check if CROO credentials are configured and respect environment modes."""
        app_env = os.getenv("APP_ENV", "development").lower()
        
        # In development mode, we can bypass CROO integration if keys are missing or BYPASS_CAP is true
        if app_env == "development":
            bypass = os.getenv("BYPASS_CAP", "false").lower() == "true"
            key = os.getenv("CROO_ORCHESTRATOR_KEY", "")
            has_services = any(
                os.getenv(cfg["service_id_env"], "")
                for cfg in AGENT_SERVICES.values()
            )
            use_croo = bool(key and key.startswith("croo_sk_") and has_services) and not bypass
            if not use_croo:
                logger.warning("Running in DEVELOPMENT mode: Bypassing CAP integration (local execution).")
            return use_croo
            
        # In production mode, CROO integration is STRICTLY mandatory
        elif app_env == "production":
            key = os.getenv("CROO_ORCHESTRATOR_KEY", "")
            if not key or not key.startswith("croo_sk_"):
                logger.error("CRITICAL: CROO_ORCHESTRATOR_KEY is missing or invalid in PRODUCTION mode.")
                raise RuntimeError("CAP Protocol integration is MANDATORY in production.")
                
            for agent, cfg in AGENT_SERVICES.items():
                if not os.getenv(cfg["service_id_env"]):
                    logger.error(f"CRITICAL: Missing service ID for {agent} in PRODUCTION mode.")
                    raise RuntimeError(f"Missing mandatory CAP service ID for {agent}")
                    
            logger.info("Running in PRODUCTION mode: CAP Protocol enforced.")
            return True
            
        else:
            raise ValueError(f"Unknown APP_ENV: {app_env}. Use 'development' or 'production'.")

    async def initialize(self):
        """Initialize the orchestrator — either CROO or local mode."""
        if self.use_croo:
            await self._init_croo()
        else:
            await self._init_local()

    async def _init_croo(self):
        """Connect to CROO as a requester agent."""
        try:
            from croo import AgentClient, Config

            config = Config(
                base_url=os.getenv("CROO_API_URL", "https://api.croo.network"),
                ws_url=os.getenv("CROO_WS_URL", "wss://api.croo.network/ws"),
            )
            api_key = os.getenv("CROO_ORCHESTRATOR_KEY", "")
            self.croo_client = AgentClient(config, api_key)
            self.stream = await self.croo_client.connect_websocket()
            logger.info("Orchestrator connected to CROO Network")
        except Exception as e:
            if os.getenv("APP_ENV", "development").lower() == "production":
                logger.error(f"CRITICAL: CROO initialization failed in production: {e}")
                raise RuntimeError(f"CAP initialization failed in production: {e}")
            logger.warning(f"CROO initialization failed, falling back to local mode: {e}")
            self.use_croo = False
            await self._init_local()

    async def _init_local(self):
        """Initialize local agent instances for development."""
        from agents.repo_doctor import RepoDoctorAgent
        from agents.security_scanner import SecurityScannerAgent
        from agents.pr_describer import PRDescriberAgent
        from agents.dependency_auditor import DependencyAuditorAgent

        self._local_agents = {
            "repo_doctor": RepoDoctorAgent(),
            "security_scanner": SecurityScannerAgent(),
            "pr_describer": PRDescriberAgent(),
            "dependency_auditor": DependencyAuditorAgent(),
        }
        logger.info("Orchestrator running in LOCAL mode (no CROO)")

    async def run_analysis(self, pr_data: PRData, repo_data: RepoData) -> dict[str, AgentReport]:
        """Fan out analysis to all agents and collect results.

        Returns a dict of agent_name -> AgentReport.
        """
        input_data = AnalysisInput(pr=pr_data, repo=repo_data).model_dump()

        if self.use_croo:
            return await self._run_croo_analysis(input_data)
        else:
            return await self._run_local_analysis(input_data)

    async def _run_croo_analysis(self, input_data: dict) -> dict[str, AgentReport]:
        """Execute analysis through CROO protocol orders."""
        reports = {}
        tasks = []

        for agent_name, config in AGENT_SERVICES.items():
            service_id = os.getenv(config["service_id_env"], "")
            if service_id:
                tasks.append(
                    self._execute_croo_order(agent_name, service_id, input_data)
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"CROO order failed: {result}")
                continue
            if isinstance(result, AgentReport):
                reports[result.agent_name] = result

        return reports

    async def _execute_croo_order(
        self, agent_name: str, service_id: str, input_data: dict
    ) -> AgentReport:
        """Execute a single CROO order: negotiate → pay → wait for delivery → get result."""
        start = time.time()

        try:
            from croo import EventType

            from croo import NegotiateOrderRequest

            # Step 1: Negotiate
            negotiation = await self.croo_client.negotiate_order(
                NegotiateOrderRequest(
                    service_id=service_id,
                    requirements=json.dumps(input_data),
                )
            )
            negotiation_id = negotiation.negotiation_id
            logger.info(f"[{agent_name}] Negotiation initiated: {negotiation_id}")

            # Step 2: Wait for order_created event (provider accepts)
            order_id = await self._wait_for_event(
                EventType.ORDER_CREATED, negotiation_id, timeout=60
            )
            logger.info(f"[{agent_name}] Order created: {order_id}")

            # Step 3: Pay
            await self.croo_client.pay_order(order_id)
            logger.info(f"[{agent_name}] Order paid: {order_id}")

            # Step 4: Wait for order_completed event
            await self._wait_for_event(
                EventType.ORDER_COMPLETED, order_id, timeout=120
            )
            logger.info(f"[{agent_name}] Order completed: {order_id}")

            # Step 5: Get delivery
            delivery = await self.croo_client.get_delivery(order_id)
            try:
                output = json.loads(delivery.deliverable_schema) if delivery.deliverable_schema else {}
            except json.JSONDecodeError:
                output = {}

            duration_ms = int((time.time() - start) * 1000)

            return AgentReport(
                agent_name=agent_name,
                status="completed",
                duration_ms=duration_ms,
                output=output,
            )

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.error(f"[{agent_name}] CROO order failed: {e}")
            return AgentReport(
                agent_name=agent_name,
                status="failed",
                duration_ms=duration_ms,
                output={},
                error=str(e),
            )

    async def _wait_for_event(self, event_type, reference_id: str, timeout: int = 60) -> str:
        """Wait for a specific CROO WebSocket event with timeout."""
        event_future = asyncio.get_event_loop().create_future()

        def on_event(e):
            if not event_future.done():
                # Return the order_id from the event
                event_future.set_result(getattr(e, "order_id", reference_id))

        self.stream.on(event_type, on_event)

        try:
            result = await asyncio.wait_for(event_future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timeout waiting for {event_type} (ref: {reference_id})")

    async def _run_local_analysis(self, input_data: dict) -> dict[str, AgentReport]:
        """Execute analysis locally (no CROO). Runs agents sequentially to respect rate limits."""
        reports = {}

        for name, agent in self._local_agents.items():
            start = time.time()
            try:
                result = await agent.analyze(input_data)
                duration_ms = int((time.time() - start) * 1000)
                reports[name] = AgentReport(
                    agent_name=name,
                    status="completed",
                    duration_ms=duration_ms,
                    output=result,
                )
            except Exception as e:
                duration_ms = int((time.time() - start) * 1000)
                logger.error(f"[{name}] Local analysis failed: {e}")
                reports[name] = AgentReport(
                    agent_name=name,
                    status="failed",
                    duration_ms=duration_ms,
                    output=agent._fallback_output(),
                    error=str(e),
                )

        return reports

    async def close(self):
        """Clean up connections."""
        if self.stream:
            await self.stream.close()
        if self.croo_client:
            await self.croo_client.close()
        logger.info("Orchestrator shut down")
