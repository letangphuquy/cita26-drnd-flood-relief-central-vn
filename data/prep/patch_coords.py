"""
patch_coords.py
===============
Reads audit_report.json and patches generate_drnd.py with corrected coordinates.

Strategy:
  APPLY  — OSM result falls inside the 4-province bbox  AND  delta > WARN_KM
  SKIP   — OSM result is outside the region (Nominatim returned a wrong-province hit)
  MANUAL — NO_RESULT; hard-coded ground-truth coordinates for critical infra nodes

Run:
  python data_prep/patch_coords.py [--dry-run]

After patching, re-run generate_drnd.py to regenerate the JSON datasets.
"""

import json
import re
import sys
import os
import shutil
from datetime import datetime

DRY_RUN = "--dry-run" in sys.argv

# 4-province bounding box (conservative)
LAT_MIN, LAT_MAX = 14.40, 17.20
LON_MIN, LON_MAX = 106.60, 109.30   # include Khe Sanh (106.73)

WARN_KM = 5.0   # only patch if discrepancy is meaningful

# ─────────────────────────────────────────────────────────────────────────────
# MANUAL FIXES
# Priority over OSM for every node listed here.
# Sources: IATA data, official port registries, cross-referenced internal GIS
# database (fact-checked 2026-03-04).  See misc/audit-log.txt for full audit.
# ─────────────────────────────────────────────────────────────────────────────
MANUAL = {
    # ── ORIGIN ───────────────────────────────────────────────────────────────
    # Dung Quat deepwater industrial port, Binh Son, Quang Ngai
    "Dung_Quat_Port":        (15.3700, 108.8000),
    # Chu Lai Airport (IATA: VCL), Nui Thanh, Quang Nam
    "Chu_Lai_Airport":       (15.4033, 108.7061),
    # Thuan An inlet / fishing port, Phu Vang, Thua Thien Hue
    "Thuan_An_Port":         (16.5200, 107.6900),
    # Sa Ky fishing port, Binh Son, Quang Ngai
    "Sa_Ky_Port":            (15.2100, 108.8700),
    # Khe Sanh strategic checkpoint, Huong Hoa, Quang Tri
    # OSM returned a bank POI but coordinates (16.626, 106.734) are correct
    # for the town. Hard-coded to the town center, not the bank.
    "Khe_Sanh_Entry":        (16.6300, 106.7300),
    # Lang Co town center, foot of Hai Van pass, Phu Loc, TTH
    # OSM returned Angsana resort hotel (Chân Mây peninsula) — wrong anchor.
    "Lang_Co_Beach_Base":    (16.2400, 108.0200),

    # ── HUB ──────────────────────────────────────────────────────────────────
    # Dong Giang district center, Quang Nam
    "Dong_Giang_Rescue_Stn": (15.9126, 107.7265),
    # Thang Binh district center, Quang Nam (coastal strip)
    "Thang_Binh_Depot":      (15.6900, 108.3400),
    # Nam Giang district center, Quang Nam
    "Nam_Giang_Forward_Base":(15.6072, 107.6071),
    # Nui Thanh district center, Quang Nam
    "Nui_Thanh_Reserve":     (15.4500, 108.6200),
    # Que Son district center, Quang Nam
    "Que_Son_Facility":      (15.6832, 108.0627),
    # Huong Viet commune, A Luoi, Thua Thien Hue (Laos border area)
    "Huong_Viet_Depot":      (16.7000, 107.0600),
    # Quang Ngai Port logistics hub (Dung Quat area)
    "Quang_Ngai_Port_Hub":   (15.3700, 108.8000),
    # Phuoc Son district center, Quang Nam
    "Phuoc_Son_Helipad":     (15.7200, 107.9700),
    # Rao Trang area, A Luoi, Thua Thien Hue (2020 landslide site)
    "Rao_Trang_Base":        (16.1500, 107.4000),
    # Bac Tra My district center, Quang Nam
    "Bac_Tra_My_Depot":      (15.3200, 107.9500),
    # Son Ha district center (Di Lang town), Quang Ngai  [fact-checked]
    # OSM centroid was wrong (too far east at 108.52). Stored (107.72) was in Laos.
    "Son_Ha_Hub":            (15.0300, 108.4700),
    # Lang Co town center — same anchor as Lang_Co_Beach_Base  [fact-checked]
    # OSM returned Angsana resort hotel.
    "Lang_Co_Forward_Post":  (16.2400, 108.0200),
    # A Luoi highland — A Dot commune (Lam Dot), A Luoi district, TTH  [fact-checked]
    # OSM returned the A Sap river feature, not the commune.
    "A_Dot_Mountain_Base":   (16.1200, 107.3000),
    # A Sap valley helipad, A Luoi district, TTH  [fact-checked]
    # OSM returned "Đường A Sáp" road feature.
    "A_Sap_Helipad":         (16.2500, 107.2500),

    # ── DEMAND ───────────────────────────────────────────────────────────────
    # Dien Ban district center, Quang Nam
    "Dien_Ban_District":     (15.8900, 108.2500),
    # Nui Thanh district, Quang Nam (coastal)
    "Nui_Thanh_District":    (15.4500, 108.6200),
    # Huong Thuy district, Thua Thien Hue
    "Huong_Thuy_District":   (16.3400, 107.6800),
    # Nam Dong district center, Thua Thien Hue
    "Nam_Dong_District":     (16.0800, 107.7200),
    # Nam Dong highland (south of district center)
    "Nam_Dong_Highland":     (16.0000, 107.6500),
    # A Vuong commune, Tay Giang district, Quang Nam
    "A_Vuong_Commune":       (15.9400, 107.5800),
    # Phu Ninh district center, Quang Nam
    "Phu_Ninh_District":     (15.5800, 108.3200),
    # Phu Dien ward, Phong Dien, Thua Thien Hue
    "Phu_Dien_Ward":         (16.7600, 107.3800),
    # Huong Tra district center, Thua Thien Hue
    "Huong_Tra_District":    (16.5100, 107.5500),
    # Southern Nui Thanh area, Quang Nam coast
    "Nui_Thanh_South":       (15.3800, 108.6500),
    # South of Tam Ky, Quang Nam
    "Tam_Ky_South":          (15.5000, 108.4200),
    # West of Phu Loc district, TTH
    "Phu_Loc_West":          (16.2300, 107.7500),
    # Southern Hue city area, TTH
    "Hue_City_South":        (16.4000, 107.6000),
    # Phong Dien district, Thua Thien Hue (north of Hue)
    "Phong_Dien_District":   (16.6100, 107.4500),
    # Tra Don commune, Bac Tra My, Quang Nam
    "Tra_Don_Commune":       (15.4000, 107.9500),
    # Lang Co lagoon/town area, TTH
    "Lang_Co_Area":          (16.2400, 108.0200),
    # Truoi reservoir, Phu Loc, Thua Thien Hue
    "Truoi_Lake_Area":       (16.3500, 107.7000),
    # Vu Gia river confluence area, Nam Giang/Dai Loc border
    "Vu_Gia_River_South":    (15.8500, 107.6000),
    # Song Bung hydropower reservoir, Nam Giang/Dong Giang
    "Song_Bung_Lake":        (15.9000, 107.5000),
    # Bach Ma National Park, TTH/Quang Nam border
    "Bach_Ma_Forest":        (16.1800, 107.8500),
    # Western A Luoi valley, TTH
    "A_Luoi_Valley":         (16.2100, 107.2800),
    # Tra My highlands (between Bac / Nam Tra My), Quang Nam
    "Tra_My_Highlands":      (15.4500, 108.0500),
    # Phuoc Son district center, Quang Nam
    "Phuoc_Son_District":    (15.7200, 107.9700),
    # Huong An commune, north TTH near Quang Tri border
    "Huong_An_Commune":      (16.7500, 107.3000),
    # Tho Quang ward, Son Tra peninsula, Da Nang (port side)
    "Tho_Quang_Ward":        (16.1000, 108.2200),
    # An Tan commune, Hoa Vang outskirts, Da Nang
    "An_Tan_Commune":        (15.9500, 108.0500),
    # Lac My commune, Hoa Vang/Dong Giang border
    "Lac_My_Commune":        (15.9600, 107.8500),
    # Hong Ha commune, A Luoi highlands, TTH
    "Hong_Ha_Commune":       (16.3500, 107.5500),
    # Quang An ward, Phu Vang, TTH
    "Quang_An_Ward":         (16.4800, 107.6800),
    # Huong Xuan commune, A Luoi district, TTH
    "Huong_Xuan_Commune":    (16.2200, 107.3500),
    # Tam Viet commune, Phu Ninh district, Quang Nam
    "Tam_Viet_Commune":      (15.5800, 108.3000),
    # Binh Duong commune, Thang Binh coastal, Quang Nam
    "Binh_Duong_Commune":    (15.7800, 108.5000),
    # Chu Lai industrial port / SEZ area, Nui Thanh, Quang Nam
    "Chu_Lai_Port_Area":     (15.4000, 108.7000),
    # My Khe Beach, Son Tra district, Da Nang
    "My_Khe_Beach_Area":     (16.0600, 108.2500),
    # A Bat commune, far north TTH / Quang Tri border
    "A_Bat_Commune":         (16.7500, 107.1500),
    # La Ee (A La) commune, Nam Giang district, Quang Nam
    "A_La_Commune":          (15.6300, 107.3700),
    # Cao Ngan commune, far northwest TTH
    "Cao_Ngan_Commune":      (16.7000, 107.1500),
    # Duc Pho district (now Duc Pho town), southern Quang Ngai
    "Duc_Pho_District":      (14.8500, 108.9600),
    # Phu Thuong ward, Phong Dien district, TTH
    "Phu_Thuong_Ward":       (16.6300, 107.4200),
    # Truong Giang commune, Nui Thanh coastal strip, Quang Nam
    "Truong_Giang_Commune":  (15.5500, 108.5200),  # moved inland — 108.62 risked sea boundary
    # Son Qua commune, Rao Trang valley, A Luoi, near Quang Tri border
    "Son_Qua_Commune":       (16.8500, 107.2000),
    # Xuan Ha ward, Son Tra district, Da Nang
    "Xuan_Ha_Ward":          (16.0700, 108.2200),
    # Bac Tra My district, Quang Nam highland
    "Bac_Tra_My":            (15.3200, 107.9500),
    # Khue Trung valley, western Quang Nam highland
    "Khue_Trung_Valley":     (15.7200, 107.5500),
    # Zuoih commune, Phuoc Son, Quang Nam
    "Zuoih_Commune":         (15.6500, 107.5500),
    # Bha Le commune, Nam Giang, Quang Nam (near Laos border)
    "Bha_Le_Commune":        (15.5500, 107.4500),
    # Tra Vie commune, Nam Giang, Quang Nam
    "Tra_Vie_Commune":       (15.8500, 107.6200),
    # Ca Dy commune (Ben Giang area), Nam Giang, Quang Nam  [fact-checked]
    # Stored (15.75, 107.76) was ~19 km north; correct center is Ben Giang.
    "Ca_Dy_Commune":         (15.5800, 107.8200),
    # Tra Bui commune, Bac Tra My, Quang Nam  [fact-checked]
    # Stored (15.54, 107.84) was NW; actual village is further SE.
    "Tra_Bui_Commune":       (15.3500, 108.1000),
    # Ta Bhing commune (Xã Tà Bhing), Nam Giang, Quang Nam
    # Renamed from Ca_Lu_Commune — "Cà Lu" was a phantom (only exists in Dakrong, Quang Tri).
    "Ta_Bhing_Commune":      (15.6200, 107.7200),
    # Phu Yen commune, Phu Ninh district, Quang Nam
    "Phu_Yen_Commune":       (15.7000, 108.3000),
    # Tam Quan — coastal area north Quang Ngai (Binh Son)
    "Tam_Quan_Town":         (15.3500, 108.8000),
    # Thuong Quang commune, Nam Dong district, TTH
    "Thuong_Quang_Commune":  (16.1500, 107.7500),
    # A Tuc commune, far north TTH near Quang Tri border
    "A_Tuc_Commune":         (16.8500, 107.0500),
    # Tam Hiep commune, southern Nui Thanh area, Quang Nam
    "Tam_Hiep_Commune":      (15.3800, 108.7000),
    # Hoa Tien commune, Hoa Vang district lowland, Da Nang  [fact-checked]
    # 107.95°E was pushing it into Dong Giang hills; actual lon ≈ 108.19°E.
    "Hoa_Tien_Commune":      (15.9800, 108.1900),
    # Tra Bong district center (Tra Xuan town), Quang Ngai  [OSM-confirmed]
    "Tra_Bong_Supply":       (15.2093, 108.4534),
    # Son Ha district center (Di Lang town), Quang Ngai  [fact-checked]
    # Both stored (107.85) and OSM centroid (108.52) were wrong.
    "Son_Ha_District":       (15.0300, 108.4700),
    # A Luoi demand nodes — micro-offset from hub centroid to avoid Θ=0  [zero-distance fix]
    # A_Luoi_Relief_Center (hub) is at (16.2135, 107.3368); demand nodes must not share it.
    "A_Luoi_District":       (16.2185, 107.3318),   # +0.005°N  -0.005°E  (~0.7 km NW)
    "A_Luoi_Mountain":       (16.2085, 107.3418),   # -0.005°N  +0.005°E  (~0.7 km SE)
    # A Dot commune (Lam Dot), A Luoi district, TTH  [fact-checked]
    # OSM returned the A Sap river feature instead of the commune.
    "A_Dot_Commune":         (16.1200, 107.3000),
    # Viet An commune (Binh Lam / Cho Viet An), Hiep Duc, Quang Nam  [fact-checked]
    # OSM moved it 43 km south to a different Viet An in Da Nang admin area.
    "Viet_An_Commune":       (15.5800, 108.1400),
    # Nam Tra My district center (Tra Mai commune), Quang Nam  [fact-checked]
    # OSM mislabeled province as Quang Ngai.
    "Nam_Tra_My":            (15.1400, 108.1200),
    # Tra Nam commune, western Nam Tra My, Quang Nam  [fact-checked]
    # OSM returned Nam Tra My town center instead (different place).
    "Tra_Nam_Commune":       (15.0800, 108.0500),
    # Ta Lang commune, Hoa Bac, Hoa Vang, Da Nang  [fact-checked]
    # OSM returned A Vuong commune in Tay Giang — completely different location.
    "Ta_Lang_Commune":       (16.1300, 107.9700),
    # Hoa Lien commune, Hoa Vang district, Da Nang  [fact-checked]
    # OSM returned an expressway road feature, not the commune centroid.
    "Hoa_Lien_Commune":      (16.0800, 108.1200),
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def in_region(lat, lon):
    return LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX


def build_corrections(report_path):
    """
    Returns dict: name → (new_lat, new_lon, source)
    source is 'osm' or 'manual'
    """
    with open(report_path, encoding="utf-8") as f:
        data = json.load(f)

    corrections = {}

    for r in data["results"]:
        name = r["name"]

        # Priority 1: manual fix if defined
        if name in MANUAL:
            corrections[name] = (*MANUAL[name], "manual")
            continue

        # Priority 2: OSM result that is inside the region AND has meaningful delta
        if r["status"] in ("ERROR", "WARNING") and r["osm"] is not None:
            olat, olon = r["osm"]
            delta = r["delta_km"] or 0
            if in_region(olat, olon) and delta >= WARN_KM:
                corrections[name] = (olat, olon, "osm")

    return corrections


def patch_source(src: str, corrections: dict) -> tuple[str, list]:
    """
    Replace coordinate tuples in the source text.
    Matches lines like:  (15.4300, 108.2073, "Nui_Thanh_District"),
    Returns (patched_src, list_of_applied_changes).
    """
    applied = []
    skipped = []

    for name, (new_lat, new_lon, source) in corrections.items():
        # Pattern: (any_lat, any_lon, "Name")  — allows variable whitespace
        pattern = re.compile(
            r'\((\s*-?\d+\.?\d*\s*),(\s*-?\d+\.?\d*\s*),(\s*"' + re.escape(name) + r'"\s*)\)'
        )
        match = pattern.search(src)
        if not match:
            skipped.append(name)
            continue

        old_lat = float(match.group(1).strip())
        old_lon = float(match.group(2).strip())
        name_part = match.group(3)

        new_str = f"({new_lat:.4f}, {new_lon:.4f},{name_part})"
        src = pattern.sub(new_str, src)
        applied.append({
            "name":   name,
            "source": source,
            "old":    (old_lat, old_lon),
            "new":    (new_lat, new_lon),
        })

    return src, applied, skipped


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    base = os.path.dirname(os.path.abspath(__file__))
    report_path = os.path.join(base, "audit_report.json")
    src_path    = os.path.join(base, "generate_drnd.py")
    backup_path = src_path + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if not os.path.exists(report_path):
        sys.exit(f"ERROR: {report_path} not found. Run audit_coords.py first.")
    if not os.path.exists(src_path):
        sys.exit(f"ERROR: {src_path} not found.")

    corrections = build_corrections(report_path)
    print(f"Corrections to apply: {len(corrections)}")
    for name, (lat, lon, src) in sorted(corrections.items()):
        print(f"  [{src:6s}] {name:40s} → ({lat:.4f}, {lon:.4f})")

    with open(src_path, encoding="utf-8") as f:
        original = f.read()

    patched, applied, skipped = patch_source(original, corrections)

    print(f"\nApplied: {len(applied)}  |  Not found in source: {len(skipped)}")
    if skipped:
        print(f"  Skipped (pattern not matched): {skipped}")

    if DRY_RUN:
        print("\n[DRY RUN] No files written.")
        return

    # Backup original
    shutil.copy2(src_path, backup_path)
    print(f"\nBackup written: {backup_path}")

    with open(src_path, "w", encoding="utf-8") as f:
        f.write(patched)
    print(f"Patched:  {src_path}")

    # Write change log
    log_path = os.path.join(base, "patch_log.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({"applied": applied, "skipped": skipped}, f, indent=2)
    print(f"Log:      {log_path}")
    print("\nDone. Now re-run:  python data_prep/generate_drnd.py")


if __name__ == "__main__":
    main()
