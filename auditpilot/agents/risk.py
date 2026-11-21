"""Deterministic risk ranking agent for AuditPilot."""

from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from auditpilot.schemas import RankedFindings
from auditpilot.tools.risk_tools import build_ranked_findings


class RiskRankingAgent(BaseAgent):
    """Build and validate ranked audit findings without an LLM call."""

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:

        # Calculate findings using deterministic Python audit tools.
        raw_result = build_ranked_findings()

        # Validate the complete result against the Pydantic schema.
        validated_result = RankedFindings.model_validate(raw_result)
        ranked_data = validated_result.model_dump()

        summary = (
            "Risk ranking completed successfully.\n"
            f"- Total findings: {validated_result.total_findings}\n"
            f"- Total amount at risk: "
            f"₹{validated_result.total_amount_at_risk_inr:,.2f}\n"
            "- Risk scores and finding order were calculated deterministically."
        )

        # Save the result using the same state key expected by the pipeline.
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            branch=ctx.branch,
            actions=EventActions(
                state_delta={
                    "ranked_findings": ranked_data,
                }
            ),
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=summary)],
            ),
        )


risk_agent = RiskRankingAgent(
    name="risk_agent",
    description=(
        "Deterministically aggregates audit findings, validates their "
        "structure, and produces a risk-ranked list."
    ),
)
