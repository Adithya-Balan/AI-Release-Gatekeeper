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
        self.use_croo = False
        self.croo_client = None
        self.stream = None

        # Local agent instances for web application
        self._local_agents = {}

    async def initialize(self):
        """Initialize local agent instances for web application bypass."""
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
        logger.info("Web Application Mode: Bypassing CAP and running local analysis.")

    async def run_analysis(self, pr_data: PRData, repo_data: RepoData) -> dict[str, AgentReport]:
        """Run analysis completely locally for the web application."""
        input_data = AnalysisInput(pr=pr_data, repo=repo_data).model_dump()
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
