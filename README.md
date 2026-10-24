# Ghost Data Still Exists — Deterministic Deletion Audit Agent

AI-powered deletion-audit agent for the **HackerRank Orchestrate (October 2026)** competition.

## System Architecture

The solution uses a **deterministic-first compiler architecture** with an LLM extraction fallback:
1. **Evidence Ingestion (`src/ingest.py`):** Normalizes SQL database exports, JSON snapshot bundles, logs, documents, and screenshots into SQLite caches.
2. **Identity Resolution (`src/identity.py`):** Graph union-find linking current identities (`user_identities.csv`), historical changes (`user_audit_log.csv`), and evidence records.
3. **Timeline Reconstruction (`src/timeline.py`):** Reconstructs system history up to `audit_at`. Treats workflow statuses and operation results as claims, establishing true state only from grounded evidence.
4. **Rules & Inventory (`src/inventory.py`, `src/rules.py`):** Maps resources to policy categories, checks tombstone conditions, and identifies policy violations.
5. **Deterministic Steps & Linter (`src/steps.py`, `src/linter.py`):** Renders strictly ordered steps (`FINDING` -> `REMEDIATION` -> `VERIFICATION`) and validates schema compliance.

## Setup Instructions

### Prerequisites
- Python 3.11+
- Virtual environment recommended

### Installation
```bash
pip install -r requirements.txt
```

### Running the Audit Pipeline

To run the audit agent across the full evaluation dataset (`dataset/deletion_requests.csv`):
```bash
python code/main.py
```
This produces the final submission file `output.csv` at the repository root.

To run sample evaluation:
```bash
python src/pipeline.py --sample
python evaluation/run_eval.py
```

To inspect an individual case via the review CLI:
```bash
python src/review.py case_05
```

## Challenge Submission Link
https://www.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists
