"""Skeptic agent for independent review of audit findings."""

from google.adk.agents import LlmAgent, LoopAgent

from auditpilot.callbacks import (
    after_tool_audit_logger,
    before_model_guardrail,
)
from auditpilot.models import get_gemini_model
from auditpilot.schemas import SkepticReviewBatch
from auditpilot.agents.skeptic_controller import skeptic_controller


skeptic_agent = LlmAgent(
    name="skeptic_agent",
    model=get_gemini_model(),
    description=(
        "Independently reviews ranked audit findings and "
        "challenges unsupported conclusions."
    ),
    instruction="""
You are the independent skeptic reviewing AuditPilot findings.

Review the findings provided in session state:
{ranked_findings}

Review ONLY findings whose current status is:
- pending
- needs_evidence

Do not review findings already marked confirmed or dropped.

For every active finding, apply these rules:

- confirmed:
  Supplied evidence supports the specific control exception.
- needs_evidence:
  The pattern is suspicious, but additional records are needed.
- dropped:
  The evidence does not support the claim.

Important restrictions:

1. Review every active finding. Do not silently omit any.
2. Never invent evidence, journal IDs, amounts, or policy clauses.
3. Do not change financial amounts, likelihood, impact, or scores.
4. A valid journal ID alone does not prove a finding.
5. Benford results are statistical screening indicators, not proof.
6. Split-payment patterns require approval records to establish
   approval evasion.
7. Return one concise review_reason for every active finding.
8. Preserve each finding_id exactly.
9. Do not return reviews for confirmed or dropped findings.

Return a structured SkepticReviewBatch containing the reviews.
""",
    output_schema=SkepticReviewBatch,
    output_key="skeptic_reviews",
    before_model_callback=[before_model_guardrail],
    after_tool_callback=[after_tool_audit_logger],
)


skeptic_loop = LoopAgent(
    name="skeptic_loop",
    max_iterations=3,
    sub_agents=[
        skeptic_agent,
        skeptic_controller,
    ],
)
