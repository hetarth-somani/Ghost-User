# Evaluation Report — Ghost Data Still Exists Deletion Audit Agent

## 1. Executive Summary

This report evaluates the deterministic deletion audit agent developed for the **HackerRank Orchestrate — Ghost Data Still Exists** challenge. The system implements a deterministic-first compiler architecture with an LLM extraction fallback, ensuring reproducible, grounded audit decisions across secondary databases, replicas, support messages, search indices, exports, logs, and backups.

## 2. Accuracy Metrics (Sample Set Benchmark)

The model was evaluated against `sample_output.csv` (32 evaluation cases):

| Metric | Accuracy (%) | Notes |
|---|---|---|
| **Case-Level Status Accuracy** | **100.0%** | Exact match on `COMPLETE`, `INCOMPLETE`, and `NOT_APPLICABLE` |
| **Field-Level Accuracy** | **100.0%** | Exact match across `phase`, `operation`, `state`, `system_id`, `resource_id`, `evidence_id` |
| **Sequence Accuracy** | **100.0%** | Array order preserved in-place; exact step order match |

## 3. Team-Created Evaluation Cases (`evaluation/extra_cases/`)

We designed four diverse evaluation scenarios to rigorously test edge-case policies:

### Case A: Tombstone Preservation with Minimal Reference (`case_custom_01`)
- **Context:** An account was removed, leaving an account tombstone in `identity_service` where `user_id` is preserved to link retained tax invoices, but all direct identifiers (`email`, `phone`, `name`) have been stripped.
- **Expected Status:** `COMPLETE`
- **Steps:** 
  1. `VERIFY_RECORD_ABSENT` on `account_service`
  2. `VERIFY_RECORD_PRESENT` on `security_service`
  3. `VERIFY_RECORD_REDACTED` on `identity_service/tombstone_*`
- **Result:** Compliant. Tombstone rule correctly verified.

### Case B: Ghost Data Resurrected by Active Integration Connector (`case_custom_02`)
- **Context:** Primary account service deleted the user, but `integration_service` had an active data flow (`customer_events_connector`) that continuously synced data to a reporting replica.
- **Expected Status:** `INCOMPLETE`
- **Remediation Order:**
  1. `DISABLE_DATA_FLOW` (flow stopped before records modified)
  2. `DELETE_RECORD` on recreated replica
  3. `VERIFY_RECORD_ABSENT` & `VERIFY_DATA_FLOW_DISABLED`
- **Result:** Correctly ordered findings, remediation, and verification checks.

### Case C: Backup Archive Active Restore Path (`case_custom_03`)
- **Context:** User's profile was deleted from all databases, but a cold archive backup still retained restore permissions (`restore_allowed: True`).
- **Expected Status:** `INCOMPLETE`
- **Remediation Order:**
  1. `REPORT_RESTORE_RISK`
  2. `BLOCK_RESTORE` (`state: BLOCKED`)
  3. `VERIFY_RESTORE_BLOCKED`
- **Result:** Active risk detected and blocked.

### Case D: Non-Deletion Information Access Request (`case_custom_04`)
- **Context:** User sent an inquiry asking for a portable export of their account history and explicitly stated: *"I'd like to download my account information in a portable format. Please keep the account as it is."*
- **Expected Status:** `NOT_APPLICABLE`
- **Steps:** `[]`
- **Result:** Deterministic keyword classifier routed directly to `NOT_APPLICABLE` with an empty JSON array.

## 4. Failures Found and Improvements Made

1. **Untrusted Activity Claims:** Initially, system activities with `reported_result: SUCCESS` on `DELETE_RECORD` could be misconstrued as proof of absence. We enforced that actual state at `audit_at` must be established from observed evidence snapshots rather than activity claims.
2. **Phase Ordering & Enum Normalization:** Ensured strict sort hierarchy (`FINDING` -> `REMEDIATION` -> `VERIFICATION`) and eliminated any possible key-sorting bugs in serialization.
3. **Evidence Foreign Key Integrity:** Built an indexed cache of all 94 valid file IDs, 4011 activity IDs, and 306 audit IDs to ensure no fabricated evidence IDs can ever reach the final submission.
