"""Base provider agent — shared CROO provider pattern and LLM integration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base class for all CROO provider agents.

    Provides:
    - LLM analysis with structured JSON output
    - CROO provider lifecycle (connect, listen, accept, deliver)
    """

    AGENT_NAME: str = "base_agent"
    SYSTEM_PROMPT: str = "You are a helpful assistant."

    def __init__(self):
        self.openai = AsyncOpenAI(
            api_key=os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY")),
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        )
        self.model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.croo_key: str = ""
        self.croo_client = None
        self.stream = None

    async def analyze(self, input_data: dict) -> dict:
        """Run LLM analysis on the input data. Override in subclasses for custom prompts."""
        raise NotImplementedError

    async def _llm_analyze(self, user_prompt: str, max_tokens: int = 2000) -> dict:
        """Call OpenAI-compatible LLM and parse structured JSON output.
        
        Includes retry logic for rate-limit (429) errors.
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self.openai.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )

                content = response.choices[0].message.content
                return json.loads(content)

            except json.JSONDecodeError as e:
                logger.error(f"[{self.AGENT_NAME}] Failed to parse LLM JSON: {e}")
                return self._fallback_output()
            except Exception as e:
                error_str = str(e)
                is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str
                
                if is_rate_limit and attempt < max_retries - 1:
                    wait = (attempt + 1) * 5  # 5s, 10s
                    logger.warning(f"[{self.AGENT_NAME}] Rate limited, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait)
                    continue
                
                logger.error(f"[{self.AGENT_NAME}] LLM analysis failed: {e}")
                return self._fallback_output()

    def _fallback_output(self) -> dict:
        """Return a safe fallback output if LLM fails. Override in subclasses."""
        return {"error": "Analysis failed", "confidence": 0.0}

    # ─── CROO Provider Lifecycle ───

    async def start_provider(self, api_key: str):
        """Connect to CROO as a provider agent and listen for orders."""
        try:
            from croo import AgentClient, Config, EventType, Event

            self.croo_key = api_key
            config = Config(
                base_url=os.getenv("CROO_API_URL", "https://api.croo.network"),
                ws_url=os.getenv("CROO_WS_URL", "wss://api.croo.network/ws"),
            )
            self.croo_client = AgentClient(config, api_key)
            self.stream = await self.croo_client.connect_websocket()

            logger.info(f"[{self.AGENT_NAME}] Connected to CROO as provider")

            # Listen for new negotiations
            def on_negotiation(e: Event):
                logger.info(f"[{self.AGENT_NAME}] Negotiation received: {e.negotiation_id}")
                asyncio.create_task(self._handle_negotiation(e.negotiation_id))

            self.stream.on(EventType.NEGOTIATION_CREATED, on_negotiation)

            # Listen for payment (trigger analysis)
            def on_paid(e: Event):
                logger.info(f"[{self.AGENT_NAME}] Order paid: {e.order_id}")
                asyncio.create_task(self._handle_paid_order(e.order_id))

            self.stream.on(EventType.ORDER_PAID, on_paid)

            logger.info(f"[{self.AGENT_NAME}] Listening for orders...")

            # Keep alive
            while True:
                await asyncio.sleep(1)

        except ImportError:
            logger.warning(f"[{self.AGENT_NAME}] croo-sdk not installed, running in local mode")
        except Exception as e:
            logger.error(f"[{self.AGENT_NAME}] Provider startup failed: {e}")

    async def _handle_negotiation(self, negotiation_id: str):
        """Auto-accept all incoming negotiations."""
        try:
            await self.croo_client.accept_negotiation(negotiation_id)
            logger.info(f"[{self.AGENT_NAME}] Accepted negotiation: {negotiation_id}")
        except Exception as e:
            logger.error(f"[{self.AGENT_NAME}] Failed to accept negotiation: {e}")

    async def _handle_paid_order(self, order_id: str):
        """Receive the order input, run analysis, and deliver the result."""
        try:
            # Get order details to extract the input
            order = await self.croo_client.get_order(order_id)

            # Parse the requirements/input from the negotiation
            negotiation = await self.croo_client.get_negotiation(order.negotiation_id)
            input_text = negotiation.requirements or ""

            # If input is JSON, parse it
            try:
                input_data = json.loads(input_text) if input_text else {}
            except json.JSONDecodeError:
                input_data = {"raw_input": input_text}

            # Run analysis
            start = time.time()
            result = await self.analyze(input_data)
            duration_ms = int((time.time() - start) * 1000)

            result["_meta"] = {
                "agent": self.AGENT_NAME,
                "duration_ms": duration_ms,
            }

            # Deliver result
            from croo import DeliverOrderRequest, DeliverableType

            await self.croo_client.deliver_order(
                order_id,
                DeliverOrderRequest(
                    deliverable_type=DeliverableType.SCHEMA,
                    deliverable_schema=json.dumps(result),
                ),
            )
            logger.info(f"[{self.AGENT_NAME}] Delivered order {order_id} in {duration_ms}ms")

        except Exception as e:
            logger.error(f"[{self.AGENT_NAME}] Failed to handle order {order_id}: {e}")
            # Deliver error response to avoid breaking the payment cycle
            try:
                from croo import DeliverOrderRequest, DeliverableType

                await self.croo_client.deliver_order(
                    order_id,
                    DeliverOrderRequest(
                        deliverable_type=DeliverableType.SCHEMA,
                        deliverable_schema=json.dumps(self._fallback_output()),
                    ),
                )
            except Exception:
                pass

    async def stop(self):
        """Clean up CROO connections."""
        if self.stream:
            await self.stream.close()
        if self.croo_client:
            await self.croo_client.close()
        logger.info(f"[{self.AGENT_NAME}] Stopped")
