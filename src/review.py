"""Interactive CLI for human review and case inspection."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


def review_case(case_id: str, repo_root: str | Path | None = None) -> None:
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent
    else:
        repo_root = Path(repo_root)

    out_file = repo_root / "output.csv"
    if not out_file.exists():
        out_file = repo_root / "sample_output_pred.csv"
    if not out_file.exists():
        print(f"No prediction output found at {out_file}")
        return

    with open(out_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r["case_id"] == case_id:
                print(f"--- Case: {case_id} ---")
                print(f"Status: {r['deletion_status']}")
                steps = json.loads(r["steps_json"])
                print(f"Total Steps: {len(steps)}")
                for s in steps:
                    print(f"  Step {s['step_no']} [{s['phase']}]: {s['operation']} on {s['system_id']}/{s['resource_id']} -> {s['state']} (evidence: {s['evidence_id']})")
                return

    print(f"Case {case_id} not found in {out_file.name}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        review_case(sys.argv[1])
    else:
        print("Usage: python src/review.py <case_id>")
