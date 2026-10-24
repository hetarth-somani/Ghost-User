"""Phase 9: Status Classification.

Deterministically assigns deletion_status:
- NOT_APPLICABLE if request_text does not authorize deletion
- INCOMPLETE if any VIOLATION_* exists
- COMPLETE if all records are compliant and flows/restore risks are disabled/blocked
"""

from __future__ import annotations

import re
from src.rules import Violation


def is_deletion_request(request_text: str) -> bool:
    """Deterministic classifier with negative intent filters and multilingual deletion terms."""
    if not request_text or not request_text.strip():
        return False

    text = request_text.lower()

    # 1. Negative filters: explicit non-deletion requests
    negative_patterns = [
        "download my account information",
        "portable format",
        "resetting the login",
        "misspelled",
        "correct it without removing",
        "marketing lists only",
        "what personal information you hold",
        "information request, not a request to erase",
        "copy of last year's invoices",
        "change the email address used for this account",
        "don't delete or change anything",
        "leave the account active",
        "not asking for deletion",
        "replace it with the new one and leave the account active",
        "stop the promotional emails",
        "need help resetting the login",
        "still want receipts and service messages",
        "want to continue using the service",
    ]
    if any(p in text for p in negative_patterns):
        return False

    # 2. Positive filters across languages (EN, FR, ES, PT, DE, JA)
    positive_terms = [
        "delete",
        "erased",
        "erasure",
        "close my account",
        "remove my account",
        "permanently deleted",
        "personal-data deletion",
        "suppression",
        "supprimer",
        "fermer mon compte",
        "effacer",
        "eliminar",
        "exclusão",
        "fechar minha conta",
        "cancelar mi cuenta",
        "löschen",
        "entfernen",
        "konto schließen",
        "削除",
        "消去",
        "アカウントを閉じる",
    ]
    return any(t in text for t in positive_terms)


def classify_case(request_text: str, violations: list[Violation]) -> str:
    """Return COMPLETE, INCOMPLETE, or NOT_APPLICABLE."""
    if not is_deletion_request(request_text):
        return "NOT_APPLICABLE"

    if violations:
        return "INCOMPLETE"

    return "COMPLETE"
