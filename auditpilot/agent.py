"""Root audit lead agent and sequential execution pipeline for AuditPilot."""

from google.adk.agents.sequential_agent import SequentialAgent
from auditpilot.agents.intake import intake_agent

# Lead audit pipeline orchestrating sequential agent execution:
# Stage 1: intake_agent (validates dataset structure, verifies balance, and reconciles trial balance)
# Note: Downstream execution gating (halting specialist execution if data_profile is FAILED)
# is a Phase 4 integration responsibility when specialist agents are introduced.
audit_lead = SequentialAgent(
    name="audit_lead",
    description="Lead Audit Pipeline Agent for Sahyadri Precision Components Pvt. Ltd.",
    sub_agents=[intake_agent],
)

# Root agent entry point for ADK Web UI and CLI runners
root_agent = audit_lead
