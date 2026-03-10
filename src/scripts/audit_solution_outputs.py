#!/usr/bin/env python3
"""Audit solver output JSON files for correctness/completeness checks.

Checks performed:
- JSON/schema validity (root object + pareto_front extraction)
- Decision-vector dimensional consistency against instance
- Value domain checks for X/R/A/W and objective fields Z1/Z2/CV
- Duplicate objective points and internal dominance violations
- Basic completeness stats (feasible count, unique X patterns)

Usage:
  python src/scripts/audit_solution_outputs.py \
      --instance data/cv/cv_small_drnd.json \
      --solutions results/exp1/cv_small_*.json
"""

from __future__ import annotations

import argparse
import glob
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EPS = 1e-9


@dataclass
class AuditResult:
    path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def status(self) -> str:
        return "FAIL" if self.errors else "PASS"


def load_instance_meta(instance_path: Path) -> dict[str, Any]:
    data = json.loads(instance_path.read_text())
    dims = data.get("dimensions", {})
    nodes = data.get("nodes", {})

    num_i = int(dims.get("num_I", 0))
    num_h = int(dims.get("num_H", 0))
    num_j = int(dims.get("num_J", 0))

    demand_idx = nodes.get("demand_indices", [])
    hub_idx = nodes.get("hub_indices", [])
    origin_idx = nodes.get("origin_indices", [])

    if not num_i:
        num_i = len(demand_idx)
    if not num_h:
        num_h = len(hub_idx)
    if not num_j:
        num_j = len(origin_idx)

    return {
        "num_I": num_i,
        "num_H": num_h,
        "num_J": num_j,
        "demand_indices": demand_idx,
        "hub_indices": hub_idx,
        "origin_indices": origin_idx,
    }


def extract_front(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        pf = data.get("pareto_front")
        if isinstance(pf, list):
            return [x for x in pf if isinstance(x, dict)]
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def dominates(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if any(k not in a for k in ("Z1", "Z2")) or any(k not in b for k in ("Z1", "Z2")):
        return False
    az1, az2 = float(a["Z1"]), float(a["Z2"])
    bz1, bz2 = float(b["Z1"]), float(b["Z2"])
    return (az1 <= bz1 + EPS and az2 <= bz2 + EPS) and (
        az1 < bz1 - EPS or az2 < bz2 - EPS
    )


def is_finite_number(x: Any) -> bool:
    try:
        v = float(x)
    except Exception:
        return False
    return math.isfinite(v)


def audit_solution_file(path: Path, inst: dict[str, Any]) -> AuditResult:
    res = AuditResult(path=path)
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        res.errors.append(f"Invalid JSON: {exc}")
        return res

    front = extract_front(data)
    if not front:
        res.errors.append("Missing or empty pareto_front")
        return res

    num_i = inst["num_I"]
    num_h = inst["num_H"]

    feasible = 0
    unique_x: set[tuple[int, ...]] = set()
    obj_seen: set[tuple[float, float]] = set()

    for idx, s in enumerate(front):
        ctx = f"solution[{idx}]"

        for k in ("Z1", "Z2"):
            if k not in s:
                res.errors.append(f"{ctx}: missing {k}")
            elif not is_finite_number(s[k]):
                res.errors.append(f"{ctx}: non-finite {k}")

        if "CV" in s:
            if not is_finite_number(s["CV"]):
                res.errors.append(f"{ctx}: non-finite CV")
            elif float(s["CV"]) < -EPS:
                res.errors.append(f"{ctx}: CV is negative ({s['CV']})")
            elif float(s["CV"]) <= EPS:
                feasible += 1

        # X checks
        if "X" in s:
            x = s["X"]
            if not isinstance(x, list):
                res.errors.append(f"{ctx}: X must be a list")
            else:
                if len(x) != num_h:
                    res.errors.append(f"{ctx}: len(X)={len(x)} != num_H={num_h}")
                bad = [v for v in x if v not in (0, 1, False, True)]
                if bad:
                    res.errors.append(f"{ctx}: X has non-binary values")
                if isinstance(x, list) and len(x) == num_h:
                    unique_x.add(tuple(int(v) for v in x))
                    if sum(int(v) for v in x) < 1:
                        res.errors.append(f"{ctx}: no open hub in X")

        # R checks (if present)
        if "R" in s:
            r = s["R"]
            if not isinstance(r, list):
                res.errors.append(f"{ctx}: R must be a list")
            else:
                if len(r) != num_h:
                    res.errors.append(f"{ctx}: len(R)={len(r)} != num_H={num_h}")
                for rv in r:
                    if not is_finite_number(rv):
                        res.errors.append(f"{ctx}: R contains non-finite value")
                        break
                    fv = float(rv)
                    if fv < -EPS or fv > 1.0 + EPS:
                        res.errors.append(f"{ctx}: R value out of [0,1]: {fv}")
                        break

        # A checks (if present)
        if "A" in s:
            a = s["A"]
            if not isinstance(a, list):
                res.errors.append(f"{ctx}: A must be a list")
            else:
                if len(a) != num_i:
                    res.errors.append(f"{ctx}: len(A)={len(a)} != num_I={num_i}")
                for av in a:
                    if not isinstance(av, int):
                        res.errors.append(f"{ctx}: A contains non-int value")
                        break
                    if av < 0 or av >= num_h:
                        res.errors.append(f"{ctx}: A value out of hub range [0,{num_h-1}]")
                        break

        # W checks (if present)
        if "W" in s:
            w = s["W"]
            if not isinstance(w, list):
                res.errors.append(f"{ctx}: W must be a list")
            else:
                if len(w) != 6:
                    res.warnings.append(f"{ctx}: len(W)={len(w)} (expected 6 for PB-NSGA)")
                for wv in w:
                    if not is_finite_number(wv):
                        res.errors.append(f"{ctx}: W contains non-finite value")
                        break

        if "Z1" in s and "Z2" in s and is_finite_number(s["Z1"]) and is_finite_number(s["Z2"]):
            key = (round(float(s["Z1"]), 6), round(float(s["Z2"]), 6))
            if key in obj_seen:
                res.warnings.append(f"{ctx}: duplicate objective point {key}")
            obj_seen.add(key)

    # Dominance consistency among feasible points.
    feasible_pts = [s for s in front if float(s.get("CV", 0.0)) <= EPS]
    dominated_count = 0
    for i, a in enumerate(feasible_pts):
        for j, b in enumerate(feasible_pts):
            if i == j:
                continue
            if dominates(b, a):
                dominated_count += 1
                break
    if dominated_count:
        res.warnings.append(
            f"{dominated_count} feasible points are dominated within provided front"
        )

    res.info.append(f"pareto_points={len(front)}")
    res.info.append(f"feasible_points={feasible}")
    res.info.append(f"unique_x={len(unique_x)}")

    if feasible == 0:
        res.warnings.append("No feasible points found (CV<=0)")

    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit solver output JSON files.")
    ap.add_argument("--instance", required=True, help="Path to instance JSON")
    ap.add_argument(
        "--solutions",
        nargs="+",
        required=True,
        help="Solution JSON paths or globs",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on warnings too",
    )
    args = ap.parse_args()

    instance_path = Path(args.instance)
    if not instance_path.exists():
        print(f"[ERROR] Instance not found: {instance_path}")
        return 2

    inst = load_instance_meta(instance_path)

    files: list[Path] = []
    for pat in args.solutions:
      matches = [Path(p) for p in glob.glob(pat)]
      if matches:
          files.extend(matches)
      else:
          p = Path(pat)
          if p.exists():
              files.append(p)

    # deterministic order + unique
    files = sorted({f.resolve() for f in files})
    if not files:
        print("[ERROR] No solution files matched")
        return 2

    any_error = False
    any_warning = False

    print(f"[Audit] instance={instance_path}")
    print(f"[Audit] files={len(files)}")

    for f in files:
        r = audit_solution_file(f, inst)
        print(f"\n[{r.status()}] {f}")
        for m in r.info:
            print(f"  info: {m}")
        for m in r.warnings:
            any_warning = True
            print(f"  warn: {m}")
        for m in r.errors:
            any_error = True
            print(f"  err : {m}")

    if any_error:
        print("\n[Audit] FAILED: errors detected")
        return 1
    if args.strict and any_warning:
        print("\n[Audit] STRICT-FAIL: warnings detected")
        return 1

    print("\n[Audit] PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
