"""End-to-end Deletion Audit Pipeline orchestrator.

Executes deterministic audit pipeline:
1. Ingests evidence into SQLite cache
2. Resolves identity bundles
3. Reconstructs timelines up to audit_at
4. Inventories resources & flows
5. Evaluates rules & violations
6. Deterministically classifies status & renders ordered steps
7. Validates output through Linter
8. Writes final output.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Native fallback to read .env file without external package dependency
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        import os
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v

from src.classify import classify_case
from src.identity import IdentityResolver
from src.ingest import EvidenceIngestor
from src.inventory import InventoryBuilder
from src.linter import Linter
from src.rules import RulesEngine
from src.steps import render_steps
from src.timeline import TimelineReconstructor


def run_pipeline(
    input_csv_name: str = "deletion_requests.csv",
    output_csv_name: str = "output.csv",
    repo_root: str | Path | None = None,
    ingest: bool = True,
) -> Path:
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent
    else:
        repo_root = Path(repo_root)

    dataset_dir = repo_root / "dataset"
    input_path = dataset_dir / input_csv_name
    output_path = repo_root / output_csv_name

    # Step 1: Ingest evidence if requested
    if ingest:
        ingestor = EvidenceIngestor(repo_root)
        ingestor.ingest_all()

    # Startup integrity guards
    with sqlite3.connect(repo_root / "cache" / "evidence_index.sqlite") as conn:
        rec_cnt = conn.execute("SELECT count(*) FROM records").fetchone()[0]
    if not ingest and rec_cnt == 0:
        raise RuntimeError("Evidence index empty; run `python -m src.ingest` first.")

    with sqlite3.connect(repo_root / "cache" / "ocr_cache.sqlite") as ocr_conn:
        ocr_cnt = ocr_conn.execute("SELECT count(*) FROM ocr_cache").fetchone()[0]
    has_pdf_png = any(p.suffix.lower() in [".pdf", ".png"] for p in (dataset_dir / "evidence").rglob("*"))
    if rec_cnt > 0 and ocr_cnt == 0 and has_pdf_png:
        raise RuntimeError("OCR cache empty but PDF/PNG evidence present. Investigate src/ingest.py and src/ocr.py.")

    # Step 2: Initialize deterministic audit modules
    id_resolver = IdentityResolver(repo_root)
    timeline_reconstructor = TimelineReconstructor(repo_root)
    inventory_builder = InventoryBuilder(repo_root)
    rules_engine = RulesEngine()

    with open(input_path, "r", encoding="utf-8") as f:
        cases = list(csv.DictReader(f))

    # Sort cases deterministically by natural numerical case_id
    cases.sort(key=lambda c: int(str(c["case_id"]).split("_")[-1]))

    rows: list[dict[str, str]] = []

    for case in cases:
        case_id = case["case_id"]
        req_email = case["email"]
        audit_at = case["audit_at"]
        request_text = case["request_text"]

        # 1. Identity resolution
        bundle = id_resolver.resolve(req_email)

        # 2. Reconstruct timeline
        events = timeline_reconstructor.build_timeline(bundle, audit_at)

        # 3. Inventory resources & risks
        resources = inventory_builder.build_inventory(bundle, events, audit_at)

        # 4. Rules & Violations
        violations = rules_engine.evaluate(resources)

        # 5. Classification
        status = classify_case(request_text, violations)

        # 6. Step generation
        steps = render_steps(status, violations, resources)
        steps_json = json.dumps(steps, separators=(",", ":"))

        rows.append({
            "case_id": case_id,
            "deletion_status": status,
            "steps_json": steps_json,
        })

    # Write output CSV
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"], quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    # Run Linter
    linter = Linter(repo_root)
    expected_count = 32 if "sample" in input_csv_name else 518
    errors = linter.lint_file(output_path, expected_rows=expected_count)
    if errors:
        print(f"Linter found {len(errors)} issues:")
        for err in errors[:15]:
            print(f" - {err}")
    else:
        print(f"Linter passed! Output verified at {output_path}")

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Deletion Audit Pipeline")
    parser.add_argument("--sample", action="store_true", help="Run on sample_deletion_requests.csv")
    parser.add_argument("--no-ingest", action="store_true", help="Skip evidence ingestion pass")
    parser.add_argument("--output", type=str, default="output.csv", help="Path to write output CSV")
    parser.add_argument("--twice", action="store_true", help="Run twice to verify byte determinism")
    parser.add_argument("--diff", action="store_true", help="Diff outputs between runs")
    args = parser.parse_args()

    input_file = "sample_deletion_requests.csv" if args.sample else "deletion_requests.csv"
    out_file = "sample_output_pred.csv" if args.sample else args.output
    run_pipeline(input_csv_name=input_file, output_csv_name=out_file, ingest=not args.no_ingest)
