"""
exp2_analyze_case_study.py — Experiment 2: Case Study Central Vietnam (CV-Large)
=================================================================================
STATUS: Active — called from run_exp2_case_study.bat / run_exp2_case_study.sh
        (Step 2 of 3).

Analyses PB-NSGA results on CV instances and, when available, also
includes VNS-TS and GWO-HD seed results in the metric table.

Expected solver output file patterns under results/exp2/:
    - PB-NSGA:  cv_<size>_seed{n}.json
    - VNS-TS:   cv_<size>_vns_ts_seed{n}.json

Outputs (written to results/exp2/ and figures/):
    exp2_metrics.csv              — Shared-reference HV/IGD+ comparison metrics
                                                                 (combined front per algorithm) and run-level std
  exp2_hub_stability.csv        — hub selection frequency + scenario safety profile
  figures/<grp>_pareto.pdf      — combined Pareto front across seeds
  figures/<grp>_hub_freq.pdf    — bar chart of hub selection frequency
  figures/<grp>_hub_heatmap.pdf — hub × scenario risk heatmap (sensitivity)

If a sibling paper/ directory exists, the generated CSV outputs are also
exported there to keep manuscript-side data files synchronized.

Note: The solution map (1×3 composite) is generated separately by
      exp2_map_solution.py in Step 3 of run_exp2_case_study.bat.

The sensitivity analysis (hub_heatmap) answers:
  "Which hubs become unsafe under different disaster scenarios?"
This directly supports the managerial insights in the paper.

Usage (canonical, from project root):
    python src/scripts/exp2_analyze_case_study.py results/exp2 results/exp2 data/cv paper
    python src/scripts/exp2_analyze_case_study.py <results_dir> [<out_dir> [<cv_data_dir> [<paper_dir>]]]
"""

import os
import sys
import json
import math
import csv
import statistics
import subprocess
import shutil

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("[Warning] matplotlib not available — plots skipped.")


# ---------------------------------------------------------------------------
# Metric helpers (self-contained)
# ---------------------------------------------------------------------------

def load_result(path):
    with open(path) as fh:
        data = json.load(fh)
    # Filter: strictly feasible first, but if none available (CV > 0 globally), 
    # we take what the solver provided as its best (rank 1).
    pareto_json = data.get("pareto_front", [])
    has_strictly_feasible = any(sol.get("CV", 0) == 0 for sol in pareto_json)
    
    if has_strictly_feasible:
        raw_pts = [(sol["Z1"], sol["Z2"]) for sol in pareto_json if sol.get("CV", 0) == 0]
    else:
        # Fallback to all rank-1 solutions if no strictly feasible ones exist
        raw_pts = [(sol["Z1"], sol["Z2"]) for sol in pareto_json if sol.get("rank", 1) == 1]
    
    # De-duplicate raw_pts
    unique = {}
    for p in raw_pts:
        k = (round(p[0], 6), round(p[1], 6))
        if k not in unique:
            unique[k] = p
    pts = list(unique.values())
    
    return pts, data.get("meta", {}), pareto_json


def dominant_pareto(runs_pts):
    all_pts = [p for run in runs_pts for p in run]
    if not all_pts: return []
    nondom = []
    for p in all_pts:
        is_dom = False
        for q in all_pts:
            if q[0] <= p[0] and q[1] <= p[1] and (q[0] < p[0] or q[1] < p[1]):
                is_dom = True
                break
        if not is_dom:
            nondom.append(p)
    # Unique by rounding to 6 decimal places to avoid floating point noise
    unique = {}
    for p in nondom:
        k = (round(p[0], 6), round(p[1], 6))
        unique[k] = p
    return sorted(unique.values(), key=lambda p: p[0])


def normalize_points(pts_list, bounds=None):
    all_pts = [p for run in pts_list for p in run]
    if not all_pts:
        return pts_list, (0.0, 1.0, 0.0, 1.0)
    if bounds is None:
        z1_min = min(p[0] for p in all_pts)
        z1_max = max(p[0] for p in all_pts)
        z2_min = min(p[1] for p in all_pts)
        z2_max = max(p[1] for p in all_pts)
    else:
        z1_min, z1_max, z2_min, z2_max = bounds
    rz1 = max(z1_max - z1_min, 1e-6)
    rz2 = max(z2_max - z2_min, 1e-6)
    normed = [[(( p[0]-z1_min)/rz1, (p[1]-z2_min)/rz2) for p in run]
              for run in pts_list]
    return normed, (z1_min, z1_max, z2_min, z2_max)


def hypervolume_2d(pareto, ref=(1.1, 1.1)):
    """2D hypervolume indicator (Zitzler & Thiele, 1999)."""
    if not pareto:
        return 0.0
    pts = sorted(pareto, key=lambda p: p[0])
    hv, prev_z2 = 0.0, ref[1]
    for z1, z2 in pts:
        w = ref[0] - z1
        h = prev_z2 - z2
        if w > 0 and h > 0:
            hv += w * h
        prev_z2 = min(prev_z2, z2)
    return hv


def igd_plus(approx, reference):
    """IGD+ (Ishibuchi et al., 2015). Both args must be normalised."""
    if not reference:
        return 0.0
    if not approx:
        return 1.0
    total = sum(
        min(math.hypot(max(rz1 - az1, 0), max(rz2 - az2, 0))
            for az1, az2 in approx)
        for rz1, rz2 in reference
    )
    return total / len(reference)


def _mean_std(vals):
    if not vals:
        return float("nan"), float("nan")
    import numpy as np
    return float(np.mean(vals)), float(np.std(vals, ddof=1) if len(vals) > 1 else 0.0)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_cv_files(results_dir):
    """
    Returns {group: {algorithm: [(seed_int, path)]}} for CV instances.

    Recognised file names (case-insensitive):
      - cv_small_seed0.json              -> PB-NSGA
      - cv_large_seed12.json             -> PB-NSGA
    - cv_large_vns_ts_seed4.json       -> VNS-TS
    - cv_large_gwo_hd_seed2.json       -> GWO-HD
    """
    import re

    groups = {}
    pat = re.compile(r"^cv_(small|large)(?:_(vns_ts|gwo_hd))?_seed(\d+)\.json$", re.IGNORECASE)

    for fname in sorted(os.listdir(results_dir)):
        m = pat.match(fname)
        if not m:
            continue

        size, algo_tag, seed_s = m.groups()
        group = f"CV_{size.lower()}"
        if algo_tag == "vns_ts":
            algorithm = "VNS-TS"
        elif algo_tag == "gwo_hd":
            algorithm = "GWO-HD"
        else:
            algorithm = "PB-NSGA"
        seed = int(seed_s)

        groups.setdefault(group, {}).setdefault(algorithm, []).append(
            (seed, os.path.join(results_dir, fname))
        )

    return groups


# ---------------------------------------------------------------------------
# Hub stability and sensitivity analysis
# ---------------------------------------------------------------------------

def load_instance(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def hub_stability(seed_results, inst):
    """
    For each hub k, compute:
      - selection_pct  : % of all Pareto solutions (across seeds) that have X[k]=1
      - pareto_count   : total Pareto solutions analysed
    Returns: list of dicts, one per hub.
    """
    num_H = inst["dimensions"]["num_H"]
    hub_counts = [0] * num_H
    total_solutions = 0

    for _seed, _pts, _meta, pareto_full in seed_results:
        for sol in pareto_full:
            X = sol.get("X", [])
            for k in range(min(num_H, len(X))):
                if X[k] == 1:
                    hub_counts[k] += 1
            total_solutions += 1

    rows = []
    for k in range(num_H):
        rows.append({
            "hub_idx":       k,
            "selection_pct": 100.0 * hub_counts[k] / max(total_solutions, 1),
            "selected_count": hub_counts[k],
            "total_solutions": total_solutions,
        })
    return rows


def scenario_risk_profile(inst):
    """
    For each hub k × each scenario s, return the risk value.
    Returns: (hub_labels, scenario_labels, risk_matrix)
      risk_matrix[k][s] = risk of hub k in scenario s
    """
    num_H  = inst["dimensions"]["num_H"]
    num_S  = inst["dimensions"]["num_S"]
    chi    = inst["global_params"]["chi"]
    hub_idx = inst["nodes"]["hub_indices"]
    scenarios = inst["scenarios"]

    hub_labels = [f"H{k}" for k in range(num_H)]
    sc_labels  = [sc.get("name", f"S{s}") for s, sc in enumerate(scenarios)]

    risk_matrix = []
    for k in range(num_H):
        h_abs = hub_idx[k]
        row = [scenarios[s]["risk"][h_abs] for s in range(num_S)]
        risk_matrix.append(row)

    return hub_labels, sc_labels, risk_matrix, chi


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_pareto(series_dict, out_path, title):
    if not HAS_MPL or not series_dict:
        return
    fig, ax = plt.subplots(figsize=(6, 4.5))
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    for i, (label, pts) in enumerate(series_dict.items()):
        if not pts:
            continue
        pts_s = sorted(pts, key=lambda p: p[0])
        ax.plot([p[0] for p in pts_s], [p[1] for p in pts_s],
                color=colors[i % len(colors)], marker="o",
                linewidth=1.8, markersize=4, alpha=0.85, label=label)
    ax.set_xlabel("$Z_1$ — Expected Logistics Cost", fontsize=11)
    ax.set_ylabel("$Z_2$ — Expected Max Deprivation", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [Plot] {out_path}")


def plot_hub_frequency(stability_rows, out_path, title):
    if not HAS_MPL:
        return
    labels = [f"H{r['hub_idx']}" for r in stability_rows]
    values = [r["selection_pct"]  for r in stability_rows]

    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 0.6), 4))
    bars = ax.bar(labels, values, color="#1f77b4", alpha=0.85, edgecolor="white")
    ax.axhline(50, color="#d62728", lw=1.2, ls="--", label="50% threshold")
    ax.set_ylabel("Selection frequency (%)", fontsize=11)
    ax.set_xlabel("Hub candidate", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_ylim(0, 105)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [Plot] {out_path}")


def plot_hub_scenario_heatmap(hub_labels, sc_labels, risk_matrix, chi,
                              stability_rows, out_path, title):
    """
    Heatmap: rows = hubs (sorted by selection frequency), columns = scenarios.
    Cell colour = risk value; cells above chi are hatched (hub unsafe).
    Right-side bar shows selection frequency.
    """
    if not HAS_MPL:
        return

    # Sort hubs by selection frequency (descending)
    freq = {r["hub_idx"]: r["selection_pct"] for r in stability_rows}
    order = sorted(range(len(hub_labels)), key=lambda k: -freq.get(k, 0))

    sorted_labels  = [hub_labels[k] for k in order]
    sorted_risk    = [risk_matrix[k] for k in order]
    sorted_freq    = [freq.get(k, 0) for k in order]
    num_H = len(sorted_labels)
    num_S = len(sc_labels)

    fig, (ax_heat, ax_freq) = plt.subplots(
        1, 2, figsize=(4 + num_S * 1.2, max(4, num_H * 0.55)),
        gridspec_kw={"width_ratios": [num_S, 1.5]}
    )

    data = [[sorted_risk[k][s] for s in range(num_S)] for k in range(num_H)]
    im = ax_heat.imshow(data, cmap="RdYlGn_r", vmin=0, vmax=1, aspect="auto")

    # Hatch unsafe cells (risk > chi)
    for k in range(num_H):
        for s in range(num_S):
            if sorted_risk[k][s] > chi:
                rect = plt.Rectangle(
                    (s - 0.5, k - 0.5), 1, 1,
                    fill=False, hatch="///", edgecolor="black", linewidth=0.5
                )
                ax_heat.add_patch(rect)
            # Annotate with numeric risk
            ax_heat.text(s, k, f"{sorted_risk[k][s]:.2f}",
                         ha="center", va="center", fontsize=7,
                         color="black" if sorted_risk[k][s] < 0.6 else "white")

    ax_heat.set_xticks(range(num_S))
    ax_heat.set_xticklabels(sc_labels, fontsize=9)
    ax_heat.set_yticks(range(num_H))
    ax_heat.set_yticklabels(sorted_labels, fontsize=9)
    ax_heat.set_title(title, fontsize=11, fontweight="bold")
    plt.colorbar(im, ax=ax_heat, label="Risk level", fraction=0.046, pad=0.04)

    # Selection frequency bar (right panel)
    ax_freq.barh(range(num_H), sorted_freq, color="#1f77b4", alpha=0.8)
    ax_freq.axvline(50, color="#d62728", lw=1.0, ls="--")
    ax_freq.set_xlim(0, 105)
    ax_freq.set_yticks(range(num_H))
    ax_freq.set_yticklabels(sorted_labels, fontsize=9)
    ax_freq.set_xlabel("Selection\nfreq. (%)", fontsize=9)
    ax_freq.invert_yaxis()
    ax_freq.grid(axis="x", alpha=0.25)

    # Shared legend for hatch
    from matplotlib.patches import Patch
    legend_patches = [
        Patch(facecolor="white", edgecolor="black", hatch="///",
              label=f"Risk > χ={chi:.2f} (hub unsafe)"),
    ]
    fig.legend(handles=legend_patches, loc="lower center",
               fontsize=8, bbox_to_anchor=(0.5, -0.06))

    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [Plot] {out_path}")


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def _load_single_result(path):
    """Load a single JSON result as one pseudo-seed run if file exists."""
    if not os.path.isfile(path):
        return None
    pts, meta, pareto_full = load_result(path)
    return (0, pts, meta, pareto_full)


def _discover_exp1_cv_small_runs(exp1_dir):
    """
    Discover all available CV-small Exp1 result JSONs for tracked algorithms.
    Returns: {algorithm: [path, ...]}
    """
    import re

    out = {"PB-NSGA": [], "VNS-TS": [], "GWO-HD": []}
    if not os.path.isdir(exp1_dir):
        return out

    files = sorted(fn for fn in os.listdir(exp1_dir) if fn.endswith(".json"))

    pb_pat = re.compile(r"^cv_small_pb_nsga(?:_aega_.*)?\.json$", re.IGNORECASE)
    vns_pat = re.compile(r"^cv_small_vns_ts(?:_.*)?\.json$", re.IGNORECASE)
    # Supports both the tracked baseline file and historical compact runs.
    gwo_pat = re.compile(r"^cv_small_gwo(?:_hd|_[a-z])\.json$", re.IGNORECASE)

    for fn in files:
        path = os.path.join(exp1_dir, fn)
        if pb_pat.match(fn):
            out["PB-NSGA"].append(path)
        elif vns_pat.match(fn):
            out["VNS-TS"].append(path)
        elif gwo_pat.match(fn):
            out["GWO-HD"].append(path)

    return out


def run(results_dir, out_dir, cv_data_dir=None, paper_dir=None, max_seed=None, exp1_dir_override=None):
    fig_dir  = os.path.join(out_dir, "figures")
    maps_dir = os.path.join(out_dir, "maps")
    os.makedirs(fig_dir,  exist_ok=True)
    os.makedirs(maps_dir, exist_ok=True)

    cv_groups = discover_cv_files(results_dir)
    if max_seed is not None:
        for grp in cv_groups:
            for algo in cv_groups[grp]:
                cv_groups[grp][algo] = [
                    (s, p) for s, p in cv_groups[grp][algo] if s <= max_seed
                ]
    if not cv_groups:
        print(f"[Exp2] No CV result files found in {results_dir}")
        return

    # Infer cv_data_dir if not provided
    if cv_data_dir is None:
        _script_dir  = os.path.dirname(os.path.abspath(__file__))
        _project_dir = os.path.dirname(os.path.dirname(_script_dir))
        cv_data_dir  = os.path.join(_project_dir, "data", "cv")
        if not os.path.isdir(cv_data_dir):
            # Fallback to legacy location
            cv_data_dir = os.path.join(_project_dir, "data_prep")

    if paper_dir is None:
        _script_dir  = os.path.dirname(os.path.abspath(__file__))
        _project_dir = os.path.dirname(os.path.dirname(_script_dir))
        candidate_paper_dir = os.path.join(_project_dir, "paper")
        paper_dir = candidate_paper_dir if os.path.isdir(candidate_paper_dir) else None

    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _project_dir = os.path.dirname(os.path.dirname(_script_dir))
    exp1_dir = exp1_dir_override or os.path.join(_project_dir, "results", "exp1")

    metrics_rows   = []
    stability_rows_all = {}

    for grp in sorted(cv_groups.keys()):
        algo_seed_map = cv_groups[grp]

        # For CV-small, aggregate all available Exp1 runs for tracked
        # algorithms to improve statistical stability.
        if grp == "CV_small":
            exp1_runs = _discover_exp1_cv_small_runs(exp1_dir)
            for algorithm in ("PB-NSGA", "VNS-TS", "GWO-HD"):
                if exp1_runs.get(algorithm):
                    base_seed = 10000
                    algo_seed_map[algorithm] = [
                        (base_seed + i, p) for i, p in enumerate(exp1_runs[algorithm])
                    ]

        print(f"\n[{grp}] discovered algorithms: {', '.join(sorted(algo_seed_map.keys()))}")

        combined_for_plot = {}
        pb_seed_results = None
        pb_hv_list = None
        pb_seeds = None

        # Build a shared normalisation/reference space across all compared
        # algorithms for this instance so HV/IGD+ are directly comparable.
        algo_seed_results = {}
        all_runs_across_algorithms = []

        for algorithm in sorted(algo_seed_map.keys()):
            seeds = sorted(algo_seed_map[algorithm], key=lambda x: x[0])
            seed_results = []
            for entry in seeds:
                if len(entry) == 2:
                    seed, path = entry
                    pts, meta, pareto_full = load_result(path)
                    seed_results.append((seed, pts, meta, pareto_full))
                elif len(entry) == 4:
                    # Pseudo-seed injected from _load_single_result.
                    seed_results.append(entry)
                else:
                    raise RuntimeError(f"Unexpected seed entry format for {algorithm}: {entry}")
            algo_seed_results[algorithm] = seed_results
            all_runs_across_algorithms.extend([sr[1] for sr in seed_results])

        _, shared_bounds = normalize_points(all_runs_across_algorithms)
        combined_reference = dominant_pareto(all_runs_across_algorithms)
        ref_norm, _ = normalize_points([combined_reference], bounds=shared_bounds)
        reference_norm = ref_norm[0] if ref_norm else []
        ref_pt = (1.0, 1.0)

        for algorithm in sorted(algo_seed_map.keys()):
            seeds = sorted(algo_seed_map[algorithm], key=lambda x: x[0])
            print(f"  - {algorithm}: {len(seeds)} seed files")

            # Load all seeds for this algorithm
            seed_results = algo_seed_results[algorithm]   # [(seed, pts, meta, pareto_full)]

            all_runs = [sr[1] for sr in seed_results]

            # Reference front for plotting this algorithm alone.
            combined = dominant_pareto(all_runs)
            norm_runs, _ = normalize_points(all_runs, bounds=shared_bounds)

            # Per-seed metrics (used for variability reporting)
            hv_list, igd_list, sz_list, rt_list, cpu_list = [], [], [], [], []
            for pts, norm_pts, sr_tuple in zip(all_runs, norm_runs, seed_results):
                meta = sr_tuple[2]  # (seed, pts, meta, pareto_full)
                hv_list.append(hypervolume_2d(norm_pts, ref_pt))
                igd_list.append(igd_plus(norm_pts, reference_norm))
                sz_list.append(len(pts))
                for k in ("runtime_s", "elapsed_s"):
                    if k in meta:
                        rt_list.append(float(meta[k]))
                        break
                if "cpu_time_s" in meta:
                    cpu_list.append(float(meta["cpu_time_s"]))

            # Comparison metrics: evaluate each algorithm's combined front
            # against the same shared reference/front normalisation.
            combined_norm, _ = normalize_points([combined], bounds=shared_bounds)
            combined_norm_pts = combined_norm[0] if combined_norm else []
            hv_cmp = hypervolume_2d(combined_norm_pts, ref_pt)
            igd_cmp = igd_plus(combined_norm_pts, reference_norm)

            _, hv_s = _mean_std(hv_list)
            _, igd_s = _mean_std(igd_list)
            sz_m, sz_s = _mean_std([float(s) for s in sz_list])
            rt_m, rt_s = _mean_std(rt_list)
            cpu_m, cpu_s = _mean_std(cpu_list)

            print(f"    HV={hv_cmp:.4f}±{hv_s:.4f}  IGD+={igd_cmp:.4f}±{igd_s:.4f}  "
                  f"front_size={sz_m:.1f}±{sz_s:.1f}"
                  + (f"  rt={rt_m:.1f}s" if rt_list else "")
                  + (f"  cpu={cpu_m:.1f}s" if cpu_list else ""))

            metrics_rows.append({
                "instance":        grp,
                "algorithm":       algorithm,
                "n_runs":          len(seeds),
                "pareto_combined": len(combined),
                "pareto_mean":     f"{sz_m:.1f}",
                "pareto_std":      f"{sz_s:.1f}",
                "HV_mean":         f"{hv_cmp:.6f}",
                "HV_std":          f"{hv_s:.6f}",
                "IGDplus_mean":    f"{igd_cmp:.6f}",
                "IGDplus_std":     f"{igd_s:.6f}",
                "runtime_s_mean":  f"{rt_m:.4f}" if rt_list else "N/A",
                "runtime_s_std":   f"{rt_s:.4f}" if rt_list else "N/A",
                "cpu_time_s_mean": f"{cpu_m:.4f}" if cpu_list else "N/A",
                "cpu_time_s_std":  f"{cpu_s:.4f}" if cpu_list else "N/A",
            })

            combined_for_plot[f"{algorithm} (combined)"] = combined

            # Keep PB-NSGA seed context for legacy sensitivity/map outputs.
            if algorithm == "PB-NSGA":
                pb_seed_results = seed_results
                pb_hv_list = hv_list
                pb_seeds = seeds

        # Pareto plot: include all discovered algorithms for this instance
        total_runs = sum(len(algo_seed_map[a]) for a in algo_seed_map)
        plot_pareto(
            combined_for_plot,
            os.path.join(fig_dir, f"{grp}_pareto.pdf"),
            title=f"Pareto Front — {grp.replace('_', ' ').title()} ({total_runs} runs)"
        )

        # Sensitivity and stability analysis (PB-NSGA only, requires instance file)
        if pb_seed_results is None:
            print("  [Skip sensitivity] PB-NSGA seeds not found for this instance")
            continue

        inst_name   = "cv_small_drnd.json" if "small" in grp else "cv_large_drnd.json"
        inst_path   = os.path.join(cv_data_dir, inst_name)
        if not os.path.isfile(inst_path):
            print(f"  [Skip sensitivity] Instance not found: {inst_path}")
            continue

        inst = load_instance(inst_path)

        # Hub stability
        stab = hub_stability(pb_seed_results, inst)
        stability_rows_all[grp] = stab
        for r in stab:
            r["instance"] = grp
        plot_hub_frequency(
            stab,
            os.path.join(fig_dir, f"{grp}_hub_freq.pdf"),
            title=f"Hub Selection Frequency — {grp.replace('_', ' ').title()}"
        )

        # Scenario risk heatmap (sensitivity)
        hub_labels, sc_labels, risk_matrix, chi = scenario_risk_profile(inst)
        plot_hub_scenario_heatmap(
            hub_labels, sc_labels, risk_matrix, chi, stab,
            os.path.join(fig_dir, f"{grp}_hub_heatmap.pdf"),
            title=f"Hub Risk Profile across Scenarios — {grp.replace('_', ' ').title()}"
        )

        # Map visualisation: pick seed with highest HV for representative plot
        best_seed_idx = pb_hv_list.index(max(pb_hv_list))
        best_entry = pb_seeds[best_seed_idx]
        if len(best_entry) == 2:
            best_seed, best_path = best_entry
        else:
            best_seed = best_entry[0]
            # Pseudo-seed entry from Exp1 fallback (CV-small).
            if "small" in grp:
                best_path = os.path.join(exp1_dir, "cv_small_pb_nsga.json")
            else:
                print("  [Skip map] Could not infer PB-NSGA source path for representative seed")
                continue
        map_out = os.path.join(maps_dir, f"{grp}_solution_map.pdf")
        _call_map_solution(inst_path, best_path, map_out)

    # Write CSVs
    metrics_path = os.path.join(out_dir, "exp2_metrics.csv")
    _write_csv(metrics_rows, metrics_path, [
        "instance", "algorithm", "n_runs",
        "pareto_combined", "pareto_mean", "pareto_std",
        "HV_mean", "HV_std", "IGDplus_mean", "IGDplus_std",
        "runtime_s_mean", "runtime_s_std",
        "cpu_time_s_mean", "cpu_time_s_std",
    ])
    _export_csv_to_paper(metrics_path, paper_dir)

    all_stab = [r for rows in stability_rows_all.values() for r in rows]
    if all_stab:
        hub_stability_path = os.path.join(out_dir, "exp2_hub_stability.csv")
        _write_csv(all_stab, hub_stability_path, [
            "instance", "hub_idx", "selection_pct",
            "selected_count", "total_solutions",
        ])
        _export_csv_to_paper(hub_stability_path, paper_dir)

    print(f"\n[Exp2] Done. Results -> {out_dir}")


def _call_map_solution(inst_path, result_path, out_path):
    """Invoke map_solution_v2.py via subprocess."""
    _script_dir  = os.path.dirname(os.path.abspath(__file__))
    map_script   = os.path.join(_script_dir, "exp2_map_solution.py")
    if not os.path.isfile(map_script):
        print(f"  [Map] exp2_map_solution.py not found — skipping map for {out_path}")
        return
    cmd = [sys.executable, map_script,
           "--instance", inst_path,
           "--result",   result_path,
           "--out",      out_path]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"  [Map] map_solution.py failed: {e}")


def _write_csv(rows, path, fields):
    if not rows:
        return
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  [CSV] {path}")


def _export_csv_to_paper(src_path, paper_dir):
    if not paper_dir or not os.path.isdir(paper_dir):
        return
    dst_path = os.path.join(paper_dir, os.path.basename(src_path))
    shutil.copy2(src_path, dst_path)
    print(f"  [Export] {dst_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse as _ap
    _ap_parser = _ap.ArgumentParser(description="Exp2 Case Study Analysis", add_help=False)
    _ap_parser.add_argument("results_dir", nargs="?", default=None)
    _ap_parser.add_argument("out_dir", nargs="?", default=None)
    _ap_parser.add_argument("cv_data_dir", nargs="?", default=None)
    _ap_parser.add_argument("paper_dir", nargs="?", default=None)
    _ap_parser.add_argument("--max-seed", type=int, default=None,
                            help="Only include seeds 0..max_seed (inclusive) for matched-budget comparison")
    _ap_parser.add_argument("--exp1-dir", default=None,
                            help="Override directory for CV-Small results (default: {project}/results/exp1)")
    _ap_args, _ = _ap_parser.parse_known_args()
    _script_dir  = os.path.dirname(os.path.abspath(__file__))
    _project_dir = os.path.dirname(os.path.dirname(_script_dir))
    _results_dir = _ap_args.results_dir or os.path.join(_project_dir, "results", "exp2")
    _out_dir     = _ap_args.out_dir or _results_dir
    _cv_data_dir = _ap_args.cv_data_dir
    _paper_dir   = _ap_args.paper_dir
    run(_results_dir, _out_dir, _cv_data_dir, _paper_dir,
        max_seed=_ap_args.max_seed, exp1_dir_override=_ap_args.exp1_dir)
