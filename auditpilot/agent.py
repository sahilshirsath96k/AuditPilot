"""Root agent entry point for AuditPilot."""

from auditpilot.agents.pipeline import audit_lead
from auditpilot.router import router_agent

root_agent = router_agent
