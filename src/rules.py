"""Phase 8: Rules Engine.

Evaluates conditions from deletion_rules.csv and classifies resources into:
- VIOLATION_REMAINING (should be deleted, but still PRESENT)
- VIOLATION_PII (should be redacted/anonymized, but has direct identifiers)
- VIOLATION_ACTIVE_FLOW (flow still active at audit_at)
- VIOLATION_RESTORE_RISK (restore path active at audit_at)
- OK (compliant)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.inventory import Resource


@dataclass
class Violation:
    violation_type: str  # VIOLATION_REMAINING, VIOLATION_PII, VIOLATION_ACTIVE_FLOW, VIOLATION_RESTORE_RISK
    resource: Resource
    required_action: str


class RulesEngine:
    def __init__(self) -> None:
        pass

    def evaluate(self, resources: list[Resource]) -> list[Violation]:
        violations: list[Violation] = []

        for res in resources:
            # Active Data Flows
            if res.is_data_flow:
                if res.state_at_audit_at in ["ACTIVE", "PRESENT"]:
                    violations.append(
                        Violation(
                            violation_type="VIOLATION_ACTIVE_FLOW",
                            resource=res,
                            required_action="DISABLE_DATA_FLOW",
                        )
                    )
                continue

            # Restore Risks
            if res.is_restore_risk:
                if res.state_at_audit_at in ["ACTIVE", "PRESENT"]:
                    violations.append(
                        Violation(
                            violation_type="VIOLATION_RESTORE_RISK",
                            resource=res,
                            required_action="BLOCK_RESTORE",
                        )
                    )
                continue

            # Account Tombstone
            if res.category == "ACCOUNT_TOMBSTONE" or res.system_id == "identity_service":
                # Tombstone rule: user_id permitted, but direct identifiers (email, phone, name) forbidden
                if res.identifiers_remaining or res.state_at_audit_at == "PRESENT" and res.identifiers_remaining:
                    violations.append(
                        Violation(
                            violation_type="VIOLATION_PII",
                            resource=res,
                            required_action="REDACT",
                        )
                    )
                continue

            # Rules requiring DELETE
            delete_categories = [
                "USER_PROFILE",
                "SECONDARY_IDENTIFIER",
                "SEARCH_INDEX_ENTRY",
                "CACHE_ENTRY",
                "SUPPORT_ATTACHMENT",
                "USER_EXPORT",
                "MARKETING_PROFILE",
            ]
            if res.category in delete_categories:
                if res.state_at_audit_at == "PRESENT":
                    violations.append(
                        Violation(
                            violation_type="VIOLATION_REMAINING",
                            resource=res,
                            required_action="DELETE",
                        )
                    )
                continue

            # Rules requiring REDACT (e.g. SUPPORT_MESSAGE)
            if res.category in ["SUPPORT_MESSAGE", "EMAIL_DELIVERY_LOG"]:
                if res.state_at_audit_at == "PRESENT" and res.identifiers_remaining:
                    violations.append(
                        Violation(
                            violation_type="VIOLATION_PII",
                            resource=res,
                            required_action="REDACT",
                        )
                    )
                continue

            # Rules requiring ANONYMIZE (e.g. ANALYTICS_PROFILE)
            if res.category in ["ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"]:
                if res.state_at_audit_at == "PRESENT" and (res.identifiers_remaining or res.state_at_audit_at != "ANONYMIZED"):
                    violations.append(
                        Violation(
                            violation_type="VIOLATION_PII",
                            resource=res,
                            required_action="ANONYMIZE",
                        )
                    )
                continue

        return violations
