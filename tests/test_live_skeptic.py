import asyncio

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from auditpilot.agents.skeptic import skeptic_agent
from auditpilot.schemas import SkepticReviewBatch


async def main():
    session_service = InMemorySessionService()

    ranked_findings = {
        "findings": [
            {
                "id": "TEST-001",
                "category": "duplicate_payment",
                "title": "Potential duplicate vendor payment",
                "entry_ids": ["JE-2025-0001", "JE-2025-0002"],
                "evidence": [
                    "Both entries have the same vendor.",
                    "Both entries have the same amount of ₹25,000.",
                    "Both entries were posted on the same date.",
                ],
                "amount_at_risk_inr": 25000.0,
                "likelihood": 3,
                "impact": 3,
                "score": 9,
                "rationale": "Matching payment details require independent review.",
                "review_reason": None,
                "status": "pending",
            }
        ],
        "total_findings": 1,
        "total_amount_at_risk_inr": 25000.0,
    }

    await session_service.create_session(
        app_name="auditpilot",
        user_id="test_user",
        session_id="skeptic_test",
        state={"ranked_findings": ranked_findings},
    )

    runner = Runner(
        agent=skeptic_agent,
        session_service=session_service,
        app_name="auditpilot",
    )

    async for event in runner.run_async(
        user_id="test_user",
        session_id="skeptic_test",
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text="Review the pending finding.")],
        ),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print("Agent response:", part.text)

    session = await session_service.get_session(
        app_name="auditpilot",
        user_id="test_user",
        session_id="skeptic_test",
    )

    result = session.state.get("skeptic_reviews")

    if result is None:
        raise AssertionError("Skeptic Agent did not save skeptic_reviews.")

    validated = SkepticReviewBatch.model_validate(result)

    print("\nStructured output validation: PASSED")
    print("Reviews returned:", len(validated.reviews))

    for review in validated.reviews:
        print("Finding ID:", review.finding_id)
        print("Status:", review.status)
        print("Reason:", review.review_reason)


if __name__ == "__main__":
    asyncio.run(main())
