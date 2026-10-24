"""Phase 6: Timeline reconstruction.

Reconstructs timeline of events up to audit_at.
Enforces the mandatory rule:
reported_status and reported_result are claims, not proof.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.cache import CacheManager
from src.identity import IdentityBundle


@dataclass
class TimelineEvent:
    event_time: str
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str
    evidence_id: str


class TimelineReconstructor:
    def __init__(self, repo_root: str | Path | None = None):
        if repo_root is None:
            self.repo_root = Path(__file__).resolve().parent.parent
        else:
            self.repo_root = Path(repo_root)
        self.cache = CacheManager(self.repo_root)

    def build_timeline(self, bundle: IdentityBundle, audit_at: str) -> list[TimelineEvent]:
        events: list[TimelineEvent] = []
        if not bundle.user_id and not bundle.emails:
            return events

        with sqlite3.connect(self.cache.evidence_db_path) as conn:
            # Query activities up to audit_at
            # Filter by user_id or resource_id mentions
            cursor = conn.cursor()
            query = """
                SELECT activity_id, event_time, event_type, source_system, target_system, resource_id, reported_result, details
                FROM activities
                WHERE event_time <= ?
                ORDER BY event_time ASC
            """
            rows = cursor.execute(query, (audit_at,)).fetchall()

            for r in rows:
                act_id, ev_time, ev_type, src_sys, tgt_sys, res_id, rep_res, details = r
                # Match against user's identifiers in details or resource_id
                matched = False
                if bundle.user_id and bundle.user_id in details:
                    matched = True
                else:
                    for em in bundle.emails:
                        if em in details:
                            matched = True
                            break

                if matched:
                    events.append(
                        TimelineEvent(
                            event_time=ev_time,
                            event_type=ev_type,
                            source_system=src_sys,
                            target_system=tgt_sys,
                            resource_id=res_id,
                            reported_result=rep_res,
                            details=details,
                            evidence_id=act_id,
                        )
                    )

        return events
