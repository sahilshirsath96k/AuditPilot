"""Conditional sequential audit pipeline for AuditPilot."""

from typing import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.events import Event
from google.genai import types

from auditpilot.agents.intake import intake_agent
from auditpilot.agents.anomaly import anomaly_agent
from auditpilot.agents.vendor import vendor_agent
from auditpilot.agents.ratio import ratio_agent
from auditpilot.agents.policy import policy_agent

specialists = ParallelAgent(
    name="specialists",
    description="Runs anomaly, vendor, and financial ratio specialists in parallel.",
    sub_agents=[
        anomaly_agent,
        vendor_agent,
        ratio_agent,
    ],
)

def intake_allows_specialists(profile: dict) -> bool:
    """Return whether intake validation allows specialist execution."""
    status = profile.get("status") if isinstance(profile, dict) else None
    status = getattr(status, "value", status)
    status = str(status).upper() if status else "MISSING"

    return status in {"PASSED", "PASSED_WITH_VARIANCE"}

class SpecialistGateAgent(BaseAgent):
    """Runs specialists only when intake validation succeeds."""


    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state if ctx.session else {}
        profile = state.get("data_profile", {})

        status = profile.get("status") if isinstance(profile, dict) else None
        status = getattr(status, "value", status)
        status = str(status).upper() if status else "MISSING"

        if not intake_allows_specialists(profile):
            message = (
                f"Specialist execution skipped. "
                f"Data intake status: {status}. "
                "Please correct the dataset issues before running the audit."
            )
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=message)],
                ),
            )
            return

        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            branch=ctx.branch,
            content=types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text=(
                            f"Data intake status: {status}. "
                            "Starting the specialist agents."
                        )
                    )
                ],
            ),
        )
        # Run anomaly, vendor, and ratio specialists first.
        async for event in self.sub_agents[0].run_async(ctx):
            yield event

        # Run policy compliance after specialist findings are available.
        async for event in policy_agent.run_async(ctx):
            yield event


specialist_gate = SpecialistGateAgent(
    name="specialist_gate",
    description="Checks intake status before allowing specialist execution.",
    sub_agents=[specialists],
)


audit_lead = SequentialAgent(
    name="audit_lead",
    description="Runs intake validation, parallel specialists, and policy compliance.",
    sub_agents=[
        intake_agent,
        specialist_gate,
    ],
)
