import os, sys, json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def plot_nodes(json_file, save_file):
    with open(json_file, "r", encoding='utf-8') as f:
        data = json.load(f)
        
        # Identify indices
        demands = data["nodes"]["demand_indices"]
        hubs = data["nodes"]["hub_indices"]
        origins = data["nodes"]["origin_indices"]
        coords = data["nodes"]["coords"]
        
        # Grab initial risk per scenario 0 (mild wrapper base)
        risk = data["scenarios"][0]["risk"]
        
        # Get all coordinates to define map bounds
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        
        fig = plt.figure(figsize=(10, 8))
        
        use_cartopy = False
        try:
            import cartopy.crs as ccrs
            import cartopy.feature as cfeature
            lon_min, lon_max = min(lons) - 0.15, max(lons) + 0.15
            lat_min, lat_max = min(lats) - 0.10, max(lats) + 0.10
            
            ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
            ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())
            ax.add_feature(cfeature.LAND.with_scale('10m'), facecolor="#F5F5DC", alpha=0.6)
            ax.add_feature(cfeature.OCEAN.with_scale('10m'), facecolor="#D6EAF8", alpha=0.8)
            ax.add_feature(cfeature.RIVERS.with_scale('10m'), edgecolor="#85C1E9", linewidth=0.8, alpha=0.7)
            ax.add_feature(cfeature.BORDERS.with_scale('10m'), edgecolor="#AAAAAA", linewidth=0.6)
            ax.add_feature(cfeature.COASTLINE.with_scale('10m'), edgecolor="#888888", linewidth=0.8)
            ax.gridlines(draw_labels=True, linewidth=0.4, color="gray", alpha=0.5, linestyle="--")
            transform = ccrs.PlateCarree()
            use_cartopy = True 
        except ImportError:
            print("[warn] Cartopy not found or failed, using plain axes")
            ax = fig.add_subplot(1, 1, 1)
            ax.set_facecolor("#EBF5FB")
            transform = None
            
        def scatter_plot(x, y, **kwargs):
            if use_cartopy:
                ax.scatter(x, y, transform=transform, zorder=kwargs.pop("zorder", 4), **kwargs)
            else:
                ax.scatter(x, y, zorder=kwargs.pop("zorder", 4), **kwargs)
        
        # Origin (Blue, Triangles)
        ox = [coords[i][1] for i in origins]
        oy = [coords[i][0] for i in origins]
        scatter_plot(ox, oy, c='blue', marker='^', s=150, label='Origins', edgecolors='k')
        
        # Hubs (Green, Squares)
        hx = [coords[i][1] for i in hubs]
        hy = [coords[i][0] for i in hubs]
        scatter_plot(hx, hy, c='green', marker='s', s=120, label='Hub Candidates', edgecolors='k')
        
        # Demands colored by Risk (Red tint based on risk magnitude)
        dx = [coords[i][1] for i in demands]
        dy = [coords[i][0] for i in demands]
        d_colors = [data["scenarios"][2]["risk"][str(i)] for i in demands]  # Extreme scenario risk
        scatter_d = scatter_plot(dx, dy, c=d_colors, cmap='Reds', marker='o', s=80, label='Demands (color=Risk)', edgecolors='k')
        
        if use_cartopy:
            # Re-create a proxy scatter just for the colorbar because cartopy geo-axes can sometimes have issues returning mappables
            proxy_scatter = ax.scatter(dx, dy, c=d_colors, cmap='Reds', marker='o', s=80, edgecolors='k', alpha=0.0)
            plt.colorbar(proxy_scatter, ax=ax, label="Vulnerability Risk (Extreme Scenario)")
        else:
            # We can't easily get the mappable from the custom scatter_plot function if ax.scatter wasn't returned
            # So let's re-run it directly to assign it for colorbar
            sc = ax.scatter(dx, dy, c=d_colors, cmap='Reds', marker='o', s=80, edgecolors='k')
            plt.colorbar(sc, ax=ax, label="Vulnerability Risk (Extreme Scenario)")
            ax.grid(True, linestyle="--", alpha=0.4)
            ax.set_xlabel("Longitude")
            ax.set_ylabel("Latitude")

        # Combine labels for legend
        handles, labels = ax.get_legend_handles_labels()
        # Since proxy scatters also give labels, we clean it up
        valid_handles = []
        valid_labels = []
        for h, l in zip(handles, labels):
            if l not in valid_labels:
                valid_handles.append(h)
                valid_labels.append(l)
        ax.legend(valid_handles, valid_labels)

        ax.set_title(f"Simulation Topography Mapping\n({os.path.basename(json_file)})")
        fig.tight_layout()
        plt.savefig(save_file, dpi=200)
        print(f"Saved visualization to {save_file}")

plot_nodes('central_vietnam_small_drnd.json', 'map_small_visualization.png')
plot_nodes('central_vietnam_large_drnd.json', 'map_large_visualization.png')