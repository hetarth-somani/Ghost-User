# Exploratory Data Analysis (EDA) Report

## 1. Dataset Overview

| File | Rows | Columns |
|---|---|---|
| `deletion_requests.csv` | 518 | case_id, email, requested_at, reported_status, reported_at, audit_at, request_text |
| `sample_deletion_requests.csv` | 32 | case_id, email, requested_at, reported_status, reported_at, audit_at, request_text |
| `sample_output.csv` | 32 | case_id, deletion_status, steps_json |
| `user_identities.csv` | 850 | user_id, name, email, phone, email_hash, updated_at |
| `user_audit_log.csv` | 306 | audit_id, user_id, event_time, field_name, old_value, new_value |
| `system_activity.csv` | 4011 | activity_id, event_time, event_type, source_system, target_system, resource_id, reported_result, details |
| `deletion_rules.csv` | 15 | rule_id, data_category, condition, required_action |
| `evidence_files.csv` | 94 | file_id, file_path, origin, captured_at |

## 2. Evidence Files Breakdown

- Total manifest files: **94**
- Total files on disk: **94**
- Manifest ↔ Disk exact match: **True**

### Modality Distribution

- `.sql`: 24 files
- `.pdf`: 4 files
- `.png`: 11 files
- `.log`: 26 files
- `.json`: 28 files
- `.txt`: 1 files

## 3. Sample Output Ground Truth Conventions

- Status distribution: `{'COMPLETE': 10, 'INCOMPLETE': 22}`
- Observed Systems: `['account_service', 'analytics_platform', 'backup_service', 'export_service', 'identity_service', 'integration_service', 'search_service', 'security_service', 'support_platform']`
- Observed Operations: `['ANONYMIZE_RECORD', 'BLOCK_RESTORE', 'DELETE_RECORD', 'DISABLE_DATA_FLOW', 'REDACT_RECORD', 'REPORT_ACTIVE_DATA_FLOW', 'REPORT_EXPOSED_PII', 'REPORT_REMAINING_RECORD', 'REPORT_RESTORE_RISK', 'VERIFY_DATA_FLOW_DISABLED', 'VERIFY_RECORD_ABSENT', 'VERIFY_RECORD_ANONYMIZED', 'VERIFY_RECORD_PRESENT', 'VERIFY_RECORD_REDACTED', 'VERIFY_RESTORE_BLOCKED']`

## 4. Non-Deletion Requests Identified

Detected 10 explicit non-deletion requests: case_533, case_534, case_535, case_536, case_537, case_538, case_539, case_540, case_541, case_542
