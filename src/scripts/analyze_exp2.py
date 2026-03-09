"""
analyze_exp2.py — Experiment 2: Case Study Central Vietnam
===========================================================
Analyses PB-NSGA results on the CV-Small and CV-Large instances.

Outputs:
  exp2_metrics.csv              — HV, IGD+ mean±std across 20 seeds
  exp2_hub_stability.csv        — hub selection frequency + scenario safety profile
  figures/<grp>_pareto.pdf      — combined Pareto front across seeds
  figures/<grp>_hub_freq.pdf    — bar chart of hub selection frequency
  figures/<grp>_hub_heatmap.pdf — hub × scenario risk heatmap (sensitivity)
  maps/<grp>_solution_map.pdf   — three representative solutions on CV map
                                  (calls map_solution.py; requires contextily)

The sensitivity analysis (hub_heatmap) answers:
  "Which hubs become unsafe under different disaster scenarios?"
This directly supports the managerial insights in the paper.

Usage:
  python scripts/analyze_exp2.py
  python scripts/analyze_exp2.py <results_dir> [<cv_data_dir>]
"""

import os
import sys
import json
import math
import csv
import statistics
import subprocess

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
    Returns {group: [(seed_int, path)]} for CV instances.
    Recognises: CV_{type}_seed{n}.json
    """
    groups = {}
    for fname in sorted(os.listdir(results_dir)):
        if not fname.endswith(".json"):
            continue
        base = fname[:-5]
        if not base.startswith("CV_"):
            continue
        parts = base.split("_")
        if len(parts) == 3 and parts[2].startswith("seed"):
            grp  = "_".join(parts[:2])       # CV_small or CV_large
            try:
                seed = int(parts[2].replace("seed", ""))
                groups.setdefault(grp, []).append((seed, os.path.join(results_dir, fname)))
            except ValueError:
                continue
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

def run(results_dir, out_dir, cv_data_dir=None):
    fig_dir  = os.path.join(out_dir, "figures")
    maps_dir = os.path.join(out_dir, "maps")
    os.makedirs(fig_dir,  exist_ok=True)
    os.makedirs(maps_dir, exist_ok=True)

    cv_groups = discover_cv_files(results_dir)
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

    metrics_rows   = []
    stability_rows_all = {}

    for grp in sorted(cv_groups.keys()):
        seeds = sorted(cv_groups[grp], key=lambda x: x[0])
        print(f"\n[{grp}] {len(seeds)} seed files found")

        # Load all seeds
        seed_results = []   # [(seed, pts, meta, pareto_full)]
        for seed, path in seeds:
            pts, meta, pareto_full = load_result(path)
            seed_results.append((seed, pts, meta, pareto_full))

        all_runs = [sr[1] for sr in seed_results]

        # Global normalisation
        _, bounds = normalize_points(all_runs)
        norm_runs, _ = normalize_points(all_runs, bounds=bounds)

        # Reference front: combined non-dominated front across all seeds
        combined  = dominant_pareto(all_runs)
        ref_norm, _ = normalize_points([combined], bounds=bounds)
        reference_norm = ref_norm[0] if ref_norm else []
        ref_pt = (1.1, 1.1)

        # Per-seed metrics
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

        hv_m,  hv_s  = _mean_std(hv_list)
        igd_m, igd_s = _mean_std(igd_list)
        sz_m,  sz_s  = _mean_std([float(s) for s in sz_list])
        rt_m,  rt_s  = _mean_std(rt_list)
        cpu_m, cpu_s = _mean_std(cpu_list)
        
        print(f"  HV={hv_m:.4f}±{hv_s:.4f}  IGD+={igd_m:.4f}±{igd_s:.4f}  "
              f"front_size={sz_m:.1f}±{sz_s:.1f}"
              + (f"  rt={rt_m:.1f}s" if rt_list else "")
              + (f"  cpu={cpu_m:.1f}s" if cpu_list else ""))

        metrics_rows.append({
            "instance":        grp,
            "algorithm":       "PB-NSGA",
            "n_runs":          len(seeds),
            "pareto_combined": len(combined),
            "pareto_mean":     f"{sz_m:.1f}",
            "pareto_std":      f"{sz_s:.1f}",
            "HV_mean":         f"{hv_m:.6f}",
            "HV_std":          f"{hv_s:.6f}",
            "IGDplus_mean":    f"{igd_m:.6f}",
            "IGDplus_std":     f"{igd_s:.6f}",
            "runtime_s_mean":  f"{rt_m:.4f}" if rt_list else "N/A",
            "runtime_s_std":   f"{rt_s:.4f}" if rt_list else "N/A",
            "cpu_time_s_mean": f"{cpu_m:.4f}" if cpu_list else "N/A",
            "cpu_time_s_std":  f"{cpu_s:.4f}" if cpu_list else "N/A",
        })

        # Pareto plot (combined front across seeds)
        plot_pareto(
            {"PB-NSGA (combined)": combined},
            os.path.join(fig_dir, f"{grp}_pareto.pdf"),
            title=f"Pareto Front — {grp.replace('_', ' ').title()} ({len(seeds)} seeds)"
        )

        # Sensitivity and stability analysis (requires instance file)
        inst_name   = "cv_small_drnd.json" if "small" in grp else "cv_large_drnd.json"
        inst_path   = os.path.join(cv_data_dir, inst_name)
        if not os.path.isfile(inst_path):
            print(f"  [Skip sensitivity] Instance not found: {inst_path}")
            continue

        inst = load_instance(inst_path)

        # Hub stability
        stab = hub_stability(seed_results, inst)
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
        best_seed_idx = hv_list.index(max(hv_list))
        best_seed, best_path = seeds[best_seed_idx]
        map_out = os.path.join(maps_dir, f"{grp}_solution_map.pdf")
        _call_map_solution(inst_path, best_path, map_out)

    # Write CSVs
    _write_csv(metrics_rows, os.path.join(out_dir, "exp2_metrics.csv"), [
        "instance", "algorithm", "n_runs",
        "pareto_combined", "pareto_mean", "pareto_std",
        "HV_mean", "HV_std", "IGDplus_mean", "IGDplus_std",
        "runtime_s_mean", "runtime_s_std",
        "cpu_time_s_mean", "cpu_time_s_std",
    ])

    all_stab = [r for rows in stability_rows_all.values() for r in rows]
    if all_stab:
        _write_csv(all_stab, os.path.join(out_dir, "exp2_hub_stability.csv"), [
            "instance", "hub_idx", "selection_pct",
            "selected_count", "total_solutions",
        ])

    print(f"\n[Exp2] Done. Results -> {out_dir}")


def _call_map_solution(inst_path, result_path, out_path):
    """Invoke map_solution.py via subprocess."""
    _script_dir  = os.path.dirname(os.path.abspath(__file__))
    map_script   = os.path.join(_script_dir, "map_solution.py")
    if not os.path.isfile(map_script):
        # Fallback: legacy location
        map_script = os.path.join(
            os.path.dirname(os.path.dirname(_script_dir)), "hlp-dataset", "map_solution.py"
        )
    if not os.path.isfile(map_script):
        print(f"  [Map] map_solution.py not found — skipping map for {out_path}")
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _script_dir  = os.path.dirname(os.path.abspath(__file__))
    _project_dir = os.path.dirname(_script_dir)
    _results_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_project_dir, "results", "exp2")
    _out_dir     = sys.argv[2] if len(sys.argv) > 2 else _results_dir
    _cv_data_dir = sys.argv[3] if len(sys.argv) > 3 else None
    run(_results_dir, _out_dir, _cv_data_dir)
