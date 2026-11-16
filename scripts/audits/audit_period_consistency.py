import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
"""Write a reproducible, read-only audit of adjacent-year fact values."""
import csv
from pathlib import Path

from src.agents.period_consistency import scan_period_consistency


def main() -> None:
    compared, issues = scan_period_consistency()
    destination = Path(__file__).resolve().parents[2] / "evaluation" / "audits" / "period_consistency_issues.csv"
    with destination.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=[
            "ticker", "scope", "report_type", "item_code_or_label", "year",
            "current_values", "next_prior_values", "unit", "ambiguous_rows",
            "current_docs", "next_docs",
        ])
        writer.writeheader()
        for issue in issues:
            writer.writerow(issue)
    print(f"Compared groups: {compared}; period_inconsistency: {len(issues)}; output: {destination}")


if __name__ == "__main__":
    main()
