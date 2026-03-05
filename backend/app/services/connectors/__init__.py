"""
Connector plugins — Sprints 5 & 6.

Each module exposes:
    async def discover(config: dict) -> list[dict]

Supported platforms:
  Sprint 5 (ERP/CRM): salesforce, servicenow, sap, dynamics365
  Sprint 6 (M365):    m365
"""
from .salesforce import discover as discover_salesforce
from .servicenow import discover as discover_servicenow
from .sap import discover as discover_sap
from .dynamics365 import discover as discover_dynamics365
from .m365 import discover as discover_m365

PLATFORM_MAP = {
    "salesforce":  discover_salesforce,
    "servicenow":  discover_servicenow,
    "sap":         discover_sap,
    "dynamics365": discover_dynamics365,
    "m365":        discover_m365,
}

__all__ = ["PLATFORM_MAP"]
