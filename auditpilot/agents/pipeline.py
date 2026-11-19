
"""Sequential audit pipeline for AuditPilot."""

from google.adk.agents.sequential_agent import SequentialAgent
from auditpilot.agents.intake import intake_agent

audit_lead = SequentialAgent(
    name="audit_lead",
    description="Lead Audit Pipeline Agent for Sahyadri Precision Components Pvt. Ltd.",
    sub_agents=[intake_agent],
)
