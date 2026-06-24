"""
solver_runner.py — Flow-preprocessing pipeline for the DRND visualiser.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent
_SELF = Path(__file__).resolve().parent


def run_preprocess_flows(
    instance_path: str,
    result_path: str,
    flows_dir: Path,
) -> bool:
    """
    Regenerate per-solution flow files from *result_path* into *flows_dir*.

    Auto-detects all paths from the caller; runs preprocess_flows.py --force
    with live log streaming. Returns True on success.
    """
    flows_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(_SELF / "preprocess_flows.py"),
        "--result",   result_path,
        "--instance", instance_path,
        "--out-dir",  str(flows_dir),
        "--force",
    ]
    with st.status("Regenerating flow data…", expanded=True) as status:
        try:
            proc = subprocess.Popen(
                cmd, cwd=_ROOT,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
        except FileNotFoundError as exc:
            status.update(label="❌ preprocess_flows.py not found", state="error")
            st.error(str(exc))
            return False

        lines: list[str] = []
        log = st.empty()
        for line in proc.stdout:  # type: ignore[union-attr]
            lines.append(line.rstrip())
            log.code("\n".join(lines[-40:]))
        proc.wait()

        ok = proc.returncode == 0
        status.update(
            label="✅ Flow data ready" if ok else f"❌ Flow preprocessing failed (exit {proc.returncode})",
            state="complete" if ok else "error",
        )
        return ok


