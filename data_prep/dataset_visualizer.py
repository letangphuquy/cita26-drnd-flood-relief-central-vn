"""
dataset_visualizer.py
=====================
Visualize DRND instances on a map of Central Vietnam.

Rendering strategy (RCA-driven):
  Cartopy Natural Earth 10m data has a generalised Vietnam coastline that
  misplaces coastal nodes into the sea.  Instead we use contextily tile-based
  maps (OpenStreetMap / CartoDB) which carry centimetre-accurate coastlines.
  All coordinates are first projected to Web Mercator (EPSG:3857) so that
  data points align exactly with the tile grid — no offset artefacts.

Requires (in venv):
  pip install contextily pyproj  (already installed)

Run with venv Python:
  .venv/Scripts/python data_prep/dataset_visualizer.py

Produces two PNG files per instance (300 dpi):
  map_<size>_nodes.png   -- node layout coloured by auxiliary risk r^a_u
  map_<size>_risk.png    -- scenario risk comparison (mild / severe / extreme)
"""

import os
import sys
import json
import warnings
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from matplotlib.gridspec import GridSpec

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Required: contextily + pyproj (both in .venv) ────────────────────────────
try:
    import contextily as ctx
    from pyproj import Transformer
    _FWD = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    _INV = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    _HAS_CTX = True
except ImportError as _e:
    _HAS_CTX = False
    _e_msg = str(_e)

# Tile source — CartoDB Positron: clean neutral background, accurate coastlines
_TILE_SOURCE = None   # resolved at runtime after import check


# ── coordinate helpers ────────────────────────────────────────────────────────

def _to_merc(lons, lats):
    """Convert parallel lon / lat sequences to Web Mercator (EPSG:3857)."""
    xs, ys = _FWD.transform(list(lons), list(lats))
    return list(xs), list(ys)


def _extent_4326(coords, pad_lat=0.15, pad_lon=0.20):
    """Return [w, e, s, n] bounding box in degrees from coord list."""
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    return [min(lons) - pad_lon, max(lons) + pad_lon,
            min(lats) - pad_lat, max(lats) + pad_lat]


def _extent_3857(ext4):
    """Convert [w, e, s, n] degrees to Web Mercator."""
    xs, ys = _FWD.transform([ext4[0], ext4[1]], [ext4[2], ext4[3]])
    return [xs[0], xs[1], ys[0], ys[1]]


# ── axes factory ─────────────────────────────────────────────────────────────

def _make_ax(fig, gs_pos, ext4):
    """
    Create a Web Mercator axes with tile basemap and lat/lon tick labels.
    Returns the axes (no separate transform — all data must be in EPSG:3857).
    """
    ext3 = _extent_3857(ext4)

    ax = fig.add_subplot(gs_pos)
    ax.set_xlim(ext3[0], ext3[1])
    ax.set_ylim(ext3[2], ext3[3])

    # ── basemap tiles ────────────────────────────────────────────────────────
    if _HAS_CTX:
        try:
            # Native EPSG:3857 — no reprojection, perfect alignment
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ctx.add_basemap(
                    ax,
                    source=ctx.providers.CartoDB.Positron,
                    attribution=False,
                    zorder=0,
                )
        except Exception as e:
            print(f"  [tile] download failed ({e}) — plain background")
            ax.set_facecolor("#EEF4F9")
    else:
        ax.set_facecolor("#EEF4F9")

    # ── lat/lon tick labels (convert from metres back to degrees) ────────────
    def _lon_fmt(x, _):
        lon, _ = _INV.transform(x, (ext3[2] + ext3[3]) / 2)
        return f"{lon:.1f}\u00b0E"

    def _lat_fmt(y, _):
        _, lat = _INV.transform((ext3[0] + ext3[1]) / 2, y)
        return f"{lat:.1f}\u00b0N"

    ax.xaxis.set_major_locator(mticker.MaxNLocator(5, integer=False))
    ax.yaxis.set_major_locator(mticker.MaxNLocator(6, integer=False))
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_lon_fmt))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_lat_fmt))
    ax.tick_params(labelsize=7)
    ax.grid(True, linestyle="--", alpha=0.25, linewidth=0.4, zorder=1)

    return ax


# ── scatter / annotation helpers ─────────────────────────────────────────────

def _sc(ax, lons, lats, **kw):
    """Scatter in Web Mercator."""
    xs, ys = _to_merc(lons, lats)
    return ax.scatter(xs, ys, **kw)


def _ann(ax, text, lon, lat, **kw):
    x, y = _FWD.transform(lon, lat)
    ax.annotate(
        text, (x, y), xytext=(3, 3), textcoords="offset points",
        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.6),
        **kw,
    )


def _label_top_n(ax, coords, indices, values, names, n, fontsize=6.5):
    ranked = sorted(indices, key=lambda i: -values[i])[:n]
    for i in ranked:
        _ann(ax, names[i].replace("_", " "),
             coords[i][1], coords[i][0],
             fontsize=fontsize, ha="left", va="bottom",
             color="#222222", clip_on=True)


# ── Plot 1: node layout coloured by r^a_u ────────────────────────────────────

def plot_node_map(data, save_path):
    coords     = data["nodes"]["coords"]
    names      = data["nodes"]["names"]
    demand_idx = data["nodes"]["demand_indices"]
    hub_idx    = data["nodes"]["hub_indices"]
    origin_idx = data["nodes"]["origin_indices"]
    aux_risk   = data["nodes"]["aux_risk"]
    dims       = data["dimensions"]
    meta_name  = data["meta"]["name"]

    ext4 = _extent_4326(coords)
    norm = Normalize(vmin=0.0, vmax=1.0)

    fig = plt.figure(figsize=(10, 12))
    fig.patch.set_facecolor("white")
    gs  = GridSpec(1, 2, figure=fig, width_ratios=[1, 0.04], wspace=0.06)
    ax  = _make_ax(fig, gs[0, 0], ext4)
    cax = fig.add_subplot(gs[0, 1])

    # Demand — YlOrRd by r^a_u
    _sc(ax,
        [coords[i][1] for i in demand_idx],
        [coords[i][0] for i in demand_idx],
        c=[aux_risk[i] for i in demand_idx],
        cmap="YlOrRd", norm=norm,
        marker="o", s=60, edgecolors="#555555", linewidths=0.5, zorder=4)

    # Hubs — Blues by r^a_u
    _sc(ax,
        [coords[k][1] for k in hub_idx],
        [coords[k][0] for k in hub_idx],
        c=[aux_risk[k] for k in hub_idx],
        cmap="Blues", norm=norm,
        marker="s", s=110, edgecolors="#222222", linewidths=0.9, zorder=5)

    # Origins — dark-green triangles
    _sc(ax,
        [coords[j][1] for j in origin_idx],
        [coords[j][0] for j in origin_idx],
        c="#1A7A2E", marker="^", s=130,
        edgecolors="#111111", linewidths=0.8, zorder=6)

    # Labels
    _label_top_n(ax, coords, demand_idx, aux_risk, names, n=6)
    for k in hub_idx:
        _ann(ax, names[k].replace("_", " "),
             coords[k][1], coords[k][0],
             fontsize=5.5, ha="left", va="top",
             color="#003080", clip_on=True)

    # Colorbar
    sm = ScalarMappable(cmap="YlOrRd", norm=norm)
    sm.set_array([])
    cbar = plt.colorbar(sm, cax=cax)
    cbar.set_label("Auxiliary flood risk  $r^a_u$", fontsize=9)
    cbar.ax.tick_params(labelsize=8)

    # Legend
    ax.legend(handles=[
        mpatches.Patch(facecolor="#D44000", edgecolor="#555", label="Demand node"),
        mpatches.Patch(facecolor="#1560A8", edgecolor="#222", label="Hub candidate"),
        mpatches.Patch(facecolor="#1A7A2E", edgecolor="#111", label="Origin / supply"),
    ], loc="lower left", fontsize=8, framealpha=0.92, edgecolor="#AAAAAA")

    ax.set_title(
        f"{meta_name}  --  node layout  ($r^a_u$ auxiliary flood risk)\n"
        f"I={dims['num_I']}  H={dims['num_H']}  J={dims['num_J']}  "
        f"S={dims['num_S']}  M={dims['num_M']}",
        fontsize=10, pad=8,
    )
    fig.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {save_path}")


# ── Plot 2: per-scenario risk comparison ─────────────────────────────────────

def plot_risk_map(data, save_path):
    coords     = data["nodes"]["coords"]
    demand_idx = data["nodes"]["demand_indices"]
    hub_idx    = data["nodes"]["hub_indices"]
    origin_idx = data["nodes"]["origin_indices"]
    scenarios  = data["scenarios"]
    meta_name  = data["meta"]["name"]

    n_sc = len(scenarios)
    ext4 = _extent_4326(coords)
    norm = Normalize(vmin=0.0, vmax=1.0)

    fig = plt.figure(figsize=(7 * n_sc, 9))
    fig.patch.set_facecolor("white")
    gs  = GridSpec(1, n_sc + 1, figure=fig,
                   width_ratios=[1] * n_sc + [0.04], wspace=0.07)
    cax = fig.add_subplot(gs[0, n_sc])

    for si, sc in enumerate(scenarios):
        ax   = _make_ax(fig, gs[0, si], ext4)
        risk = sc["risk"]

        # Demand — Reds by scenario risk
        _sc(ax,
            [coords[i][1] for i in demand_idx],
            [coords[i][0] for i in demand_idx],
            c=[risk[i] for i in demand_idx],
            cmap="Reds", norm=norm,
            marker="o", s=60, edgecolors="#555555", linewidths=0.5, zorder=4)

        # Hubs — Blues by scenario risk
        _sc(ax,
            [coords[k][1] for k in hub_idx],
            [coords[k][0] for k in hub_idx],
            c=[risk[k] for k in hub_idx],
            cmap="Blues", norm=norm,
            marker="s", s=110, edgecolors="#222222", linewidths=0.9, zorder=5)

        # Origins — dark-green triangles
        _sc(ax,
            [coords[j][1] for j in origin_idx],
            [coords[j][0] for j in origin_idx],
            c="#1A7A2E", marker="^", s=130,
            edgecolors="#111111", linewidths=0.8, zorder=6)

        # Epicenters — red stars
        for ep in sc.get("epicenters", []):
            _sc(ax, [ep["lon"]], [ep["lat"]],
                marker="*", s=280, c="#FF0000",
                edgecolors="#800000", linewidths=0.9, zorder=7)

        avg_r = sum(risk[i] for i in demand_idx) / len(demand_idx)
        ax.set_title(
            f"{sc['name'].capitalize()}  "
            f"($\\pi$={sc['probability']},  $\\phi$={sc.get('phi_circuity','?')})\n"
            f"avg demand risk = {avg_r:.3f}",
            fontsize=9,
        )

    sm = ScalarMappable(cmap="Reds", norm=norm)
    sm.set_array([])
    cbar = plt.colorbar(sm, cax=cax)
    cbar.set_label("Scenario risk  $r_{us}$", fontsize=9)
    cbar.ax.tick_params(labelsize=8)

    fig.suptitle(f"{meta_name}  --  scenario risk  (* = epicentre)",
                 fontsize=11, y=1.01)
    fig.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {save_path}")


# ── entry point ───────────────────────────────────────────────────────────────

def visualize(json_path):
    if not _HAS_CTX:
        print(f"  [ERROR] contextily/pyproj not found ({_e_msg})")
        print("  Run: .venv/Scripts/python data_prep/dataset_visualizer.py")
        return

    print(f"  [backend] contextily (CartoDB Positron, EPSG:3857 native)")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    base      = os.path.splitext(os.path.basename(json_path))[0]
    out_nodes = os.path.join(SCRIPT_DIR, f"map_{base}_nodes.png")
    out_risk  = os.path.join(SCRIPT_DIR, f"map_{base}_risk.png")

    print(f"Visualising: {json_path}")
    plot_node_map(data, out_nodes)
    plot_risk_map(data, out_risk)


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else [
        os.path.join(SCRIPT_DIR, "cv_small_drnd.json"),
        os.path.join(SCRIPT_DIR, "cv_large_drnd.json"),
    ]
    for path in targets:
        if os.path.exists(path):
            visualize(path)
        else:
            print(f"[skip] not found: {path}")
