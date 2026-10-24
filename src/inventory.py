"""Phase 7: Resource & risk inventory.

Discovers all relevant resources and data flows for the user up to audit_at,
grounded strictly in evidence records and activities.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.cache import CacheManager
from src.identity import IdentityBundle
from src.timeline import TimelineEvent


@dataclass
class Resource:
    system_id: str
    resource_id: str
    category: str
    state_at_audit_at: str  # PRESENT | ABSENT | REDACTED | ANONYMIZED | DISABLED | BLOCKED
    identifiers_remaining: set[str] = field(default_factory=set)
    evidence_ids: list[str] = field(default_factory=list)
    is_data_flow: bool = False
    is_restore_risk: bool = False
    is_retained_record: bool = False


class InventoryBuilder:
    def __init__(self, repo_root: str | Path | None = None):
        if repo_root is None:
            self.repo_root = Path(__file__).resolve().parent.parent
        else:
            self.repo_root = Path(repo_root)
        self.cache = CacheManager(self.repo_root)

    def build_inventory(
        self,
        bundle: IdentityBundle,
        events: list[TimelineEvent],
        audit_at: str,
    ) -> list[Resource]:
        resources_map: dict[tuple[str, str], Resource] = {}

        # 1. Search evidence_index.sqlite records for matches on user_id or emails
        with sqlite3.connect(self.cache.evidence_db_path) as conn:
            cursor = conn.cursor()
            # Fetch records observed at or before audit_at
            query = """
                SELECT system_id, resource_id, data_category, user_id, identifiers_json, state, observed_at, evidence_id, details_json
                FROM records
                WHERE observed_at <= ?
                ORDER BY observed_at ASC
            """
            rows = cursor.execute(query, (audit_at,)).fetchall()

            for r in rows:
                sys_id, res_id, cat, uid, idents_str, state, obs_at, ev_id, details_str = r
                idents = json.loads(idents_str) if idents_str else {}
                details = json.loads(details_str) if details_str else {}

                match = False
                if bundle.user_id and uid == bundle.user_id:
                    match = True
                elif any(em in str(idents).lower() or em in str(details).lower() for em in bundle.emails):
                    match = True

                if match and res_id:
                    key = (sys_id, res_id)
                    remaining = set()
                    for k, v in idents.items():
                        if v and any(em in str(v).lower() for em in bundle.emails):
                            remaining.add("email")
                        if v and any(p in str(v) for p in bundle.phones):
                            remaining.add("phone")

                    # Map system to category if not specific, prioritizing resource_id prefix
                    if res_id.startswith("tombstone_"):
                        cat = "ACCOUNT_TOMBSTONE"
                        sys_id = "identity_service"
                    elif res_id.startswith("legal_hold_"):
                        cat = "LEGAL_HOLD_RECORD"
                        sys_id = "legal_service"
                    elif "audit_record" in res_id or sys_id == "security_service":
                        cat = "SECURITY_AUDIT_LOG"
                        sys_id = "security_service"
                    elif cat in ["OBSERVED_EXPORT", "SNAPSHOT_RECORD", "DOCUMENT_OBSERVATION"]:
                        sys_cat_map = {
                            "account_service": "USER_PROFILE",
                            "search_service": "SEARCH_INDEX_ENTRY",
                            "support_platform": "SUPPORT_MESSAGE",
                            "analytics_platform": "ANALYTICS_PROFILE",
                            "export_service": "USER_EXPORT",
                            "security_service": "SECURITY_AUDIT_LOG",
                            "identity_service": "ACCOUNT_TOMBSTONE",
                            "integration_service": "CACHE_ENTRY",
                            "backup_service": "BACKUP_ARCHIVE",
                            "legal_service": "LEGAL_HOLD_RECORD",
                        }
                        cat = sys_cat_map.get(sys_id, cat)

                    is_flow = "data_flow" in res_id or sys_id == "integration_service"
                    is_backup = "backup" in res_id or sys_id == "backup_service"
                    is_retained = cat in ["SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD", "BACKUP_ARCHIVE"]

                    if key not in resources_map:
                        resources_map[key] = Resource(
                            system_id=sys_id,
                            resource_id=res_id,
                            category=cat,
                            state_at_audit_at=state,
                            identifiers_remaining=remaining,
                            evidence_ids=[ev_id],
                            is_data_flow=is_flow,
                            is_restore_risk=is_backup,
                            is_retained_record=is_retained,
                        )
                    else:
                        # Update with latest observed state at or before audit_at
                        res = resources_map[key]
                        res.state_at_audit_at = state
                        res.identifiers_remaining = remaining
                        # Place specific evidence (like logs, dumps) ahead of generic exports
                        if ev_id not in res.evidence_ids:
                            if "log" in ev_id or "sql" in ev_id:
                                res.evidence_ids.insert(0, ev_id)
                            else:
                                res.evidence_ids.append(ev_id)

        # 2. Add resources from timeline activities (flows, backup checks)
        for ev in events:
            if ev.resource_id:
                key = (ev.target_system or ev.source_system, ev.resource_id)
                sys_id = ev.target_system or ev.source_system
                is_flow = "data_flow" in ev.resource_id or ev.event_type in ["CHECK_DATA_FLOW", "DISABLE_DATA_FLOW", "SYNC_RECORD"]
                is_backup = "backup" in ev.resource_id or ev.event_type in ["CHECK_RESTORE_ACCESS", "BLOCK_RESTORE", "RESTORE_BACKUP"]

                state = "PRESENT"
                if ev.event_type == "DISABLE_DATA_FLOW" and ev.reported_result == "SUCCESS":
                    state = "DISABLED"
                elif ev.event_type == "BLOCK_RESTORE" and ev.reported_result == "SUCCESS":
                    state = "BLOCKED"
                elif ev.event_type in ["CHECK_DATA_FLOW", "SYNC_RECORD"]:
                    state = "ACTIVE"
                elif ev.event_type == "CHECK_RESTORE_ACCESS":
                    state = "ACTIVE"

                if key not in resources_map:
                    is_audit = "audit_record" in ev.resource_id or sys_id == "security_service"
                    is_tombstone = ev.resource_id.startswith("tombstone_") or sys_id == "identity_service"
                    is_support = ev.resource_id.startswith("support_") or sys_id == "support_platform"
                    is_search = ev.resource_id.startswith("search_") or sys_id == "search_service"
                    is_analytics = ev.resource_id.startswith("analytics_") or sys_id == "analytics_platform"

                    if is_backup:
                        cat = "BACKUP_ARCHIVE"
                    elif is_flow:
                        cat = "CACHE_ENTRY"
                    elif is_audit:
                        cat = "SECURITY_AUDIT_LOG"
                    elif is_tombstone:
                        cat = "ACCOUNT_TOMBSTONE"
                    elif is_support:
                        cat = "SUPPORT_MESSAGE"
                    elif is_search:
                        cat = "SEARCH_INDEX_ENTRY"
                    elif is_analytics:
                        cat = "ANALYTICS_PROFILE"
                    else:
                        cat = "USER_PROFILE"

                    resources_map[key] = Resource(
                        system_id=sys_id,
                        resource_id=ev.resource_id,
                        category=cat,
                        state_at_audit_at=state,
                        identifiers_remaining=set(),
                        evidence_ids=[ev.evidence_id],
                        is_data_flow=is_flow,
                        is_restore_risk=is_backup,
                        is_retained_record=is_backup or is_audit,
                    )

        return list(resources_map.values())
