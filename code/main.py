"""Top-level runnable entry point for code.zip package.

Processes dataset/deletion_requests.csv and outputs output.csv.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.pipeline import run_pipeline


def main() -> None:
    print("Executing Ghost Data Still Exists Deletion Audit Agent...")
    run_pipeline(
        input_csv_name="deletion_requests.csv",
        output_csv_name="output.csv",
        repo_root=repo_root,
        ingest=True,
    )
    print("Audit run complete. Results written to output.csv.")


if __name__ == "__main__":
    main()
