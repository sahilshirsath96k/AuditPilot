
"""Deterministic request router for AuditPilot."""

from typing import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types

from auditpilot.agents.pipeline import audit_lead


def classify_request(message: str) -> str:
    """Classify a user request without an LLM call."""
    normalized = " ".join(message.strip().lower().split())
    normalized = normalized.rstrip("!?.")

    if normalized in {
        "hi", "hello", "hey",
        "good morning", "good afternoon", "good evening",
    }:
        return "greeting"

    if normalized in {
        "help",
        "what can you do",
        "show help",
        "about auditpilot",
    }:
        return "help"

    # Reject explicit negation before checking audit commands.
    negative_phrases = (
        "don't ",
        "do not ",
        "never ",
        "not ",
        "no ",
    )

    if any(normalized.startswith(phrase) for phrase in negative_phrases):
        return "unknown"

    if normalized in {"approve", "approve memo", "sign off", "sign off memo"}:
        return "sign_off_approve"

    if normalized in {"reject", "reject memo"}:
        return "sign_off_reject"

    if normalized in {"request changes", "request_changes"}:
        return "sign_off_request_changes"

    audit_phrases = {
        "start audit",
        "run audit",
        "run financial checks",
        "perform audit",
        "begin audit",
    }
    if any(
        normalized == phrase or normalized.startswith(phrase + " ")
        for phrase in audit_phrases
    ):
        return "audit"

class RouterAgent(BaseAgent):
    """Routes ordinary messages directly and audit requests to the audit pipeline."""
	
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        message = ""

        if ctx.user_content and ctx.user_content.parts:
            message = " ".join(
                part.text
                for part in ctx.user_content.parts
                if part.text
            )

        request_type = classify_request(message)

        if request_type.startswith("sign_off_"):
            decision = request_type.replace("sign_off_", "").upper()
            from auditpilot.tools.report_tools import sign_off_memo
            res = sign_off_memo(decision=decision, reviewer_name="Audit Partner")
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=res["notes"])],
                ),
            )
            return

        if request_type == "audit":
            async for event in audit_lead.run_async(ctx):
                yield event
            return

        if request_type == "greeting":
            response = (
                "Hello! I'm AuditPilot, your financial forensic audit assistant. "
                "How can I help you today?"
            )
        elif request_type == "help":
            response = (
                "I can help you run financial audit checks on the configured "
                "accounting dataset. Try 'Start audit' to begin the audit intake."
            )
        else:
            response = (
                "I can help with financial audit tasks. "
                "Try 'Start audit' to run the audit intake, or ask 'What can you do?' "
                "to learn about my capabilities."
            )

        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            branch=ctx.branch,
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=response)],
            ),
        )


router_agent = RouterAgent(
    name="request_router",
    description="Routes general conversation and financial audit requests.",
)
