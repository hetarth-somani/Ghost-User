"""Evaluation script benchmarking pipeline predictions against sample_output.csv.

Computes:
1. Status accuracy
2. Step-level field accuracy
3. Sequence accuracy (array-order strictly preserved, key order/whitespace normalized)
Outputs detailed failure analysis.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def evaluate_predictions(pred_csv: Path, target_csv: Path) -> dict[str, Any]:
    with open(pred_csv, "r", encoding="utf-8") as f:
        pred_rows = {r["case_id"]: r for r in csv.DictReader(f)}

    with open(target_csv, "r", encoding="utf-8") as f:
        target_rows = {r["case_id"]: r for r in csv.DictReader(f)}

    total_cases = len(target_rows)
    status_matches = 0
    sequence_matches = 0
    total_steps = 0
    step_field_matches = 0
    mismatches: list[dict[str, Any]] = []

    for case_id, tgt in target_rows.items():
        pr = pred_rows.get(case_id)
        if not pr:
            mismatches.append({"case_id": case_id, "error": "Missing from predictions"})
            continue

        tgt_status = tgt["deletion_status"]
        pr_status = pr["deletion_status"]

        if tgt_status == pr_status:
            status_matches += 1
        else:
            mismatches.append({
                "case_id": case_id,
                "error": "Status mismatch",
                "expected_status": tgt_status,
                "got_status": pr_status,
            })

        tgt_steps = json.loads(tgt["steps_json"])
        pr_steps = json.loads(pr["steps_json"])

        total_steps += len(tgt_steps)

        # Exact sequence check: array order must match strictly
        if len(tgt_steps) == len(pr_steps):
            steps_identical = True
            for i in range(len(tgt_steps)):
                ts = tgt_steps[i]
                ps = pr_steps[i]
                for key in ["phase", "operation", "system_id", "resource_id", "state", "evidence_id"]:
                    if ts.get(key) == ps.get(key):
                        step_field_matches += 1
                    else:
                        steps_identical = False
            if steps_identical:
                sequence_matches += 1
            else:
                mismatches.append({
                    "case_id": case_id,
                    "error": "Step sequence/field mismatch",
                    "expected_steps": tgt_steps,
                    "got_steps": pr_steps,
                })
        else:
            mismatches.append({
                "case_id": case_id,
                "error": f"Step count mismatch: expected {len(tgt_steps)}, got {len(pr_steps)}",
            })

    status_acc = (status_matches / total_cases) * 100 if total_cases else 0
    seq_acc = (sequence_matches / total_cases) * 100 if total_cases else 0
    field_acc = (step_field_matches / (total_steps * 6)) * 100 if total_steps else 0

    return {
        "total_cases": total_cases,
        "status_accuracy": status_acc,
        "sequence_accuracy": seq_acc,
        "field_accuracy": field_acc,
        "mismatches": mismatches,
    }


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    pred = repo_root / "sample_pred.csv"
    tgt = repo_root / "dataset" / "sample_output.csv"
    if pred.exists() and tgt.exists():
        res = evaluate_predictions(pred, tgt)
        print(f"Status Acc: {res['status_accuracy']:.1f}%")
        print(f"Sequence Acc: {res['sequence_accuracy']:.1f}%")
        print(f"Field Acc: {res['field_accuracy']:.1f}%")
        if res["mismatches"]:
            print(f"First 5 mismatches: {json.dumps(res['mismatches'][:5], indent=2)}")
