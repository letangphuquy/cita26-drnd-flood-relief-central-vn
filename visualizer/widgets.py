"""
panels.py — Shared UI helpers used across multiple tabs.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import streamlit as st

from visualizer.config import SC_NAMES, SC_PROBS, SC_ICONS

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src" / "visualizer") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src" / "visualizer"))

from solution_loader import Solution  # noqa: E402


def compute_knee(solutions: List[Solution]) -> int:
    """Tchebycheff knee on the normalised Pareto front."""
    z1s = [s.Z1 for s in solutions]
    z2s = [s.Z2 for s in solutions]
    z1_min, z1r = min(z1s), (max(z1s) - min(z1s)) or 1.0
    z2_min, z2r = min(z2s), (max(z2s) - min(z2s)) or 1.0
    return min(
        range(len(solutions)),
        key=lambda i: max(
            (solutions[i].Z1 - z1_min) / z1r,
            (solutions[i].Z2 - z2_min) / z2r,
        ),
    )


def scenario_selector(key: str, disabled: bool = False) -> int:
    """Three-button scenario selector widget. Returns selected scenario index 0/1/2."""
    idx = st.session_state.get("scenario_idx", 0)
    cols = st.columns(3)
    for i, (col, name, prob, icon) in enumerate(
        zip(cols, SC_NAMES, SC_PROBS, SC_ICONS)
    ):
        with col:
            if st.button(
                f"{icon} **{name}** — p={prob}",
                key=f"sc_{key}_{i}",
                use_container_width=True,
                type="primary" if idx == i else "secondary",
                disabled=disabled,
            ):
                st.session_state["scenario_idx"] = i
                st.rerun()
    return idx
