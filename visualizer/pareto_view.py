"""
pareto_view.py — Build an interactive Plotly Pareto scatter figure.

Usage in Streamlit:
    fig = build_pareto_fig(solutions, selected_idx=2)
    event = st.plotly_chart(fig, on_select="rerun", key="pareto")
    if event.selection.points:
        idx = int(event.selection.points[0].customdata[0])
"""
from __future__ import annotations

from typing import List, Optional
import sys
from pathlib import Path

import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "visualizer"))
from solution_loader import Solution

# ── colours ───────────────────────────────────────────────────────────────────
_COL_PF       = "#2196F3"   # blue  — Pareto optimal
_COL_FEASIBLE = "#90CAF9"   # light blue — non-Pareto feasible
_COL_SELECTED = "#FF5722"   # orange-red — selected point
_MODE_LABELS  = {0: "Road", 1: "Water", 2: "Air"}


def build_pareto_fig(
    solutions: List[Solution],
    selected_idx: Optional[int] = None,
    show_all_feasible: bool = False,
    title: str = "Pareto Front — Z1 vs Z2",
) -> go.Figure:
    """
    Build an interactive Plotly scatter of the Pareto front.

    Parameters
    ----------
    solutions       : List of Solution objects (pareto_front preferred).
    selected_idx    : Index in *solutions* to highlight.
    show_all_feasible: If True, non-rank-1 feasible solutions shown lighter.
    title           : Figure title.

    Returns a go.Figure ready for st.plotly_chart.
    """
    pf = [s for s in solutions if s.rank == 1 and s.CV == 0.0]
    feas = [s for s in solutions if s not in pf and s.CV == 0.0] if show_all_feasible else []

    fig = go.Figure()

    # Background feasible cloud
    if feas:
        fig.add_trace(go.Scatter(
            x=[s.Z1 for s in feas],
            y=[s.Z2 for s in feas],
            mode="markers",
            marker=dict(color=_COL_FEASIBLE, size=7, opacity=0.5),
            name="Feasible (non-PF)",
            hovertemplate="Z1=%{x:,.0f}<br>Z2=%{y:,.0f}<extra>Non-Pareto</extra>",
        ))

    # Pareto front — clickable
    if pf:
        hover = [
            f"<b>Solution {i}</b><br>"
            f"Z1 (cost): {s.Z1:,.0f}<br>"
            f"Z2 (depriv): {s.Z2:,.0f}<br>"
            f"Open hubs: {s.num_open_hubs}<br>"
            f"Rank: {s.rank}"
            for i, s in enumerate(pf)
        ]
        fig.add_trace(go.Scatter(
            x=[s.Z1 for s in pf],
            y=[s.Z2 for s in pf],
            mode="markers+lines",
            marker=dict(color=_COL_PF, size=10, line=dict(width=1.5, color="white")),
            line=dict(color=_COL_PF, width=1, dash="dot"),
            name=f"Pareto front ({len(pf)})",
            customdata=[[i] for i in range(len(pf))],
            hovertemplate="%{text}<extra></extra>",
            text=hover,
        ))

    # Selected point overlay
    if selected_idx is not None and 0 <= selected_idx < len(pf):
        s = pf[selected_idx]
        fig.add_trace(go.Scatter(
            x=[s.Z1], y=[s.Z2],
            mode="markers",
            marker=dict(color=_COL_SELECTED, size=16, symbol="star",
                        line=dict(width=1.5, color="white")),
            name=f"Selected #{selected_idx}",
            hovertemplate=f"<b>Selected</b><br>Z1={s.Z1:,.0f}<br>Z2={s.Z2:,.0f}<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        xaxis=dict(title="Z1 — Expected Total Logistics Cost", tickformat=",.0f", gridcolor="#e8e8e8"),
        yaxis=dict(title="Z2 — Expected Max Deprivation Cost", tickformat=",.0f", gridcolor="#e8e8e8"),
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=60, r=20, t=60, b=50),
        hovermode="closest",
        height=400,
    )
    return fig
