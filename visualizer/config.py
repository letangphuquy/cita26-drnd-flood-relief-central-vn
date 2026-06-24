"""
config.py — Centralised path configuration for the DRND visualiser.

Single source of truth for all dataset/version path decisions.
Import from here; never hardcode paths in views.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent

# ── Experiment pipeline paths (Tab 3 / experiments_view.py) ──────────────────
PATHS: Dict[str, Dict[str, Dict[str, Path]]] = {
    "CV Large": {
        "v1": {
            "instance": _ROOT / "data" / "cv" / "v1" / "cv_large_drnd.json",
            "results":  _ROOT / "results" / "exp2",
            "flows":    _ROOT / "results" / "exp2" / "flows",
            "saa_oos":  _ROOT / "results" / "exp2",
            "analysis": _ROOT / "results" / "exp2",
        },
        "v2": {
            "instance": _ROOT / "data" / "cv" / "v2" / "cv_large_drnd.json",
            "results":  _ROOT / "results" / "exp2" / "v2",
            "flows":    _ROOT / "results" / "exp2" / "v2" / "flows",
            "saa_oos":  _ROOT / "results" / "exp2" / "v2",
            "analysis": _ROOT / "results" / "exp2" / "v2",
        },
    },
    "CV Small": {
        "v1": {
            "instance": _ROOT / "data" / "cv" / "v1" / "cv_small_drnd.json",
            "results":  _ROOT / "results" / "exp1",
            "flows":    _ROOT / "results" / "exp1" / "flows",
            "analysis": _ROOT / "results" / "exp1",
        },
        "v2": {
            "instance": _ROOT / "data" / "cv" / "v2" / "cv_small_drnd.json",
            "results":  _ROOT / "results" / "exp1" / "v2",
            "flows":    _ROOT / "results" / "exp1" / "v2" / "flows",
            "analysis": _ROOT / "results" / "exp1" / "v2",
        },
    },
}

DATASETS: List[str] = list(PATHS.keys())
VERSIONS: List[str] = ["v1", "v2"]

# ── Shared UI / solver constants ──────────────────────────────────────────────
SC_NAMES:  List[str]       = ["Mild", "Severe", "Extreme"]
SC_PROBS:  List[float]     = [0.60, 0.30, 0.10]
SC_ICONS:  List[str]       = ["🌊", "⚠️", "🔴"]
SC_COLORS: List[str]       = ["#0277BD", "#E65100", "#B71C1C"]
MODE_NAMES: Dict[int, str] = {0: "Road 🚚", 1: "Water 🚤", 2: "Air 🚁"}

SOLVER_BIN  = _ROOT / "src" / "solver" / ("solver.exe" if sys.platform.startswith("win") else "solver")
DEFAULT_GEN: Dict[str, int] = {"CV Large": 500, "CV Small": 300}
INF_SENTINEL: float = 1e9


def _find_best_result(results_dir: Path, dataset_name: str) -> Optional[Path]:
    """Return first existing PB-NSGA seed file in *results_dir* for *dataset_name*."""
    if dataset_name == "CV Large":
        candidates = [results_dir / f"CV_large_seed{s}.json" for s in range(20)]
    else:
        candidates = (
            [results_dir / f"cv_small_pb_nsga_seed{s}.json" for s in range(20)]
            + [results_dir / "cv_small_pb_nsga.json"]
        )
    return next((p for p in candidates if p.exists()), None)


# ── Algorithm catalogue ───────────────────────────────────────────────────────

ALGO_LABELS: Dict[str, str] = {
    "pb_nsga":  "PB-NSGA",
    "milp_aws": "MILP-AWS",
}

# Filename for each non-PB-NSGA algorithm, keyed by (algo, dataset_name).
# CV-Large has no MILP result (solver doesn't scale); omit it here.
_ALGO_FILE: Dict[str, Dict[str, str]] = {
    "milp_aws": {"CV Small": "cv_small_milp_aws.json"},
}


def available_algorithms(dataset_name: str, version: str) -> List[str]:
    """Return ordered list of algorithm keys that have result files on disk."""
    p = PATHS[dataset_name][version]
    algos: List[str] = []
    if _find_best_result(p["results"], dataset_name):
        algos.append("pb_nsga")
    for algo, ds_map in _ALGO_FILE.items():
        fname = ds_map.get(dataset_name)
        if fname and (p["results"] / fname).exists():
            algos.append(algo)
    return algos


def get_explorer_config(
    dataset_name: str,
    version: str,
    algorithm: str = "pb_nsga",
) -> Dict[str, Any]:
    """
    Return paths dict for the Solution Explorer.

    Keys: ``instance`` (str), ``result`` (str | None), ``flows_dir`` (Path).
    Each algorithm gets its own flows dir so PB-NSGA and MILP-AWS flows
    never overwrite each other.
    """
    p = PATHS[dataset_name][version]

    if algorithm == "pb_nsga":
        result   = _find_best_result(p["results"], dataset_name)
        flows_dir = p["flows"]
    else:
        fname  = _ALGO_FILE.get(algorithm, {}).get(dataset_name)
        candidate = p["results"] / fname if fname else None
        result    = candidate if (candidate and candidate.exists()) else None
        flows_dir = p["flows"].parent / f"flows_{algorithm}"

    return {
        "instance":  str(p["instance"]),
        "result":    str(result) if result else None,
        "flows_dir": flows_dir,
    }
