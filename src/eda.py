"""Phase 1: Dataset Exploratory Data Analysis (EDA) and profiling.

Analyzes all CSVs and evidence files, validates referential integrity,
extracts sample_output conventions, and generates dataset_profile.json
and eda_report.md.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any


def analyze_dataset(repo_root: str | Path | None = None) -> dict[str, Any]:
    """Run full EDA over dataset/ and return profile dictionary."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent
    else:
        repo_root = Path(repo_root)

    dataset_dir = repo_root / "dataset"
    evidence_dir = dataset_dir / "evidence"

    profile: dict[str, Any] = {}

    # 1. Row counts & column schemas
    csv_files = [
        "deletion_requests.csv",
        "sample_deletion_requests.csv",
        "sample_output.csv",
        "user_identities.csv",
        "user_audit_log.csv",
        "system_activity.csv",
        "deletion_rules.csv",
        "evidence_files.csv",
    ]

    profile["csv_metrics"] = {}
    for filename in csv_files:
        filepath = dataset_dir / filename
        if not filepath.exists():
            continue
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            rows = list(reader)
            profile["csv_metrics"][filename] = {
                "row_count": len(rows),
                "columns": header,
            }

    # Assert exactly 518 deletion requests
    assert profile["csv_metrics"]["deletion_requests.csv"]["row_count"] == 518, (
        f"Expected 518 requests, found {profile['csv_metrics']['deletion_requests.csv']['row_count']}"
    )

    # 2. Deletion rules analysis
    rules_path = dataset_dir / "deletion_rules.csv"
    rules_map: dict[str, dict[str, str]] = {}
    with open(rules_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rules_map[row["data_category"]] = {
                "rule_id": row["rule_id"],
                "condition": row["condition"],
                "required_action": row["required_action"],
            }
    profile["deletion_rules"] = rules_map

    # 3. Evidence files manifest check
    evidence_manifest_path = dataset_dir / "evidence_files.csv"
    manifest_files: dict[str, dict[str, str]] = {}
    with open(evidence_manifest_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            manifest_files[row["file_id"]] = {
                "file_path": row["file_path"],
                "origin": row["origin"],
                "captured_at": row["captured_at"],
            }
    profile["evidence_manifest_count"] = len(manifest_files)

    # Walk actual evidence folder
    actual_files: set[str] = set()
    modality_counts: dict[str, int] = {}
    for p in evidence_dir.rglob("*"):
        if p.is_file():
            rel_path = p.relative_to(dataset_dir).as_posix()
            actual_files.add(rel_path)
            ext = p.suffix.lower()
            modality_counts[ext] = modality_counts.get(ext, 0) + 1

    profile["actual_evidence_count"] = len(actual_files)
    profile["modality_distribution"] = modality_counts

    # Verify manifest matches disk exactly
    manifest_rel_paths = {row["file_path"] for row in manifest_files.values()}
    profile["manifest_matches_disk"] = manifest_rel_paths == actual_files

    # 4. Extract sample_output conventions
    sample_output_path = dataset_dir / "sample_output.csv"
    sample_system_ids: set[str] = set()
    sample_resource_prefixes: set[str] = set()
    sample_operations: set[str] = set()
    sample_statuses: dict[str, int] = {}

    with open(sample_output_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = row["deletion_status"]
            sample_statuses[status] = sample_statuses.get(status, 0) + 1
            steps = json.loads(row["steps_json"])
            for step in steps:
                sample_system_ids.add(step.get("system_id", ""))
                res = step.get("resource_id", "")
                prefix = res.split("_")[0] if "_" in res else res
                sample_resource_prefixes.add(prefix)
                sample_operations.add(step.get("operation", ""))

    profile["sample_conventions"] = {
        "status_distribution": sample_statuses,
        "system_ids": sorted(list(sample_system_ids)),
        "resource_prefixes": sorted(list(sample_resource_prefixes)),
        "operations": sorted(list(sample_operations)),
    }

    # 5. Non-deletion requests detection (cases in deletion_requests)
    del_req_path = dataset_dir / "deletion_requests.csv"
    non_deletion_cases: list[str] = []
    with open(del_req_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            txt = row["request_text"].lower()
            if any(
                p in txt
                for p in [
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
                ]
            ):
                non_deletion_cases.append(row["case_id"])
    profile["detected_non_deletion_cases"] = non_deletion_cases

    return profile


def write_eda_outputs(repo_root: str | Path | None = None) -> None:
    """Generate dataset_profile.json and eda_report.md."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent
    else:
        repo_root = Path(repo_root)

    profile = analyze_dataset(repo_root)

    config_dir = repo_root / "config"
    config_dir.mkdir(exist_ok=True)
    with open(config_dir / "dataset_profile.json", "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

    eval_dir = repo_root / "evaluation"
    eval_dir.mkdir(exist_ok=True)
    report_path = eval_dir / "eda_report.md"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Exploratory Data Analysis (EDA) Report\n\n")
        f.write("## 1. Dataset Overview\n\n")
        f.write("| File | Rows | Columns |\n|---|---|---|\n")
        for fn, metrics in profile["csv_metrics"].items():
            f.write(f"| `{fn}` | {metrics['row_count']} | {', '.join(metrics['columns'])} |\n")

        f.write("\n## 2. Evidence Files Breakdown\n\n")
        f.write(f"- Total manifest files: **{profile['evidence_manifest_count']}**\n")
        f.write(f"- Total files on disk: **{profile['actual_evidence_count']}**\n")
        f.write(f"- Manifest ↔ Disk exact match: **{profile['manifest_matches_disk']}**\n\n")
        f.write("### Modality Distribution\n\n")
        for ext, count in profile["modality_distribution"].items():
            f.write(f"- `{ext}`: {count} files\n")

        f.write("\n## 3. Sample Output Ground Truth Conventions\n\n")
        f.write(f"- Status distribution: `{profile['sample_conventions']['status_distribution']}`\n")
        f.write(f"- Observed Systems: `{profile['sample_conventions']['system_ids']}`\n")
        f.write(f"- Observed Operations: `{profile['sample_conventions']['operations']}`\n")

        f.write("\n## 4. Non-Deletion Requests Identified\n\n")
        f.write(f"Detected {len(profile['detected_non_deletion_cases'])} explicit non-deletion requests: ")
        f.write(f"{', '.join(profile['detected_non_deletion_cases'])}\n")


if __name__ == "__main__":
    write_eda_outputs()
    print("EDA completed successfully.")
