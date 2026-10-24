"""Phase 3: Evidence ingestion into evidence_index.sqlite.

Loads manifest, system_activity, user_audit_log, and parses all 94 evidence files:
- SQL snapshots (sqlite3 parse)
- JSON records (service_resource_export, snapshot_bundles)
- Log files (regex and structured trace parsers)
- PDFs and images (via Extractor)
Decouples reported claim from observed evidence state.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from src.cache import CacheManager
from src.ocr import Extractor


class EvidenceIngestor:
    def __init__(self, repo_root: str | Path | None = None):
        if repo_root is None:
            self.repo_root = Path(__file__).resolve().parent.parent
        else:
            self.repo_root = Path(repo_root)

        self.dataset_dir = self.repo_root / "dataset"
        self.evidence_dir = self.dataset_dir / "evidence"
        self.cache = CacheManager(self.repo_root)
        self.extractor = Extractor(self.repo_root)

    def ingest_all(self) -> None:
        """Run complete evidence ingestion pass."""
        self._ingest_valid_ids()
        self._ingest_activity()
        self._ingest_audit_log()
        self._ingest_evidence_files()

    def _ingest_valid_ids(self) -> None:
        """Populate valid_evidence_ids with file_ids, activity_ids, audit_ids."""
        with sqlite3.connect(self.cache.evidence_db_path) as conn:
            # 1. Manifest file IDs
            manifest_csv = self.dataset_dir / "evidence_files.csv"
            with open(manifest_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    conn.execute(
                        "INSERT OR IGNORE INTO valid_evidence_ids (evidence_id, source_type) VALUES (?, ?)",
                        (row["file_id"], "file_id"),
                    )

            # 2. Activity IDs
            activity_csv = self.dataset_dir / "system_activity.csv"
            with open(activity_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    conn.execute(
                        "INSERT OR IGNORE INTO valid_evidence_ids (evidence_id, source_type) VALUES (?, ?)",
                        (row["activity_id"], "activity_id"),
                    )

            # 3. Audit IDs
            audit_csv = self.dataset_dir / "user_audit_log.csv"
            with open(audit_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    conn.execute(
                        "INSERT OR IGNORE INTO valid_evidence_ids (evidence_id, source_type) VALUES (?, ?)",
                        (row["audit_id"], "audit_id"),
                    )

    def _ingest_activity(self) -> None:
        """Populate system_activity into SQLite activities table."""
        activity_csv = self.dataset_dir / "system_activity.csv"
        with open(activity_csv, "r", encoding="utf-8") as f, sqlite3.connect(self.cache.evidence_db_path) as conn:
            reader = csv.DictReader(f)
            for row in reader:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO activities 
                    (activity_id, event_time, event_type, source_system, target_system, resource_id, reported_result, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["activity_id"],
                        row["event_time"],
                        row["event_type"],
                        row["source_system"],
                        row["target_system"],
                        row["resource_id"],
                        row["reported_result"],
                        row["details"],
                    ),
                )

    def _ingest_audit_log(self) -> None:
        """Populate user_audit_log into SQLite audit table."""
        audit_csv = self.dataset_dir / "user_audit_log.csv"
        with open(audit_csv, "r", encoding="utf-8") as f, sqlite3.connect(self.cache.evidence_db_path) as conn:
            reader = csv.DictReader(f)
            for row in reader:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO audit 
                    (audit_id, user_id, event_time, field_name, old_value, new_value)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["audit_id"],
                        row["user_id"],
                        row["event_time"],
                        row["field_name"],
                        row["old_value"],
                        row["new_value"],
                    ),
                )

    def _ingest_evidence_files(self) -> None:
        """Parse files from evidence_files.csv into records table."""
        manifest_csv = self.dataset_dir / "evidence_files.csv"
        with open(manifest_csv, "r", encoding="utf-8") as f:
            manifest_rows = list(csv.DictReader(f))

        for row in manifest_rows:
            file_id = row["file_id"]
            rel_path = row["file_path"]
            file_path = self.dataset_dir / rel_path
            captured_at = row["captured_at"]

            if not file_path.exists():
                continue

            ext = file_path.suffix.lower()
            if ext == ".json":
                self._parse_json_evidence(file_id, file_path, captured_at)
            elif ext == ".sql":
                self._parse_sql_evidence(file_id, file_path, captured_at)
            elif ext == ".log":
                self._parse_log_evidence(file_id, file_path, captured_at)
            elif ext in [".txt", ".pdf", ".png"]:
                self._parse_doc_or_image_evidence(file_id, file_path, captured_at, ext)

    def _insert_record(
        self,
        system_id: str,
        resource_id: str,
        data_category: str,
        user_id: str | None,
        identifiers: dict[str, Any],
        state: str,
        observed_at: str,
        evidence_id: str,
        details: Any = None,
    ) -> None:
        with sqlite3.connect(self.cache.evidence_db_path) as conn:
            conn.execute(
                """
                INSERT INTO records 
                (system_id, resource_id, data_category, user_id, identifiers_json, state, observed_at, evidence_id, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    system_id,
                    resource_id,
                    data_category,
                    user_id,
                    json.dumps(identifiers),
                    state,
                    observed_at,
                    evidence_id,
                    json.dumps(details) if details else None,
                ),
            )

    def _parse_json_evidence(self, file_id: str, file_path: Path, captured_at: str) -> None:
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception:
                return

        # Check for service_resource_export structure
        if isinstance(data, dict) and "service_exports" in data:
            for sys_id, export_content in data["service_exports"].items():
                if isinstance(export_content, dict):
                    for collection_name, items in export_content.items():
                        if isinstance(items, list):
                            for item in items:
                                res_id = item.get("resource_id", "")
                                obs_at = item.get("observed_at", captured_at)
                                user_ref = item.get("customer_reference") or item.get("subject_reference")
                                # Determine state
                                state = "PRESENT"
                                if item.get("status_code") == 404 or item.get("profile") is None and sys_id == "account_service":
                                    state = "ABSENT"
                                elif item.get("restore_allowed") is False:
                                    state = "BLOCKED"
                                elif item.get("enabled") is False or item.get("last_delivery_status") == "stopped":
                                    state = "DISABLED"
                                elif item.get("audience_cohort") and not any(item.get(k) for k in ["email", "phone", "customer_reference"]):
                                    state = "ANONYMIZED"
                                elif sys_id == "support_platform" and not item.get("requester_email"):
                                    state = "REDACTED"

                                idents = {
                                    k: item[k]
                                    for k in ["email", "owner_email", "requester_email", "customer_email", "phone", "requester_phone"]
                                    if item.get(k)
                                }
                                self._insert_record(
                                    system_id=sys_id,
                                    resource_id=res_id,
                                    data_category="OBSERVED_EXPORT",
                                    user_id=user_ref,
                                    identifiers=idents,
                                    state=state,
                                    observed_at=obs_at,
                                    evidence_id=file_id,
                                    details=item,
                                )

        # Check for security_audit_ledger
        elif "audit_ledger" in data if isinstance(data, dict) else False:
            for entry in data.get("audit_ledger", []):
                self._insert_record(
                    system_id="security_service",
                    resource_id=entry.get("resource_id", ""),
                    data_category="SECURITY_AUDIT_LOG",
                    user_id=entry.get("subject_reference"),
                    identifiers={},
                    state="PRESENT",
                    observed_at=entry.get("timestamp", captured_at),
                    evidence_id=file_id,
                    details=entry,
                )

        # Check for customer_data_snapshot_bundle format with nested "snapshots"
        elif isinstance(data, dict) and "snapshots" in data:
            for snap in data.get("snapshots", []):
                data_store = snap.get("data_store", "record_system")
                collection = snap.get("collection", "")
                cap_time = snap.get("captured_at", captured_at)
                for item in snap.get("records", []):
                    res_id = item.get("resource_id", "")
                    user_ref = item.get("subject_reference") or item.get("user_id") or item.get("customer_reference")
                    acc_status = str(item.get("account_status", "")).upper()

                    state = "PRESENT"
                    if acc_status in ["DELETED", "ABSENT"]:
                        state = "ABSENT" if data_store == "account_service" else "REDACTED"
                    elif data_store == "identity_service" and not any(item.get(k) for k in ["name", "email", "phone", "email_hash"]):
                        state = "REDACTED"

                    cat = "ACCOUNT_TOMBSTONE" if data_store == "identity_service" else "SECURITY_AUDIT_LOG" if data_store == "security_service" else "USER_PROFILE"
                    idents = {k: item[k] for k in ["email", "phone", "name"] if item.get(k)}
                    self._insert_record(
                        system_id=data_store,
                        resource_id=res_id,
                        data_category=cat,
                        user_id=user_ref,
                        identifiers=idents,
                        state=state,
                        observed_at=cap_time,
                        evidence_id=file_id,
                        details=item,
                    )

        # Check for general customer_data_snapshot_bundle, connector configs, or manifests
        elif isinstance(data, dict):
            for k, val in data.items():
                if isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict) and "resource_id" in item:
                            # In connector configs / manifests, system is stored in key 'system' or 'system_id'
                            resolved_sys = item.get("system_id") or item.get("system")
                            res_id_val = item.get("resource_id", "")
                            if not resolved_sys:
                                # Derive from resource_id prefix
                                prefix_sys_map = {
                                    "account": "account_service",
                                    "search": "search_service",
                                    "support": "support_platform",
                                    "analytics": "analytics_platform",
                                    "export": "export_service",
                                    "security": "security_service",
                                    "identity": "identity_service",
                                    "tombstone": "identity_service",
                                    "data": "integration_service",
                                    "backup": "backup_service",
                                    "legal": "legal_service",
                                    "audit": "security_service",
                                }
                                prefix = res_id_val.split("_")[0] if "_" in res_id_val else ""
                                resolved_sys = prefix_sys_map.get(prefix)

                            if not resolved_sys:
                                raise ValueError(f"Unresolvable system_id for resource {res_id_val} in evidence {file_id}")

                            rec_status = str(item.get("result") or item.get("status") or item.get("state") or "PRESENT").upper()
                            state = "ABSENT" if rec_status in ["NOT_FOUND", "DELETED", "ABSENT"] else "BLOCKED" if rec_status == "BLOCKED" else "DISABLED" if rec_status == "DISABLED" else "PRESENT"
                            if "data_flow" in res_id_val and rec_status == "ACTIVE":
                                state = "ACTIVE"
                            elif "backup" in res_id_val and rec_status == "ACTIVE":
                                state = "ACTIVE"

                            subj = item.get("subject_reference") or item.get("user_id") or item.get("customer_reference")
                            idents = {k: item[k] for k in ["email", "phone"] if k in item and item[k]}
                            if subj and "@" in str(subj):
                                idents["email"] = str(subj)
                                user_id_val = None
                            else:
                                user_id_val = subj

                            obs_time = item.get("recorded_at") or item.get("timestamp") or captured_at
                            cat_val = item.get("record_type") or "SNAPSHOT_RECORD"

                            self._insert_record(
                                system_id=resolved_sys,
                                resource_id=res_id_val,
                                data_category=cat_val,
                                user_id=user_id_val,
                                identifiers=idents,
                                state=state,
                                observed_at=obs_time,
                                evidence_id=file_id,
                                details=item,
                            )

    def _parse_sql_evidence(self, file_id: str, file_path: Path, captured_at: str) -> None:
        """Execute SQLite-compatible SQL snapshot script into in-memory SQLite and extract records."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                script = f.read()

            mem_conn = sqlite3.connect(":memory:")
            mem_conn.executescript(script)
            mem_cur = mem_conn.cursor()

            tables = [r[0] for r in mem_cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            for table in tables:
                col_info = mem_cur.execute(f"PRAGMA table_info('{table}')").fetchall()
                col_names = [c[1].lower() for c in col_info]

                rows = mem_cur.execute(f"SELECT * FROM '{table}'").fetchall()
                for row_vals in rows:
                    row_dict = {col_names[idx]: val for idx, val in enumerate(row_vals)}

                    res_id = str(row_dict.get("resource_id") or row_dict.get("id") or "")
                    user_id = str(row_dict.get("user_id") or row_dict.get("customer_reference") or "")
                    email = row_dict.get("email") or row_dict.get("customer_email") or row_dict.get("owner_email")
                    phone = row_dict.get("phone") or row_dict.get("phone_number")
                    status_col = str(row_dict.get("account_status") or row_dict.get("status") or "PRESENT").upper()

                    state = "ABSENT" if status_col in ["DELETED", "ABSENT", "REMOVED"] else "PRESENT"

                    sys_id = "account_service"
                    cat = "USER_PROFILE"
                    if "search" in table or "search" in res_id:
                        sys_id = "search_service"
                        cat = "SEARCH_INDEX_ENTRY"
                    elif "support" in table or "support" in res_id:
                        sys_id = "support_platform"
                        cat = "SUPPORT_MESSAGE"

                    idents = {}
                    if email:
                        idents["email"] = str(email)
                    if phone:
                        idents["phone"] = str(phone)

                    self._insert_record(
                        system_id=sys_id,
                        resource_id=res_id,
                        data_category=cat,
                        user_id=user_id if user_id else None,
                        identifiers=idents,
                        state=state,
                        observed_at=captured_at,
                        evidence_id=file_id,
                        details={"table": table, "row": row_dict},
                    )
            mem_conn.close()
        except Exception as e:
            pass

    def _parse_log_evidence(self, file_id: str, file_path: Path, captured_at: str) -> None:
        """Parse structured logs for lookup traces and operations."""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                # Look for resource lookups, emails, and statuses
                res_match = re.search(r"(account_\d+|search_\d+|support_\d+|data_flow_\d+|backup_\d+|analytics_\d+)", line)
                status_match = re.search(r"\b(404|NOT_FOUND|DELETED|ABSENT)\b", line, re.IGNORECASE)
                email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", line)
                if res_match:
                    res_id = res_match.group(1)
                    prefix = res_id.split("_")[0]
                    sys_map = {
                        "account": "account_service",
                        "search": "search_service",
                        "support": "support_platform",
                        "data": "integration_service",
                        "backup": "backup_service",
                        "analytics": "analytics_platform",
                    }
                    sys_id = sys_map.get(prefix, "service")
                    state = "ABSENT" if status_match else "PRESENT"
                    idents = {"email": email_match.group(0)} if email_match else {}
                    self._insert_record(
                        system_id=sys_id,
                        resource_id=res_id,
                        data_category="LOG_OBSERVATION",
                        user_id=None,
                        identifiers=idents,
                        state=state,
                        observed_at=captured_at,
                        evidence_id=file_id,
                        details={"log_line": line.strip()},
                    )

    def _parse_doc_or_image_evidence(self, file_id: str, file_path: Path, captured_at: str, ext: str) -> None:
        """Extract text from docs/images/txt and scan for identifiers and resources."""
        if ext == ".txt":
            # Parse structured handover file lines
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("-") and "|" in line:
                        parts = [p.strip() for p in line.lstrip("-").split("|")]
                        if len(parts) >= 6:
                            # format: timestamp | system_id | resource_id | category | status | identifier
                            obs_time, sys_id, res_id, cat, status_val, ident_val = parts[:6]
                            state = "ABSENT" if status_val in ["NOT_FOUND", "DELETED", "ABSENT"] else "REDACTED" if status_val in ["REDACTED", "ANONYMIZED"] else "PRESENT"
                            idents = {"email": ident_val} if "@" in ident_val else {}
                            user_id = ident_val if ident_val.startswith("user_") else None
                            self._insert_record(
                                system_id=sys_id,
                                resource_id=res_id,
                                data_category=cat,
                                user_id=user_id,
                                identifiers=idents,
                                state=state,
                                observed_at=obs_time,
                                evidence_id=file_id,
                                details={"handover_line": line},
                            )
            return

        if ext == ".pdf":
            text = self.extractor.extract_pdf(file_path)
        else:
            text = self.extractor.extract_image(file_path)

        if not text:
            return

        res_matches = set(re.findall(r"(account_\d+|search_\d+|support_\d+|data_flow_\d+|backup_\d+|analytics_\d+|tombstone_\d+)", text))
        email_matches = set(re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", text))
        user_matches = set(re.findall(r"\buser_\d+\b", text))

        for res_id in res_matches:
            prefix = res_id.split("_")[0]
            sys_id = "account_service" if prefix == "account" else "identity_service" if prefix == "tombstone" else "service"
            self._insert_record(
                system_id=sys_id,
                resource_id=res_id,
                data_category="DOCUMENT_OBSERVATION",
                user_id=next(iter(user_matches), None),
                identifiers={"email": list(email_matches)} if email_matches else {},
                state="PRESENT",
                observed_at=captured_at,
                evidence_id=file_id,
                details={"text_snippet": text[:500]},
            )
