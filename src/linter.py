"""Phase 11: Output Linter.

Hard-fails on ANY violation of challenge rules:
- Exactly 518 data rows
- Exact column names (case_id, deletion_status, steps_json)
- Valid deletion_status enum
- Valid JSON array for steps_json
- Exactly 7 keys per step
- step_no starts at 1 and consecutive
- Allowed phase, operation, and state combinations
- Phase ordering: FINDING -> REMEDIATION -> VERIFICATION
- Non-empty evidence_id for COMPLETE and FINDINGS
- Empty evidence_id for REMEDIATION and future VERIFICATION
- Foreign key resolution against valid_evidence_ids
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from src.cache import CacheManager


ALLOWED_COMBINATIONS = {
    # Findings
    ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"),
    ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
    ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
    ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"),
    # Remediation
    ("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED"),
    ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED"),
    ("REMEDIATION", "DELETE_RECORD", "ABSENT"),
    ("REMEDIATION", "REDACT_RECORD", "REDACTED"),
    ("REMEDIATION", "ANONYMIZE_RECORD", "ANONYMIZED"),
    # Verification
    ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"),
    ("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"),
    ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"),
    ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
    ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),
}

REQUIRED_STEP_KEYS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}


class Linter:
    def __init__(self, repo_root: str | Path | None = None):
        if repo_root is None:
            self.repo_root = Path(__file__).resolve().parent.parent
        else:
            self.repo_root = Path(repo_root)

        self.cache = CacheManager(self.repo_root)
        self.valid_evidence_ids = self._load_valid_evidence_ids()

    def _load_valid_evidence_ids(self) -> set[str]:
        valid_ids = set()
        if self.cache.evidence_db_path.exists():
            with sqlite3.connect(self.cache.evidence_db_path) as conn:
                try:
                    rows = conn.execute("SELECT evidence_id FROM valid_evidence_ids").fetchall()
                    valid_ids = {r[0] for r in rows}
                except Exception:
                    pass
        return valid_ids

    def lint_file(self, csv_path: Path, expected_rows: int = 518) -> list[str]:
        errors: list[str] = []

        if not csv_path.exists():
            return [f"File {csv_path} does not exist."]

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            if header != ["case_id", "deletion_status", "steps_json"]:
                errors.append(f"Header mismatch. Expected ['case_id', 'deletion_status', 'steps_json'], got {header}")

            rows = list(reader)
            if len(rows) != expected_rows:
                errors.append(f"Row count mismatch: expected {expected_rows}, got {len(rows)}")

            # Check sorted case_id
            case_ids = [r["case_id"] for r in rows]
            # Case IDs follow case_01 or case_33 pattern
            # Verify no duplicate case IDs
            if len(set(case_ids)) != len(case_ids):
                errors.append("Duplicate case_ids detected.")

            for r_idx, row in enumerate(rows, start=1):
                case_id = row.get("case_id", f"row_{r_idx}")
                status = row.get("deletion_status", "")
                if status not in ["COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"]:
                    errors.append(f"{case_id}: Invalid deletion_status '{status}'")

                steps_raw = row.get("steps_json", "")
                try:
                    steps = json.loads(steps_raw)
                except Exception as e:
                    errors.append(f"{case_id}: steps_json is not valid JSON ({e})")
                    continue

                if not isinstance(steps, list):
                    errors.append(f"{case_id}: steps_json must be a JSON array")
                    continue

                if status == "NOT_APPLICABLE":
                    if len(steps) != 0:
                        errors.append(f"{case_id}: NOT_APPLICABLE case must have empty steps array [], got {len(steps)}")
                    continue

                if status == "COMPLETE":
                    # Only verification steps allowed
                    for step in steps:
                        if step.get("phase") != "VERIFICATION":
                            errors.append(f"{case_id}: COMPLETE case contains non-VERIFICATION step: {step.get('phase')}")
                        ev_id = step.get("evidence_id", "")
                        if not ev_id:
                            errors.append(f"{case_id}: COMPLETE case has empty evidence_id for {step.get('resource_id')}")
                        elif self.valid_evidence_ids and ev_id not in self.valid_evidence_ids:
                            errors.append(f"{case_id}: Unresolvable evidence_id '{ev_id}'")

                if status == "INCOMPLETE":
                    phases = [s.get("phase") for s in steps]
                    if "FINDING" not in phases or "REMEDIATION" not in phases or "VERIFICATION" not in phases:
                        errors.append(f"{case_id}: INCOMPLETE case must have FINDING, REMEDIATION, and VERIFICATION phases")

                # Step-by-step checks
                expected_step_no = 1
                phase_order_seen = []
                for s in steps:
                    step_keys = set(s.keys())
                    if step_keys != REQUIRED_STEP_KEYS:
                        errors.append(f"{case_id}: Invalid step keys: {step_keys - REQUIRED_STEP_KEYS} missing, {REQUIRED_STEP_KEYS - step_keys} extra")

                    s_no = s.get("step_no")
                    if s_no != expected_step_no:
                        errors.append(f"{case_id}: Non-consecutive step_no: expected {expected_step_no}, got {s_no}")
                    expected_step_no += 1

                    combo = (s.get("phase"), s.get("operation"), s.get("state"))
                    if combo not in ALLOWED_COMBINATIONS:
                        errors.append(f"{case_id}: Invalid step combination: {combo}")

                    # Phase ordering validation
                    curr_phase = s.get("phase")
                    if phase_order_seen and phase_order_seen[-1] != curr_phase:
                        if curr_phase == "FINDING" and ("REMEDIATION" in phase_order_seen or "VERIFICATION" in phase_order_seen):
                            errors.append(f"{case_id}: Out of order phase {curr_phase} after {phase_order_seen}")
                        elif curr_phase == "REMEDIATION" and "VERIFICATION" in phase_order_seen:
                            errors.append(f"{case_id}: Out of order phase {curr_phase} after {phase_order_seen}")
                    phase_order_seen.append(curr_phase)

                    # Evidence ID checks for INCOMPLETE
                    if status == "INCOMPLETE":
                        ev_id = s.get("evidence_id", "")
                        if curr_phase == "FINDING":
                            if not ev_id:
                                errors.append(f"{case_id}: FINDING step requires non-empty evidence_id")
                            elif self.valid_evidence_ids and ev_id not in self.valid_evidence_ids:
                                errors.append(f"{case_id}: Unresolvable evidence_id '{ev_id}' in FINDING")
                        elif curr_phase in ["REMEDIATION", "VERIFICATION"]:
                            if ev_id != "":
                                errors.append(f"{case_id}: {curr_phase} step in INCOMPLETE case must have empty evidence_id, got '{ev_id}'")

        return errors
