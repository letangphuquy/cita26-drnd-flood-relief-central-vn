"""exp2_analyze_saa_oos.py - SAA/OOS diagnostic summary."""

import argparse
import json


def _load_evals(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("evaluations", [])


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def analyze(saa_path, oos_path, out_json=None):
    saa_data = _load_evals(saa_path)
    oos_data = _load_evals(oos_path)

    z1_diffs = [
        (sol["new_Z1"] - sol["orig_Z1"]) / max(1.0, sol["orig_Z1"]) * 100.0
        for sol in saa_data
    ]
    z2_diffs = [
        (sol["new_Z2"] - sol["orig_Z2"]) / max(1.0, sol["orig_Z2"]) * 100.0
        for sol in saa_data
    ]
    cv_saa = [sol["new_CV"] for sol in saa_data]
    cv_oos = [sol["new_CV"] for sol in oos_data]

    summary = {
        "saa": {
            "file": saa_path,
            "n_evaluations": len(saa_data),
            "mean_z1_diff_pct": _mean(z1_diffs),
            "mean_z2_diff_pct": _mean(z2_diffs),
            "mean_cv": _mean(cv_saa),
            "feasible_count": sum(1 for c in cv_saa if c <= 1e-9),
        },
        "oos": {
            "file": oos_path,
            "n_evaluations": len(oos_data),
            "mean_cv": _mean(cv_oos),
            "feasible_count": sum(1 for c in cv_oos if c <= 1e-9),
        },
    }

    print("--- SAA EVALUATION ---")
    print(f"File               : {saa_path}")
    print(f"Mean Z1 difference : {summary['saa']['mean_z1_diff_pct']:.2f}%")
    print(f"Mean Z2 difference : {summary['saa']['mean_z2_diff_pct']:.2f}%")
    print(f"Mean CV in SAA     : {summary['saa']['mean_cv']:.4f}")
    print(f"Feasible solutions : {summary['saa']['feasible_count']} / {summary['saa']['n_evaluations']}")

    print("\n--- OOS EVALUATION ---")
    print(f"File               : {oos_path}")
    print(f"Mean CV in OOS     : {summary['oos']['mean_cv']:.4f}")
    print(f"Feasible solutions : {summary['oos']['feasible_count']} / {summary['oos']['n_evaluations']}")

    if out_json:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"\n[Saved] {out_json}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze SAA/OOS evaluation outputs")
    parser.add_argument("--saa-eval", required=True, help="Path to *_saa_eval.json")
    parser.add_argument("--oos-eval", required=True, help="Path to *_oos_eval.json")
    parser.add_argument("--out", default=None, help="Optional path to write summary JSON")
    args = parser.parse_args()
    analyze(args.saa_eval, args.oos_eval, args.out)
