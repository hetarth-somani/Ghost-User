"""Phase 10: Step Generation.

Deterministic step generator for steps_json.
Orders steps strictly:
1. Phase: FINDING -> REMEDIATION -> VERIFICATION
2. Within Phase: Operation order (per problem specification)
3. Within Operation: system_id ascending
4. Within system_id: resource_id ascending
5. Renumber step_no consecutively starting at 1.
"""

from __future__ import annotations

from typing import Any

from src.inventory import Resource
from src.rules import Violation


OPERATION_ORDER = {
    # Findings
    "REPORT_REMAINING_RECORD": 1,
    "REPORT_EXPOSED_PII": 2,
    "REPORT_ACTIVE_DATA_FLOW": 3,
    "REPORT_RESTORE_RISK": 4,
    # Remediation
    "DISABLE_DATA_FLOW": 11,
    "BLOCK_RESTORE": 12,
    "DELETE_RECORD": 13,
    "REDACT_RECORD": 14,
    "ANONYMIZE_RECORD": 15,
    # Verification
    "VERIFY_RECORD_ABSENT": 21,
    "VERIFY_RECORD_PRESENT": 22,
    "VERIFY_RECORD_REDACTED": 23,
    "VERIFY_RECORD_ANONYMIZED": 24,
    "VERIFY_DATA_FLOW_DISABLED": 25,
    "VERIFY_RESTORE_BLOCKED": 26,
}

PHASE_ORDER = {
    "FINDING": 1,
    "REMEDIATION": 2,
    "VERIFICATION": 3,
}


def render_steps(
    deletion_status: str,
    violations: list[Violation],
    resources: list[Resource],
) -> list[dict[str, Any]]:
    if deletion_status == "NOT_APPLICABLE":
        return []

    raw_steps: list[dict[str, Any]] = []

    if deletion_status == "INCOMPLETE":
        # 1. FINDINGS (grounded with real evidence_id)
        for v in violations:
            ev_id = v.resource.evidence_ids[0] if v.resource.evidence_ids else ""
            if v.violation_type == "VIOLATION_REMAINING":
                raw_steps.append({
                    "phase": "FINDING",
                    "system_id": v.resource.system_id,
                    "resource_id": v.resource.resource_id,
                    "operation": "REPORT_REMAINING_RECORD",
                    "state": "PRESENT",
                    "evidence_id": ev_id,
                })
            elif v.violation_type == "VIOLATION_PII":
                raw_steps.append({
                    "phase": "FINDING",
                    "system_id": v.resource.system_id,
                    "resource_id": v.resource.resource_id,
                    "operation": "REPORT_EXPOSED_PII",
                    "state": "PRESENT",
                    "evidence_id": ev_id,
                })
            elif v.violation_type == "VIOLATION_ACTIVE_FLOW":
                raw_steps.append({
                    "phase": "FINDING",
                    "system_id": v.resource.system_id,
                    "resource_id": v.resource.resource_id,
                    "operation": "REPORT_ACTIVE_DATA_FLOW",
                    "state": "ACTIVE",
                    "evidence_id": ev_id,
                })
            elif v.violation_type == "VIOLATION_RESTORE_RISK":
                raw_steps.append({
                    "phase": "FINDING",
                    "system_id": v.resource.system_id,
                    "resource_id": v.resource.resource_id,
                    "operation": "REPORT_RESTORE_RISK",
                    "state": "ACTIVE",
                    "evidence_id": ev_id,
                })

        # 2. REMEDIATION (future plan: evidence_id = "")
        for v in violations:
            if v.violation_type == "VIOLATION_ACTIVE_FLOW":
                raw_steps.append({
                    "phase": "REMEDIATION",
                    "system_id": v.resource.system_id,
                    "resource_id": v.resource.resource_id,
                    "operation": "DISABLE_DATA_FLOW",
                    "state": "DISABLED",
                    "evidence_id": "",
                })
            elif v.violation_type == "VIOLATION_RESTORE_RISK":
                raw_steps.append({
                    "phase": "REMEDIATION",
                    "system_id": v.resource.system_id,
                    "resource_id": v.resource.resource_id,
                    "operation": "BLOCK_RESTORE",
                    "state": "BLOCKED",
                    "evidence_id": "",
                })
            elif v.violation_type == "VIOLATION_REMAINING":
                raw_steps.append({
                    "phase": "REMEDIATION",
                    "system_id": v.resource.system_id,
                    "resource_id": v.resource.resource_id,
                    "operation": "DELETE_RECORD",
                    "state": "ABSENT",
                    "evidence_id": "",
                })
            elif v.violation_type == "VIOLATION_PII":
                op = "ANONYMIZE_RECORD" if v.required_action == "ANONYMIZE" else "REDACT_RECORD"
                st = "ANONYMIZED" if v.required_action == "ANONYMIZE" else "REDACTED"
                raw_steps.append({
                    "phase": "REMEDIATION",
                    "system_id": v.resource.system_id,
                    "resource_id": v.resource.resource_id,
                    "operation": op,
                    "state": st,
                    "evidence_id": "",
                })

        # 3. VERIFICATION (future checks for INCOMPLETE: evidence_id = "")
        # First verify absent records (account_service first)
        for res in resources:
            if res.system_id == "account_service":
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": res.system_id,
                    "resource_id": res.resource_id,
                    "operation": "VERIFY_RECORD_ABSENT",
                    "state": "ABSENT",
                    "evidence_id": "",
                })
        for v in violations:
            if v.violation_type == "VIOLATION_REMAINING" and v.resource.system_id != "account_service":
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": v.resource.system_id,
                    "resource_id": v.resource.resource_id,
                    "operation": "VERIFY_RECORD_ABSENT",
                    "state": "ABSENT",
                    "evidence_id": "",
                })
        # Next retained records (security_service)
        for res in resources:
            if res.system_id == "security_service":
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": res.system_id,
                    "resource_id": res.resource_id,
                    "operation": "VERIFY_RECORD_PRESENT",
                    "state": "PRESENT",
                    "evidence_id": "",
                })
        # Redacted & anonymized post-remediation checks
        for v in violations:
            if v.violation_type == "VIOLATION_PII":
                op = "VERIFY_RECORD_ANONYMIZED" if v.required_action == "ANONYMIZE" else "VERIFY_RECORD_REDACTED"
                st = "ANONYMIZED" if v.required_action == "ANONYMIZE" else "REDACTED"
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": v.resource.system_id,
                    "resource_id": v.resource.resource_id,
                    "operation": op,
                    "state": st,
                    "evidence_id": "",
                })
            elif v.violation_type == "VIOLATION_ACTIVE_FLOW":
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": v.resource.system_id,
                    "resource_id": v.resource.resource_id,
                    "operation": "VERIFY_DATA_FLOW_DISABLED",
                    "state": "DISABLED",
                    "evidence_id": "",
                })
            elif v.violation_type == "VIOLATION_RESTORE_RISK":
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": v.resource.system_id,
                    "resource_id": v.resource.resource_id,
                    "operation": "VERIFY_RESTORE_BLOCKED",
                    "state": "BLOCKED",
                    "evidence_id": "",
                })

    elif deletion_status == "COMPLETE":
        # Only VERIFICATION steps, all citing real evidence_ids
        for res in resources:
            ev_id = res.evidence_ids[0] if res.evidence_ids else ""
            if res.system_id == "account_service" and res.state_at_audit_at == "ABSENT":
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": res.system_id,
                    "resource_id": res.resource_id,
                    "operation": "VERIFY_RECORD_ABSENT",
                    "state": "ABSENT",
                    "evidence_id": ev_id,
                })
            elif res.system_id == "security_service" and res.state_at_audit_at == "PRESENT":
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": res.system_id,
                    "resource_id": res.resource_id,
                    "operation": "VERIFY_RECORD_PRESENT",
                    "state": "PRESENT",
                    "evidence_id": ev_id,
                })
            elif res.system_id in ["identity_service", "support_platform"] and res.state_at_audit_at in ["REDACTED", "PRESENT"]:
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": res.system_id,
                    "resource_id": res.resource_id,
                    "operation": "VERIFY_RECORD_REDACTED",
                    "state": "REDACTED",
                    "evidence_id": ev_id,
                })
            elif res.system_id == "analytics_platform" and res.state_at_audit_at in ["ANONYMIZED", "PRESENT"]:
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": res.system_id,
                    "resource_id": res.resource_id,
                    "operation": "VERIFY_RECORD_ANONYMIZED",
                    "state": "ANONYMIZED",
                    "evidence_id": ev_id,
                })
            elif res.is_data_flow and res.state_at_audit_at == "DISABLED":
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": res.system_id,
                    "resource_id": res.resource_id,
                    "operation": "VERIFY_DATA_FLOW_DISABLED",
                    "state": "DISABLED",
                    "evidence_id": ev_id,
                })
            elif res.is_restore_risk and res.state_at_audit_at == "BLOCKED":
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": res.system_id,
                    "resource_id": res.resource_id,
                    "operation": "VERIFY_RESTORE_BLOCKED",
                    "state": "BLOCKED",
                    "evidence_id": ev_id,
                })

    # Sort strictly by (phase, operation, system_id, resource_id)
    def sort_key(s: dict[str, Any]) -> tuple:
        p_val = PHASE_ORDER.get(s["phase"], 99)
        op_val = OPERATION_ORDER.get(s["operation"], 99)
        return (p_val, op_val, s["system_id"], s["resource_id"])

    # Eliminate duplicate step signatures if any
    unique_steps = []
    seen = set()
    for s in raw_steps:
        sig = (s["phase"], s["system_id"], s["resource_id"], s["operation"], s["state"])
        if sig not in seen:
            seen.add(sig)
            unique_steps.append(s)

    unique_steps.sort(key=sort_key)

    # Renumber step_no consecutively starting at 1
    final_steps = []
    for idx, s in enumerate(unique_steps, start=1):
        final_steps.append({
            "step_no": idx,
            "phase": s["phase"],
            "system_id": s["system_id"],
            "resource_id": s["resource_id"],
            "operation": s["operation"],
            "state": s["state"],
            "evidence_id": s["evidence_id"],
        })

    return final_steps
