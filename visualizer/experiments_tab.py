"""
experiments_tab.py — Tab 3: Experiment Pipeline runner and results display.

Entry point: render(dataset_name, version_name, inst_raw, node_info)
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent
_VENV_PY = _ROOT / ".venv" / "bin" / "python3"
_SCRIPTS  = _ROOT / "src" / "scripts"

sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src" / "visualizer"))

from solution_loader import NodeInfo  # noqa: E402
from visualizer.config import PATHS, SOLVER_BIN, _find_best_result  # noqa: E402


# ── Experiment definitions ────────────────────────────────────────────────────

@dataclass
class Exp:
    id:     str
    name:   str
    desc:   str
    cmd_fn: Callable[[str, str], List[str]]
    out_fn: Callable[[str, str], Path]


def _py(script: str) -> List[str]:
    return [str(_VENV_PY), str(_SCRIPTS / script)]


def _p(dataset: str, version: str) -> Dict[str, Any]:
    return PATHS[dataset][version]


def _exp1_cmd(dataset: str, version: str) -> List[str]:
    p = _p(dataset, version)
    return [
        "bash", str(_ROOT / "run_exp1_baselines.sh"),
        "--instance",    str(p["instance"]),
        "--results-dir", str(p["results"]),
    ]


def _exp2_cmd(dataset: str, version: str) -> List[str]:
    # Returns the solver invocation for the first missing seed.
    # The ▶ Run button handler for EXP-2 uses _run_exp2() instead.
    p = _p(dataset, version)
    res = p["results"]
    missing = [k for k in range(20) if not (res / f"CV_large_seed{k}.json").exists()]
    seed = missing[0] if missing else 0
    return [
        str(SOLVER_BIN), str(p["instance"]),
        "--pop", "200", "--gen", "500",
        "--seed", str(seed),
        "--out", str(res / f"CV_large_seed{seed}.json"),
    ]


def _exp3_cmd(dataset: str, version: str) -> List[str]:
    p = _p("CV Large", version)  # always the 20-seed CV-Large pool
    data_prep = _ROOT / "data" / "prep"
    return _py("exp_oos_multiseed.py") + [
        "--results-dir", str(p["results"]),
        "--saa-data",    str(data_prep / "cv_large_saa100.json"),
        "--oos-data",    str(data_prep / "cv_large_oos10.json"),
    ]


def _exp4_cmd(dataset: str, version: str) -> List[str]:
    p = _p("CV Large", version)  # always CV-Large results + instance dir
    data_cv_dir = p["instance"].parent
    return _py("exp2_analyze_case_study.py") + [
        str(p["results"]), str(p["results"]), str(data_cv_dir),
    ]


def _exp5_cmd(dataset: str, version: str) -> List[str]:
    saa_data_dir = _ROOT / "data" / "prep" / "saa_convergence"
    results_dir  = _ROOT / "results" / "saa_convergence" / version
    figures_dir  = _ROOT / "figures" / version
    return _py("exp_saa_convergence.py") + [
        "--data-dir",    str(saa_data_dir),
        "--results-dir", str(results_dir),
        "--figures-dir", str(figures_dir),
    ]


def _exp6_cmd(dataset: str, version: str) -> List[str]:
    p = _p("CV Large", version)  # always CV-Large seed 0 + instance
    seed0 = p["results"] / "CV_large_seed0.json"
    out   = _ROOT / "figures" / version / "cv_large_map_detailed.pdf"
    return _py("exp2_map_solution.py") + [
        "--instance", str(p["instance"]),
        "--result",   str(seed0),
        "--out",      str(out),
    ]


def _exp7_cmd(dataset: str, version: str) -> List[str]:
    p = _p("CV Large", version)  # always CV-Large results, flows, instance
    out = _ROOT / "narrative_data.json"
    return [str(_VENV_PY), str(_ROOT / "visualizer" / "narrative_data.py"),
            "--results",  str(p["results"]),
            "--flows",    str(p["flows"]),
            "--instance", str(p["instance"]),
            "--out",      str(out)]


def _exp1_out(dataset: str, version: str) -> Path:
    return _p(dataset, version)["results"] / "cv_small_metrics.csv"


def _exp2_out(dataset: str, version: str) -> Path:
    return _p(dataset, version)["results"] / "CV_large_seed19.json"


def _exp3_out(dataset: str, version: str) -> Path:
    return _p("CV Large", version)["results"] / "CV_large_seed19_saa_eval.json"


def _exp4_out(dataset: str, version: str) -> Path:
    return _p("CV Large", version)["results"] / "exp2_metrics.csv"


def _exp5_out(dataset: str, version: str) -> Path:
    return _ROOT / "results" / "saa_convergence" / version / "convergence_summary.csv"


def _exp6_out(dataset: str, version: str) -> Path:
    return _ROOT / "figures" / version / "cv_large_map_detailed.pdf"


def _exp7_out(dataset: str, version: str) -> Path:
    return _ROOT / "narrative_data.json"


# Dataset constraint per experiment (None = runnable from either sidebar selection).
# EXP-3/4/6/7 pin internally to CV-Large paths so no constraint is needed.
_EXP_DATASET: Dict[str, str] = {
    "EXP-1": "CV Small",
    "EXP-2": "CV Large",
}

_EXPS: List[Exp] = [
    Exp("EXP-1", "CV-Small baseline comparison",
        "Greedy · VNS-TS · GWO-HD · MILP-AWS · PB-NSGA on CV-Small (seed 15); evaluate HV/IGD+",
        _exp1_cmd, _exp1_out),
    Exp("EXP-2", "CV-Large 20-seed PB-NSGA",
        "Run solver seeds 0–19 on CV-Large instance (may take ~2 hrs)",
        _exp2_cmd, _exp2_out),
    Exp("EXP-3", "OOS/SAA multi-seed evaluation",
        "Evaluate all 20 seeds on SAA-100 training + OOS-10 adversarial datasets",
        _exp3_cmd, _exp3_out),
    Exp("EXP-4", "Aggregate analysis",
        "Hub stability · Pareto trade-off · scenario sensitivity (CV-Large)",
        _exp4_cmd, _exp4_out),
    Exp("EXP-5", "SAA N-sensitivity",
        "Replication-based SAA convergence study on CV-Small",
        _exp5_cmd, _exp5_out),
    Exp("EXP-6", "Solution map (1×3 composite)",
        "High-fidelity Matplotlib network map across three scenarios",
        _exp6_cmd, _exp6_out),
    Exp("EXP-7", "Extract narrative_data.json",
        "Compute all Block 1–10 narrative query keys from 20-seed pool",
        _exp7_cmd, _exp7_out),
]


# ── Streaming runner ──────────────────────────────────────────────────────────

def _stream_run(cmd: List[str], label: str) -> bool:
    """Run *cmd* as subprocess with live log streaming inside st.status()."""
    with st.status(f"Running {label}…", expanded=True) as status:
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(_ROOT),
            )
        except FileNotFoundError as e:
            status.update(label=f"❌ {label} — command not found", state="error")
            st.error(str(e))
            return False

        lines: List[str] = []
        log = st.empty()
        for line in proc.stdout:  # type: ignore[union-attr]
            lines.append(line.rstrip())
            log.code("\n".join(lines[-40:]))
        proc.wait()

        ok = proc.returncode == 0
        status.update(
            label=f"{'✅' if ok else '❌'} {label}{'.' if ok else f' (exit {proc.returncode})'}",
            state="complete" if ok else "error",
        )
        return ok


# ── Shared: flow postprocessing for any PB-NSGA result ───────────────────────

def _postprocess_flows(dataset: str, version: str) -> None:
    """Regenerate flow files for the best available PB-NSGA result in the results dir."""
    p = _p(dataset, version)
    result_file = _find_best_result(p["results"], dataset)
    if result_file is None:
        st.warning("No PB-NSGA result file found — skipping flow preprocessing.")
        return
    st.info(f"Preprocessing flows for `{result_file.name}`…")
    ok = _stream_run(
        [sys.executable, str(Path(__file__).parent / "preprocess_flows.py"),
         "--result",   str(result_file),
         "--instance", str(p["instance"]),
         "--out-dir",  str(p["flows"]),
         "--force"],
        "Flow preprocessing",
    )
    if ok:
        st.success(f"Flows written to `{p['flows'].relative_to(_ROOT)}`")


# ── EXP-1 special handler — baseline run + flow preprocessing ────────────────

def _run_exp1(dataset: str, version: str) -> None:
    """Run all baselines via run_exp1_baselines.sh, then preprocess flows for PB-NSGA result."""
    ok = _stream_run(_exp1_cmd(dataset, version), "CV-Small baseline comparison")
    if ok:
        _postprocess_flows(dataset, version)


# ── EXP-2 multi-seed special handler ─────────────────────────────────────────

def _run_exp2(dataset: str, version: str, max_seed: int) -> None:
    """Run solver for each missing seed up to *max_seed* with live streaming."""
    p = _p(dataset, version)
    res = p["results"]
    missing = [k for k in range(max_seed + 1)
               if not (res / f"CV_large_seed{k}.json").exists()]

    if not missing:
        st.success(f"All seeds 0–{max_seed} already exist in {res.relative_to(_ROOT)}")
        return

    st.info(f"Running {len(missing)} missing seed(s): {missing}")
    for seed in missing:
        out = res / f"CV_large_seed{seed}.json"
        cmd = [
            str(SOLVER_BIN), str(p["instance"]),
            "--pop", "200", "--gen", "500",
            "--seed", str(seed),
            "--out", str(out),
        ]
        ok = _stream_run(cmd, f"EXP-2 seed {seed}")
        if not ok:
            st.error(f"Seed {seed} failed — stopping multi-seed run.")
            return

    _postprocess_flows(dataset, version)


# ── Status check ─────────────────────────────────────────────────────────────

def _status_icon(exp: Exp, dataset: str, version: str) -> Tuple[str, str]:
    out = exp.out_fn(dataset, version)
    if out.exists():
        rel = out.relative_to(_ROOT) if out.is_relative_to(_ROOT) else out
        return "✅", f"`{rel.name}`"
    return "⏳", "not yet run"


# ── PDF / figure rendering ────────────────────────────────────────────────────

def _render_pdf_or_download(path: Path, caption: str) -> None:
    if not path.exists():
        st.caption(f"_{caption}: not generated yet_")
        return
    try:
        from pdf2image import convert_from_path  # noqa: PLC0415
        imgs = convert_from_path(str(path), dpi=150, first_page=1, last_page=1)
        st.image(imgs[0], caption=caption, use_container_width=True)
    except Exception:
        st.download_button(
            f"⬇ Download {caption}",
            data=path.read_bytes(),
            file_name=path.name,
            mime="application/pdf",
            key=f"dl_{path.stem}",
        )


# ── Risk heatmap (always renderable — built from inst_raw) ───────────────────

def _risk_heatmap_fig(inst_raw: Dict[str, Any], node_info: NodeInfo):
    try:
        import plotly.graph_objects as go  # noqa: PLC0415
    except ImportError:
        return None

    hub_globals = node_info.hub_indices
    chi = float(inst_raw.get("global_params", {}).get("chi", 0.70))
    scenarios = inst_raw.get("scenarios", [])
    sc_labels = ["Mild", "Severe", "Extreme"]

    hub_names = [
        node_info.names[g] if g < len(node_info.names) else f"H{k}"
        for k, g in enumerate(hub_globals)
    ]

    z_values = []
    for k, g in enumerate(hub_globals):
        row = []
        for sc_idx in range(min(3, len(scenarios))):
            r = float(scenarios[sc_idx].get("hub_risk", {}).get(str(g), 0.0))
            row.append(r)
        z_values.append(row)

    fig = go.Figure(go.Heatmap(
        z=z_values,
        x=sc_labels,
        y=hub_names,
        colorscale=[[0, "#1a9850"], [chi, "#fee08b"], [1, "#d73027"]],
        zmin=0, zmax=1,
        colorbar=dict(title="Risk", tickvals=[0, chi, 1],
                      ticktext=["0", f"χ={chi}", "1"]),
        hovertemplate="Hub: %{y}<br>Scenario: %{x}<br>Risk: %{z:.3f}<extra></extra>",
    ))
    # Horizontal line at chi threshold
    fig.add_hline(
        y=chi * (len(hub_names) - 1),  # approximate y position
        line=dict(color="rgba(200,0,0,0.4)", width=1, dash="dash"),
    )
    fig.update_layout(
        title=f"Hub flood risk by scenario (χ = {chi:.2f} threshold)",
        height=max(300, 28 * len(hub_names) + 80),
        margin=dict(l=160, r=40, t=48, b=40),
        xaxis_title="Flood scenario",
        yaxis_title="",
    )
    return fig


# ── Figure paths helper ───────────────────────────────────────────────────────

def _fig_paths(dataset: str, version: str) -> Dict[str, Path]:
    p = _p(dataset, version)
    res = p["results"]
    fig_v = _ROOT / "figures" / version
    return {
        "pareto":   res / "exp2_pareto_tradeoff.pdf",
        "sol_map":  fig_v / "cv_large_map_detailed.pdf",
        "saa_conv": _ROOT / "results" / "saa_convergence" / version / "saa_convergence.pdf",
        "hub_freq": res / "CV_large_hub_freq.pdf",
        "metrics":  _p("CV Small", version)["results"] / "cv_small_metrics.csv",
    }


# ── Main render ───────────────────────────────────────────────────────────────

def render(
    dataset_name: str,
    version_name: str,
    inst_raw: Dict[str, Any],
    node_info: NodeInfo,
) -> None:
    """Tab 3 entry point. Called from app.py with sidebar-selected dataset/version."""

    st.subheader("🔬 Experiment Pipeline")
    st.caption(
        f"Dataset: **{dataset_name}** · Version: **{version_name}**  "
        "— buttons stream live output below each row."
    )

    # ── Pipeline table ────────────────────────────────────────────────────────
    ss = st.session_state
    ss.setdefault("exp2_max_seed", 19)

    for exp in _EXPS:
        icon, note = _status_icon(exp, dataset_name, version_name)

        with st.container():
            c0, c1, c2, c3 = st.columns([1, 6, 2, 1])
            c0.markdown(f"**{exp.id}**")
            c2.markdown(f"{icon} {note}")

            required = _EXP_DATASET.get(exp.id)
            if required and dataset_name != required:
                c1.markdown(f"**{exp.name}**  \n_{exp.desc}_")
                c3.markdown(f"_{required} only_")
            else:
                if exp.id == "EXP-2":
                    c1.markdown(f"**{exp.name}**  \n_{exp.desc}_")
                    ss["exp2_max_seed"] = int(c1.number_input(
                        "Run seeds 0 –", min_value=0, max_value=19,
                        value=int(ss["exp2_max_seed"]),
                        key="exp2_max_seed_input",
                    ))
                else:
                    c1.markdown(f"**{exp.name}**  \n_{exp.desc}_")

                if c3.button("▶ Run", key=f"run_{exp.id}"):
                    if exp.id == "EXP-1":
                        if version_name == "v1":
                            st.error(
                                "EXP-1 v1 results are canonical and immutable. "
                                "Switch to **v2** in the sidebar to run.",
                                icon="🔒",
                            )
                        else:
                            _run_exp1(dataset_name, version_name)
                    elif exp.id == "EXP-2":
                        _run_exp2(dataset_name, version_name, int(ss["exp2_max_seed"]))
                    else:
                        _stream_run(exp.cmd_fn(dataset_name, version_name), exp.name)
                    st.rerun()

    # ── Figure gallery ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📊 Results & Figures")

    paths = _fig_paths(dataset_name, version_name)

    # Table 4-1: CV-Small algorithm comparison
    metrics_path = paths["metrics"]
    if metrics_path.exists():
        try:
            import pandas as pd  # noqa: PLC0415
            df = pd.read_csv(metrics_path)
            styled = df.style
            if "hv_mean" in df.columns:
                styled = styled.highlight_max(subset=["hv_mean"], color="#c8e6c9")
            for col in ("igd_mean", "wall_s", "cpu_s"):
                if col in df.columns:
                    styled = styled.highlight_min(subset=[col], color="#c8e6c9",
                                                  props="color: inherit")
            st.markdown("**Table 4-1 — Algorithm comparison (CV-Small)**")
            st.dataframe(styled, use_container_width=True)
        except Exception as e:
            st.warning(f"Could not render metrics table: {e}")
    else:
        st.caption("_Table 4-1: run EXP-1 to generate `cv_small_metrics.csv`_")

    # Risk heatmap (Fig 4-6) — always renderable
    st.markdown("**Fig 4-6 — Hub flood risk heatmap**")
    fig = _risk_heatmap_fig(inst_raw, node_info)
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("_plotly not available_")

    # PDF figures in 2-column layout
    st.markdown("**Figures**")
    col_a, col_b = st.columns(2)
    with col_a:
        _render_pdf_or_download(paths["pareto"],   "Fig 1 — Pareto fronts")
        _render_pdf_or_download(paths["saa_conv"], "Fig 3 — SAA convergence")
    with col_b:
        _render_pdf_or_download(paths["sol_map"],  "Fig 2 — Solution map (1×3)")
        _render_pdf_or_download(paths["hub_freq"], "Fig 4-5 — Hub selection frequency")

    # Narrative data viewer
    st.divider()
    nd_path = _ROOT / "narrative_data.json"
    if nd_path.exists():
        st.markdown("**Narrative data** (`narrative_data.json`)")
        with open(nd_path, encoding="utf-8") as f:
            nd = json.load(f)
        c1, c2 = st.columns([3, 1])
        with c1:
            st.json(nd, expanded=False)
        with c2:
            st.download_button(
                "⬇ narrative_data.json",
                data=json.dumps(nd, indent=2, ensure_ascii=False).encode(),
                file_name="narrative_data.json",
                mime="application/json",
                key="dl_narrative",
            )
    else:
        st.caption("_Run EXP-7 to generate `narrative_data.json`_")
