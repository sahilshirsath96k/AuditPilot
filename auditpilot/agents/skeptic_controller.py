
"""Deterministic controller for applying skeptic reviews."""

from typing import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from auditpilot.tools.skeptic_tools import verify_entry_ids

def apply_skeptic_reviews(
    ranked: dict,
    reviews_data: dict,
    ledger_path: str = "data/ledger.csv",
) -> dict:
    """Apply skeptic decisions while independently verifying entry IDs."""

    if hasattr(ranked, "model_dump"):
        ranked = ranked.model_dump()

    if hasattr(reviews_data, "model_dump"):
        reviews_data = reviews_data.model_dump()

    if not isinstance(ranked, dict) or "findings" not in ranked:
        raise ValueError("Missing or invalid ranked_findings state.")

    if not isinstance(reviews_data, dict):
        reviews_data = {}

    reviews = reviews_data.get("reviews", [])
    review_map = {
        review["finding_id"]: review
        for review in reviews
        if isinstance(review, dict) and review.get("finding_id")
    }

    updated_findings = []

    for original in ranked["findings"]:
        finding = dict(original)
        review = review_map.get(finding["id"])

        verification = verify_entry_ids(
            entry_ids=finding.get("entry_ids", []),
            ledger_path=ledger_path,
        )

        if not verification["is_valid"]:
            status = "dropped"
            reason = (
                "Journal entry ID verification failed: "
                + verification["notes"]
            )

        elif finding.get("status") in {"confirmed", "dropped"}:
            status = finding["status"]
            reason = finding.get("review_reason") or (
                "Decision preserved from an earlier review round."
            )

        elif not review:
            status = "needs_evidence"
            reason = "No skeptic review was returned for this finding."

        elif review.get("status") not in {
            "confirmed", "needs_evidence", "dropped"
        }:
            status = "needs_evidence"
            reason = "The skeptic returned an invalid review status."

        else:
            status = review["status"]
            reason = str(review.get("review_reason", "")).strip()

            if not reason:
                status = "needs_evidence"
                reason = "The skeptic did not provide a review reason."

        finding["status"] = status
        finding["review_reason"] = reason
        updated_findings.append(finding)

    result = dict(ranked)
    result["findings"] = updated_findings

    return result

class SkepticControllerAgent(BaseAgent):
    """Validates and applies skeptic decisions without changing risk calculations."""

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:

        state = ctx.session.state if ctx.session else {}

        ranked = state.get("ranked_findings")
        reviews_data = state.get("skeptic_reviews", {})

        if hasattr(ranked, "model_dump"):
            ranked = ranked.model_dump()

        if hasattr(reviews_data, "model_dump"):
            reviews_data = reviews_data.model_dump()

        if not isinstance(reviews_data, dict):
            reviews_data = {}

        # Apply skeptic decisions and independently verify journal IDs.
        updated_ranked = apply_skeptic_reviews(
            ranked=ranked,
            reviews_data=reviews_data,
            ledger_path=state.get("ledger_path", "data/ledger.csv"),
        )

        findings = updated_ranked["findings"]

        needs_evidence_count = sum(
            item["status"] == "needs_evidence"
            for item in findings
        )

        rounds = int(state.get("skeptic_review_rounds", 0)) + 1

        summary = (
            f"Skeptic review round: {rounds}\n"
            f"Total findings: {len(findings)}\n"
            f"Confirmed: {sum(f['status'] == 'confirmed' for f in findings)}\n"
            f"Needs evidence: {needs_evidence_count}\n"
            f"Dropped: {sum(f['status'] == 'dropped' for f in findings)}"
        )

        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            branch=ctx.branch,
            actions=EventActions(
                state_delta={
                    "ranked_findings": updated_ranked,
                    "skeptic_review_rounds": rounds,
                    "skeptic_review_summary": summary,
                },
                escalate=(needs_evidence_count == 0),
            ),
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=summary)],
            ),
        )

skeptic_controller = SkepticControllerAgent(
    name="skeptic_controller",
    description="Applies and validates skeptic decisions while preserving original risk calculations.",
)
