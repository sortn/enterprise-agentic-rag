from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "project"))

from evaluation.regression import compare_reports  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two evaluation reports")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path, default=Path("evaluation_regression.json"))
    parser.add_argument("--quality-tolerance", type=float, default=0.01)
    parser.add_argument("--latency-tolerance", type=float, default=0.10)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    result = compare_reports(
        baseline,
        candidate,
        quality_tolerance=args.quality_tolerance,
        latency_tolerance=args.latency_tolerance,
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("passed", "regression_count")}, indent=2))
    raise SystemExit(0 if result["passed"] else 2)


if __name__ == "__main__":
    main()
