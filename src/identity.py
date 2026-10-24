"""Phase 5: Identity resolution graph.

Resolves request email across user_identities.csv and user_audit_log.csv
to build a complete IdentityBundle of all historical and current identifiers:
- user_id
- emails
- phones
- names
- email_hashes
- time_windows
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class IdentityBundle:
    user_id: Optional[str]
    emails: set[str] = field(default_factory=set)
    phones: set[str] = field(default_factory=set)
    names: set[str] = field(default_factory=set)
    email_hashes: set[str] = field(default_factory=set)
    audit_history: list[dict[str, str]] = field(default_factory=list)


class IdentityResolver:
    def __init__(self, repo_root: str | Path | None = None):
        if repo_root is None:
            self.repo_root = Path(__file__).resolve().parent.parent
        else:
            self.repo_root = Path(repo_root)

        self.dataset_dir = self.repo_root / "dataset"
        self._identities_by_id: dict[str, dict[str, str]] = {}
        self._identities_by_email: dict[str, str] = {}
        self._audit_by_user: dict[str, list[dict[str, str]]] = {}
        self._email_to_user_from_audit: dict[str, str] = {}

        self._load_identities()
        self._load_audit_log()

    def _load_identities(self) -> None:
        ident_csv = self.dataset_dir / "user_identities.csv"
        with open(ident_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = row["user_id"]
                email = row["email"].strip().lower()
                self._identities_by_id[uid] = row
                self._identities_by_email[email] = uid

    def _load_audit_log(self) -> None:
        audit_csv = self.dataset_dir / "user_audit_log.csv"
        with open(audit_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = row["user_id"]
                if uid not in self._audit_by_user:
                    self._audit_by_user[uid] = []
                self._audit_by_user[uid].append(row)

                # Track historical email mapping
                if row["field_name"] == "email":
                    old_em = row["old_value"].strip().lower()
                    new_em = row["new_value"].strip().lower()
                    if old_em:
                        self._email_to_user_from_audit[old_em] = uid
                    if new_em:
                        self._email_to_user_from_audit[new_em] = uid

    def resolve(self, email: str) -> IdentityBundle:
        norm_email = email.strip().lower()
        # Find user_id
        user_id = self._identities_by_email.get(norm_email)
        if not user_id:
            user_id = self._email_to_user_from_audit.get(norm_email)

        bundle = IdentityBundle(user_id=user_id)
        bundle.emails.add(norm_email)

        if user_id and user_id in self._identities_by_id:
            row = self._identities_by_id[user_id]
            if row.get("email"):
                bundle.emails.add(row["email"].strip().lower())
            if row.get("phone"):
                bundle.phones.add(row["phone"].strip())
            if row.get("name"):
                bundle.names.add(row["name"].strip())
            if row.get("email_hash"):
                bundle.email_hashes.add(row["email_hash"].strip().lower())

        if user_id and user_id in self._audit_by_user:
            bundle.audit_history = self._audit_by_user[user_id]
            for audit_entry in bundle.audit_history:
                field = audit_entry["field_name"]
                old_val = audit_entry.get("old_value", "").strip()
                new_val = audit_entry.get("new_value", "").strip()
                if field == "email":
                    if old_val:
                        bundle.emails.add(old_val.lower())
                    if new_val:
                        bundle.emails.add(new_val.lower())
                elif field == "phone":
                    if old_val:
                        bundle.phones.add(old_val)
                    if new_val:
                        bundle.phones.add(new_val)
                elif field == "email_hash":
                    if old_val:
                        bundle.email_hashes.add(old_val.lower())
                    if new_val:
                        bundle.email_hashes.add(new_val.lower())

        return bundle
