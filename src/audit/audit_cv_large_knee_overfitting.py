"""
audit_cv_large_knee_overfitting.py
====================================
Audits the CV-Large case-study claim that "three scenarios produce
identical solutions" and the related figure–text consistency.

Phases:
  0. Figure–text consistency: identify which Pareto solution (if any)
     matches the paper's claimed knee-point (Z1=$4.6M, Z2=43,453,
     hubs {H0, H1, H3, H11, H14, H15, H16, H19}) and which one
     populates `cv_large_flow.json`.
  1. Per-scenario data extraction from cv_large_flow.json.
  2. Cross-scenario diagnostic table: how much do the operational
     decisions actually differ?
  3. Verdict: Case A (overfitting), B (genuine robust), or
     C (data integrity broken).

Usage:
    cd <repo_root>
    python src/audit/audit_cv_large_knee_overfitting.py

Outputs:
    results/exp2/audit_knee_scenario_diff.csv
    src/audit/CV_LARGE_KNEE_OVERFITTING_AUDIT.md  (written separately)
"""

from __future__ import annotations
import csv
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SEED0       = REPO / "results/exp2/CV_large_seed0.json"
FLOW        = REPO / "results/exp2/cv_large_flow.json"
INSTANCE    = REPO / "data/cv/cv_large_drnd.json"
OUT_CSV     = REPO / "results/exp2/audit_knee_scenario_diff.csv"

# Paper's claimed knee-point
PAPER_Z1    = 4.6e6
PAPER_Z2    = 43_453
PAPER_HUBS  = {0, 1, 3, 11, 14, 15, 16, 19}    # H0..H19


# ── Phase 0: figure–text consistency ─────────────────────────────────────────

def phase0_consistency():
    print("="*78)
    print("PHASE 0 — FIGURE–TEXT CONSISTENCY CHECK")
    print("="*78)

    # 0a: enumerate Pareto front
    pf = json.load(open(SEED0))["pareto_front"]
    print(f"\nseed0 Pareto front size: {len(pf)}")
    print(f"\n  {'idx':>3} {'Z1 (M$)':>10} {'Z2 (k)':>10} {'CV':>6}  open hubs")
    for i, sol in enumerate(pf):
        open_h = sorted(k for k, x in enumerate(sol['X']) if x == 1)
        print(f"  {i:>3} {sol['Z1']/1e6:>10.2f} {sol['Z2']/1e3:>10.1f} "
              f"{sol.get('CV',0):>6.1f}  {open_h}")

    # 0b: which solution claims-the-paper?
    closest_obj = None; closest_obj_d = float('inf')
    closest_hubs = None; closest_hubs_jaccard = -1.0
    for i, sol in enumerate(pf):
        # objective distance (relative)
        d = abs(sol['Z1']-PAPER_Z1)/PAPER_Z1 + abs(sol['Z2']-PAPER_Z2)/PAPER_Z2
        if d < closest_obj_d:
            closest_obj_d, closest_obj = d, (i, sol)
        # hub-set Jaccard
        h = {k for k, x in enumerate(sol['X']) if x == 1}
        jac = len(h & PAPER_HUBS) / max(1, len(h | PAPER_HUBS))
        if jac > closest_hubs_jaccard:
            closest_hubs_jaccard, closest_hubs = jac, (i, sol, h)

    i, s = closest_obj
    print(f"\nClosest by Z1+Z2: idx {i}, Z1=${s['Z1']/1e6:.2f}M, Z2={s['Z2']/1e3:.1f}k "
          f"(rel.diff {closest_obj_d:.3f})")
    i, s, h = closest_hubs
    print(f"Closest by hub set: idx {i}, hubs={sorted(h)} "
          f"(Jaccard {closest_hubs_jaccard:.2f} vs paper)")
    paper_only = PAPER_HUBS - h
    sol_only = h - PAPER_HUBS
    print(f"  paper-claims but solution lacks: {sorted(paper_only)}")
    print(f"  solution has but paper omits:    {sorted(sol_only)}")

    # 0c: flow.json identification
    flow = json.load(open(FLOW))
    fmeta = flow['meta']
    fX = fmeta.get('X', [])
    fZ1 = fmeta.get('Z1', 0.0); fZ2 = fmeta.get('Z2', 0.0)
    fCV = fmeta.get('CV', 0.0)
    fhubs = sorted(k for k, x in enumerate(fX) if x == 1)
    print(f"\ncv_large_flow.json (drives figure):")
    print(f"  Z1=${fZ1/1e6:.2f}M  Z2={fZ2/1e3:.1f}k  CV={fCV:.2f}  hubs={fhubs}")
    print(f"  Feasible? {'YES' if fCV <= 1e-6 else 'NO (CV>0)'}")

    # 0d: flow vs Pareto match
    flow_match = None
    for i, sol in enumerate(pf):
        if sol['X'] == fX:
            flow_match = i
            break
    print(f"  Matches Pareto solution: {'idx '+str(flow_match) if flow_match is not None else 'NONE'}")

    return {
        "paper_z1": PAPER_Z1, "paper_z2": PAPER_Z2, "paper_hubs": sorted(PAPER_HUBS),
        "closest_obj_idx": closest_obj[0],
        "closest_obj_z1": closest_obj[1]['Z1'], "closest_obj_z2": closest_obj[1]['Z2'],
        "closest_obj_hubs": sorted(k for k, x in enumerate(closest_obj[1]['X']) if x == 1),
        "closest_hub_idx": closest_hubs[0], "closest_hub_jaccard": closest_hubs_jaccard,
        "flow_z1": fZ1, "flow_z2": fZ2, "flow_cv": fCV,
        "flow_hubs": fhubs, "flow_matches_pareto_idx": flow_match,
    }


# ── Phase 1+2: per-scenario data + diagnostic ────────────────────────────────

def phase1_2_per_scenario():
    print()
    print("="*78)
    print("PHASE 1+2 — PER-SCENARIO OPERATIONAL DECISIONS (from flow.json)")
    print("="*78)

    flow = json.load(open(FLOW))
    inst = json.load(open(INSTANCE))
    scens = flow['scenarios']
    inst_scens = inst['scenarios']
    n_S = len(scens)
    n_I = inst['dimensions']['num_I']
    n_J = inst['dimensions']['num_J']
    n_H = inst['dimensions']['num_H']
    n_M = inst['dimensions']['num_M']

    rows = []
    per_s = {}   # s → dict of metrics

    for si, sc in enumerate(scens):
        name = inst_scens[si]['name']
        y_ks = sc.get('y_ks', [])
        n_active = sum(1 for y in y_ks if y)

        da = sc.get('demand_assignments', [])      # list of {demand, hub} or similar
        oa = sc.get('origin_assignments', [])
        inv = sc.get('inventory_held', [])
        ts = sc.get('transshipment', [])           # list of edges [k,h,mode,vol]?

        # Modal mix from demand_assignments + transshipment
        # Try multiple shapes — be defensive
        truck = water = heli = 0
        ts_vol = 0.0
        # demand_assignments format detection
        for entry in da:
            if isinstance(entry, dict):
                m = entry.get('mode', entry.get('m', None))
                if m == 0: truck += 1
                elif m == 1: water += 1
                elif m == 2: heli += 1
            elif isinstance(entry, (list, tuple)) and len(entry) >= 3:
                m = entry[2]
                if m == 0: truck += 1
                elif m == 1: water += 1
                elif m == 2: heli += 1

        # transshipment volume
        for entry in ts:
            if isinstance(entry, dict):
                ts_vol += float(entry.get('volume', entry.get('flow', 0.0)))
            elif isinstance(entry, (list, tuple)) and len(entry) >= 4:
                ts_vol += float(entry[-1])

        # Hub set used (any hub assigned at least one demand or origin)
        hubs_used = set()
        for entry in da:
            if isinstance(entry, dict):
                hubs_used.add(entry.get('hub', entry.get('k', -1)))
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                hubs_used.add(entry[1])
        hubs_used.discard(-1)

        per_s[si] = {
            "name": name,
            "y_ks": y_ks,
            "n_active": n_active,
            "hubs_used": hubs_used,
            "n_demand_assigns": len(da),
            "n_origin_assigns": len(oa),
            "demand_assignments": da,
            "origin_assignments": oa,
            "truck": truck, "water": water, "heli": heli,
            "ts_vol": ts_vol, "ts_count": len(ts),
            "inv": inv,
        }

        print(f"\nScenario {si} ({name}):")
        print(f"  y_ks active count        : {n_active}/{n_H}")
        print(f"  hubs used (assigned)     : {sorted(hubs_used)}")
        print(f"  #demand assignments      : {len(da)}")
        print(f"  #origin assignments      : {len(oa)}")
        print(f"  modal mix (demand arcs)  : truck={truck} water={water} heli={heli}")
        print(f"  transshipment edges/vol  : {len(ts)} edges, {ts_vol:.0f} kg total")

    # ── Cross-scenario diff ──
    def da_hamming(s1, s2):
        # dict-of-dicts-keyed-by-demand comparison
        a = {}
        b = {}
        for e in per_s[s1]['demand_assignments']:
            if isinstance(e, dict):
                a[e.get('demand', e.get('i'))] = e.get('hub', e.get('k'))
            elif isinstance(e, (list, tuple)):
                a[e[0]] = e[1]
        for e in per_s[s2]['demand_assignments']:
            if isinstance(e, dict):
                b[e.get('demand', e.get('i'))] = e.get('hub', e.get('k'))
            elif isinstance(e, (list, tuple)):
                b[e[0]] = e[1]
        keys = set(a) | set(b)
        return sum(1 for k in keys if a.get(k) != b.get(k))

    def y_hamming(s1, s2):
        ya = per_s[s1]['y_ks']; yb = per_s[s2]['y_ks']
        return sum(1 for u, v in zip(ya, yb) if u != v)

    def jaccard(s1, s2):
        a = per_s[s1]['hubs_used']; b = per_s[s2]['hubs_used']
        return len(a & b) / max(1, len(a | b))

    pairs = [(0,1), (1,2), (0,2)]
    print()
    print("="*78)
    print("CROSS-SCENARIO DIFFERENCES")
    print("="*78)
    print()
    print(f"{'pair':>10}  {'da-Hamm':>10}  {'y-Hamm':>8}  "
          f"{'jaccard':>8}  {'modal-diff':>10}  {'tsvol-diff':>12}")
    for s1, s2 in pairs:
        da_h = da_hamming(s1, s2)
        y_h = y_hamming(s1, s2)
        jac = jaccard(s1, s2)
        modal_d = (abs(per_s[s1]['truck']-per_s[s2]['truck'])
                   + abs(per_s[s1]['water']-per_s[s2]['water'])
                   + abs(per_s[s1]['heli']-per_s[s2]['heli']))
        ts_d = abs(per_s[s1]['ts_vol']-per_s[s2]['ts_vol'])
        label = f"{per_s[s1]['name'][:6]}-{per_s[s2]['name'][:6]}"
        print(f"  {label:>10}  {da_h:>10}  {y_h:>8}  {jac:>8.3f}  "
              f"{modal_d:>10}  {ts_d:>12.0f}")
        rows.append({
            "pair": label, "da_hamming": da_h, "y_hamming": y_h,
            "jaccard": round(jac, 4), "modal_diff": modal_d,
            "ts_vol_diff": round(ts_d, 0),
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "pair", "da_hamming", "y_hamming", "jaccard", "modal_diff", "ts_vol_diff"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nSaved CSV: {OUT_CSV}")

    return per_s, rows


# ── Phase 3: verdict ─────────────────────────────────────────────────────────

def phase3_verdict(consistency, rows):
    print()
    print("="*78)
    print("PHASE 3 — VERDICT")
    print("="*78)

    flow_feasible = consistency["flow_cv"] <= 1e-6
    flow_matches_pareto = consistency["flow_matches_pareto_idx"] is not None
    paper_hub_match_jaccard = consistency["closest_hub_jaccard"]

    da_max = max(r['da_hamming'] for r in rows) if rows else 0
    y_max = max(r['y_hamming'] for r in rows) if rows else 0
    modal_max = max(r['modal_diff'] for r in rows) if rows else 0

    # Data-integrity issues take precedence over A/B classification
    issues = []
    if not flow_feasible:
        issues.append(
            f"flow.json represents an INFEASIBLE solution (CV={consistency['flow_cv']:.2f}); "
            f"figure visualises an out-of-Pareto-front point."
        )
    if not flow_matches_pareto:
        issues.append(
            "flow.json does NOT match any Pareto solution in seed0; "
            "the figure is decoupled from the live Pareto results."
        )
    if paper_hub_match_jaccard < 1.0:
        issues.append(
            f"Paper's hub list {{H0,H1,H3,H11,H14,H15,H16,H19}} matches NO Pareto "
            f"solution exactly (best Jaccard = {paper_hub_match_jaccard:.2f})."
        )

    if issues:
        print("\nDATA INTEGRITY ISSUES (must be fixed regardless of A/B/C verdict):")
        for it in issues:
            print(f"  ✗ {it}")

    # Now A/B classification on the cross-scenario diffs
    if da_max < 5 and y_max <= 3 and modal_max < 5:
        verdict = "CASE A — overfitting / poor scenario differentiation"
    elif da_max > 15 or y_max > 5 or modal_max >= 10:
        verdict = "CASE B — genuine cross-scenario differentiation"
    else:
        verdict = "CASE B (borderline) — moderate differentiation"

    print(f"\nVERDICT (cross-scenario only): {verdict}")
    print(f"  max demand-assignment Hamming = {da_max} / {sum(1 for _ in rows[0]) if rows else 0}")
    print(f"  max y_ks Hamming             = {y_max} / 20")
    print(f"  max modal-mix L1 diff        = {modal_max}")

    return verdict, issues


def main():
    consistency = phase0_consistency()
    per_s, rows = phase1_2_per_scenario()
    verdict, issues = phase3_verdict(consistency, rows)

    summary_path = REPO / "results/exp2/audit_knee_summary.json"
    with open(summary_path, "w") as f:
        json.dump({
            "consistency": consistency,
            "verdict": verdict,
            "issues": issues,
            "cross_scenario_rows": rows,
        }, f, indent=2, default=str)
    print(f"\nSaved JSON summary: {summary_path}")


if __name__ == "__main__":
    main()
