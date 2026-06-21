"""
solver_runner.py — Solver invocation and flow-preprocessing pipeline.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import streamlit as st

from visualizer.config import SOLVER_BIN, INF_SENTINEL

_ROOT = Path(__file__).resolve().parent.parent
_SELF = Path(__file__).resolve().parent


def sanitize_instance_for_solver(instance_path: str) -> Tuple[str, Optional[Path]]:
    """Replace non-finite floats with ±INF_SENTINEL so the solver's strict JSON parser accepts them."""
    with open(instance_path, encoding="utf-8") as f:
        data = json.load(f)
    found = False

    def _clean(obj):
        nonlocal found
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        if isinstance(obj, float) and not math.isfinite(obj):
            found = True
            return math.copysign(INF_SENTINEL, obj) if obj == obj else INF_SENTINEL
        return obj

    cleaned = _clean(data)
    if not found:
        return instance_path, None

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(cleaned, tmp, allow_nan=False)
    tmp.close()
    return tmp.name, Path(tmp.name)


def run_solver_pipeline(
    instance_path: str,
    result_path: Path,
    flows_dir: Path,
    pop: int,
    gen: int,
    seed: int,
    algo: str,
) -> bool:
    """Run PB-NSGA-II then preprocess_flows.py. Returns True on success."""
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with st.status("Running solver pipeline…", expanded=True) as status:
        solver_instance_path, tmp_path = sanitize_instance_for_solver(instance_path)
        if tmp_path is not None:
            st.write("Sanitizing non-finite values for the solver's strict JSON parser…")
        try:
            st.write(f"PB-NSGA-II: pop={pop}, gen={gen}, seed={seed}, algo={algo}")
            proc = subprocess.run(
                [str(SOLVER_BIN), solver_instance_path,
                 "--pop", str(pop), "--gen", str(gen),
                 "--seed", str(seed), "--algo", algo,
                 "--out", str(result_path)],
                cwd=_ROOT, capture_output=True, text=True,
            )
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

        if proc.returncode != 0:
            status.update(label="Solver failed", state="error")
            st.error(proc.stderr or "Solver exited with a non-zero status.")
            return False

        st.write("Generating flow/routing data…")
        flows_dir.mkdir(parents=True, exist_ok=True)
        proc2 = subprocess.run(
            [sys.executable, str(_SELF / "preprocess_flows.py"),
             "--result", str(result_path),
             "--instance", instance_path,
             "--out-dir", str(flows_dir),
             "--force"],
            cwd=_ROOT, capture_output=True, text=True,
        )
        if proc2.returncode != 0:
            status.update(label="Flow preprocessing failed", state="error")
            st.error(proc2.stderr or "preprocess_flows.py exited with a non-zero status.")
            return False

        status.update(label="Done", state="complete")
    return True
