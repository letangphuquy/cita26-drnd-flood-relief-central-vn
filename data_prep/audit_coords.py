"""
audit_coords.py
===============
Fact-check all node coordinates in generate_drnd.py against
the OpenStreetMap Nominatim geocoding API.

For each node, the script:
  1. Sends the curated search query to Nominatim
  2. Computes Haversine distance between stored vs. returned coordinates
  3. Flags nodes with discrepancy > WARN_KM (warning) or > ERROR_KM (error)
  4. Prints a structured report and writes audit_report.json

Usage:
  python data_prep/audit_coords.py

Setup (one-time):
  pip install requests
  (No other dependencies needed — uses only stdlib + requests)

Nominatim usage policy:
  - Max 1 request / second  → enforced by time.sleep(1.1) between calls
  - Must set a descriptive User-Agent header (see USER_AGENT below)
  - Do NOT run this script in a tight loop or CI pipeline
  - Full policy: https://operations.osmfoundation.org/policies/nominatim/
"""

import json
import math
import time
import os
import sys

try:
    import requests
except ImportError:
    sys.exit("ERROR: 'requests' not installed. Run: pip install requests")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# IMPORTANT: replace with your real project name + contact email.
# Nominatim blocks anonymous or generic User-Agents.
USER_AGENT = "DRND-for-Flood-prevention-in-Central-VietNam/1.0 (research; contact: [quyltp.22git@vku.udn.vn])"

WARN_KM  = 5.0    # flag as WARNING if discrepancy >= 5 km
ERROR_KM = 15.0   # flag as ERROR   if discrepancy >= 15 km

SLEEP_S  = 1.1    # seconds between API calls (policy: >= 1.0)

EARTH_R  = 6371.0


# ─────────────────────────────────────────────────────────────────────────────
# CURATED QUERY MAP
# Maps node name → Nominatim search string.
# Nodes whose names are synthetic facility labels (e.g. "A_Luoi_Relief_Center")
# must be mapped to their underlying real place name.
# Nodes without an entry fall back to auto-query (name + "Vietnam").
# ─────────────────────────────────────────────────────────────────────────────

QUERY_MAP = {
    # ── ORIGIN NODES ─────────────────────────────────────────────────────────
    "Hai_Van_Pass_North":    "Hai Van Pass, Da Nang, Vietnam",
    "Dung_Quat_Port":        "Dung Quat Port, Binh Son, Quang Ngai, Vietnam",
    "Chu_Lai_Airport":       "Chu Lai Airport, Nui Thanh, Quang Nam, Vietnam",
    "Thuan_An_Port":         "Thuan An Port, Phu Vang, Thua Thien Hue, Vietnam",
    "Sa_Ky_Port":            "Sa Ky Port, Binh Son, Quang Ngai, Vietnam",
    "Khe_Sanh_Entry":        "Khe Sanh, Huong Hoa, Quang Tri, Vietnam",
    "Tra_Bong_Supply":       "Tra Bong District, Quang Ngai, Vietnam",
    "Da_Nang_Seaport":       "Tien Sa Port, Son Tra, Da Nang, Vietnam",
    "Hue_Train_Station":     "Hue Railway Station, Thua Thien Hue, Vietnam",
    "Ly_Son_Island_Supply":  "Ly Son Island, Quang Ngai, Vietnam",
    "Lang_Co_Beach_Base":    "Lang Co, Phu Loc, Thua Thien Hue, Vietnam",
    "Duc_Pho_Harbor":        "Duc Pho, Quang Ngai, Vietnam",

    # ── HUB NODES ─────────────────────────────────────────────────────────────
    "Da_Nang_Airport_Hub":   "Da Nang International Airport, Vietnam",
    "Tam_Ky_Logistics_Hub":  "Tam Ky City, Quang Nam, Vietnam",
    "A_Luoi_Relief_Center":  "A Luoi District, Thua Thien Hue, Vietnam",
    "Dong_Giang_Rescue_Stn": "Dong Giang District, Quang Nam, Vietnam",
    "Thang_Binh_Depot":      "Thang Binh District, Quang Nam, Vietnam",
    "Nam_Giang_Forward_Base":"Nam Giang District, Quang Nam, Vietnam",
    "Phu_Loc_Staging_Area":  "Phu Loc District, Thua Thien Hue, Vietnam",
    "Nui_Thanh_Reserve":     "Nui Thanh District, Quang Nam, Vietnam",
    "Lang_Co_Forward_Post":  "Lang Co, Phu Loc, Thua Thien Hue, Vietnam",
    "Binh_Son_Warehouse":    "Binh Son District, Quang Ngai, Vietnam",
    "A_Dot_Mountain_Base":   "A Dot Commune, A Luoi, Thua Thien Hue, Vietnam",
    "Quang_Ngai_Depot":      "Quang Ngai City, Vietnam",
    "A_Sap_Helipad":         "A Sap, A Luoi, Thua Thien Hue, Vietnam",
    "Que_Son_Facility":      "Que Son District, Quang Nam, Vietnam",
    "Huong_Viet_Depot":      "Huong Viet Commune, A Luoi, Thua Thien Hue, Vietnam",
    "Quang_Ngai_Port_Hub":   "Quang Ngai Port, Quang Ngai, Vietnam",
    "Phuoc_Son_Helipad":     "Phuoc Son District, Quang Nam, Vietnam",
    "Rao_Trang_Base":        "Rao Trang, A Luoi, Thua Thien Hue, Vietnam",
    "Bac_Tra_My_Depot":      "Bac Tra My District, Quang Nam, Vietnam",
    "Son_Ha_Hub":            "Son Ha District, Quang Ngai, Vietnam",

    # ── DEMAND NODES (spot-check the most likely hallucinations) ─────────────
    "Hoi_An_City":           "Hoi An City, Quang Nam, Vietnam",
    "Nui_Thanh_District":    "Nui Thanh District, Quang Nam, Vietnam",
    "A_Luoi_Mountain":       "A Luoi District, Thua Thien Hue, Vietnam",
    "Da_Nang_City":          "Da Nang City, Vietnam",
    "Tam_Ky_City":           "Tam Ky City, Quang Nam, Vietnam",
    "Quang_Ngai_City":       "Quang Ngai City, Vietnam",
    "Binh_Son_District":     "Binh Son District, Quang Ngai, Vietnam",
    "Son_Ha_District":       "Son Ha District, Quang Ngai, Vietnam",
    "Duc_Pho_District":      "Duc Pho District, Quang Ngai, Vietnam",
    "Tra_Bong_District":     "Tra Bong District, Quang Ngai, Vietnam",
    "Bac_Tra_My":            "Bac Tra My District, Quang Nam, Vietnam",
    "Phuoc_Son_District":    "Phuoc Son District, Quang Nam, Vietnam",
    "Nam_Dong_District":     "Nam Dong District, Thua Thien Hue, Vietnam",
    "Ly_Son_Island":         "Ly Son Island, Quang Ngai, Vietnam",
    "Chu_Lai_Port_Area":     "Chu Lai, Nui Thanh, Quang Nam, Vietnam",
    "A_Sap_Valley":          "A Sap, A Luoi, Thua Thien Hue, Vietnam",
}

# ─────────────────────────────────────────────────────────────────────────────
# NODE DATA  (copied from generate_drnd.py — single source of truth to audit)
# ─────────────────────────────────────────────────────────────────────────────

# fmt: (lat, lon, name)
DEMAND_NODES = [
    (15.8732, 108.3341, "Hoi_An_City"),
    (15.9374, 108.3036, "Dien_Ban_District"),
    (15.4300, 108.2073, "Nui_Thanh_District"),
    (15.7562, 108.2461, "Thang_Binh_District"),
    (16.0752, 108.1491, "Dai_Loc_District"),
    (15.9867, 107.9883, "Dong_Giang_District"),
    (16.2114, 108.0243, "Tay_Giang_District"),
    (16.3012, 107.8631, "A_Luoi_District"),
    (15.90,   107.65,   "Nam_Giang_District"),
    (16.1004, 107.7321, "A_Vuong_Commune"),
    (15.9421, 108.2631, "Viet_An_Commune"),
    (16.0123, 108.0961, "Que_Son_District"),
    (15.73,   108.12,   "Phu_Ninh_District"),
    (15.5600, 108.3600, "Tam_Ky_City"),
    (16.47,   107.52,   "Huong_Tra_District"),
    (16.39,   107.60,   "Huong_Thuy_District"),
    (16.08,   107.75,   "Nam_Dong_District"),
    (16.20,   107.86,   "Phu_Loc_District"),
    (16.4001, 107.6521, "A_Luoi_Mountain"),
    (16.2812, 107.5321, "Nam_Dong_Highland"),
    (16.0543, 108.2022, "Da_Nang_City"),
    (15.9123, 108.1541, "Cam_Le_District"),
    (16.1232, 108.1982, "Lien_Chieu_District"),
    (16.0012, 108.2401, "Son_Tra_District"),
    (15.8721, 108.0841, "Thanh_Khe_District"),
    (16.2432, 108.0762, "Hoa_Vang_District"),
    (15.7321, 108.1432, "Phu_Yen_Commune"),
    (15.3200, 107.8341, "Bac_Tra_My"),
    (15.8453, 107.9872, "Nam_Tra_My"),
    (15.6721, 108.0341, "Hiep_Duc_District"),
    (15.5631, 108.2541, "Tien_Phuoc_District"),
    (15.4321, 108.4012, "Nui_Thanh_South"),
    (15.6012, 108.3341, "Tam_Ky_South"),
    (16.5123, 107.6012, "Phu_Loc_West"),
    (16.52,   107.62,   "Phu_Vang_District"),
    (16.58,   107.43,   "Quang_Dien_District"),
    (16.52,   107.40,   "Phong_Dien_District"),
    (16.42,   107.56,   "Hue_City_South"),
    (16.4631, 107.4321, "Khe_Tre_Commune"),
    (15.7143, 107.8101, "Tra_Don_Commune"),
    (15.5832, 107.9431, "Tra_Nam_Commune"),
    (16.24,   107.94,   "Lang_Co_Area"),
    (16.6012, 107.3541, "Truoi_Lake_Area"),
    (15.9432, 107.5932, "Vu_Gia_River_South"),
    (16.1321, 107.4531, "Song_Bung_Lake"),
    (16.2500, 107.2700, "A_Sap_Valley"),
    (15.8123, 107.6321, "Phuoc_Son_District"),
    (15.6831, 107.7851, "Tra_My_Highlands"),
    (16.1900, 107.8600, "Bach_Ma_Forest"),
    (16.3500, 107.3000, "A_Luoi_Valley"),
    (16.78,   107.22,   "Huong_An_Commune"),
    (16.0500, 108.23,   "Tho_Quang_Ward"),
    (15.9812, 108.1721, "Hoa_Cuong_Ward"),
    (15.8342, 108.0012, "An_Tan_Commune"),
    (16.1891, 107.9341, "Lac_My_Commune"),
    (16.3543, 107.6521, "Hong_Ha_Commune"),
    (16.50,   107.62,   "Quang_An_Ward"),
    (16.2231, 107.3041, "Huong_Xuan_Commune"),
    (15.6521, 108.1341, "Tam_Viet_Commune"),
    (15.4832, 108.3031, "Tam_Hiep_Commune"),
    (15.7981, 108.4201, "Binh_Duong_Commune"),
    (16.80,   107.26,   "Phu_Dien_Ward"),
    (16.0601, 108.20,   "My_Khe_Beach_Area"),
    (16.9321, 107.3012, "A_Dot_Commune"),
    (15.4501, 108.5801, "Tam_Quan_Town"),
    (15.2431, 108.4231, "Nuoc_Trong_Reservoir"),
    (15.1241, 108.3121, "Duc_Pho_District"),
    (16.9541, 107.1231, "A_Bat_Commune"),
    (17.0231, 107.2031, "A_La_Commune"),
    (16.8501, 107.2501, "Cao_Ngan_Commune"),
    (15.0541, 108.6541, "Mo_Duc_District"),
    (15.1831, 108.7801, "Minh_Long_District"),
    (15.42,   108.69,   "Chu_Lai_Port_Area"),
    (15.4012, 107.8501, "Son_Ha_District"),
    (15.2831, 107.7021, "Son_Tay_District"),
    (15.0001, 107.9231, "Tra_Bong_District"),
    (14.9321, 108.1431, "Nghia_Hanh_District"),
    (14.8541, 108.3201, "Tu_Nghia_District"),
    (15.1200, 108.4801, "Quang_Ngai_City"),
    (14.9012, 108.5601, "Son_Tinh_District"),
    (15.1231, 108.6271, "Binh_Son_District"),
    (15.7200, 107.5500, "Khue_Trung_Valley"),
    (16.72,   107.28,   "Phu_Thuong_Ward"),
    (15.5501, 108.5401, "Truong_Giang_Commune"),
    (17.07,   107.16,   "Son_Qua_Commune"),
    (15.93,   108.28,   "Xuan_Ha_Ward"),
    (16.085,  108.20,   "Man_Thai_Ward"),
    (15.5601, 107.9151, "Phuoc_Hiep_Commune"),
    (16.1400, 108.0500, "Hoa_Lien_Commune"),
    (16.31,   107.82,   "Hoa_Tien_Commune"),
    (16.0321, 107.6531, "Zuoih_Commune"),
    (15.8901, 107.4581, "Bha_Le_Commune"),
    (15.8500, 107.6200, "Tra_Vie_Commune"),
    (15.7500, 107.7600, "Ca_Dy_Commune"),
    (15.5400, 107.8400, "Tra_Bui_Commune"),
    (16.2521, 107.8951, "Ta_Lang_Commune"),
    (16.4012, 107.4081, "Thuong_Quang_Commune"),
    (16.6721, 107.2541, "A_Ngo_Commune"),
    (16.8341, 107.0931, "A_Tuc_Commune"),
    (15.6000, 107.7000, "Ca_Lu_Commune"),
]

HUB_NODES = [
    (16.0544, 108.2022, "Da_Nang_Airport_Hub"),
    (15.5600, 108.3300, "Tam_Ky_Logistics_Hub"),
    (16.4601, 107.5961, "A_Luoi_Relief_Center"),
    (15.9700, 107.8600, "Dong_Giang_Rescue_Stn"),
    (15.6400, 108.2100, "Thang_Binh_Depot"),
    (15.85,   107.70,   "Nam_Giang_Forward_Base"),
    (16.18,   107.80,   "Phu_Loc_Staging_Area"),
    (15.4500, 108.4200, "Nui_Thanh_Reserve"),
    (16.25,   107.90,   "Lang_Co_Forward_Post"),
    (15.2200, 108.6000, "Binh_Son_Warehouse"),
    (16.9300, 107.2500, "A_Dot_Mountain_Base"),
    (15.0500, 108.4000, "Quang_Ngai_Depot"),
    (16.1500, 107.6200, "A_Sap_Helipad"),
    (15.7800, 108.0500, "Que_Son_Facility"),
    (16.86,   107.24,   "Huong_Viet_Depot"),
    (14.8700, 108.7900, "Quang_Ngai_Port_Hub"),
    (15.6200, 107.7200, "Phuoc_Son_Helipad"),
    (17.05,   107.18,   "Rao_Trang_Base"),
    (16.2800, 107.5100, "Bac_Tra_My_Depot"),
    (15.4800, 107.7200, "Son_Ha_Hub"),
]

ORIGIN_NODES = [
    (16.1124, 108.1948, "Hai_Van_Pass_North"),
    (15.4000, 108.3100, "Dung_Quat_Port"),
    (15.7500, 108.4700, "Chu_Lai_Airport"),
    (16.53,   107.70,   "Thuan_An_Port"),
    (14.7600, 108.6900, "Sa_Ky_Port"),
    (17.1900, 107.0700, "Khe_Sanh_Entry"),
    (15.3600, 107.8900, "Tra_Bong_Supply"),
    (16.0930, 108.2280, "Da_Nang_Seaport"),
    (16.46,   107.60,   "Hue_Train_Station"),
    (15.3800, 109.1000, "Ly_Son_Island_Supply"),
    (16.21,   107.96,   "Lang_Co_Beach_Base"),
    (14.5700, 108.9800, "Duc_Pho_Harbor"),
]


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def haversine(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return EARTH_R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def nominatim_geocode(query: str) -> dict | None:
    """
    Query Nominatim. Returns the top result as a dict with keys
    {lat, lon, display_name} or None if no result found.
    """
    params = {
        "q":              query,
        "format":         "json",
        "limit":          1,
        "countrycodes":   "vn",      # restrict to Vietnam
        "addressdetails": 0,
    }
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        if results:
            r = results[0]
            return {
                "lat":          float(r["lat"]),
                "lon":          float(r["lon"]),
                "display_name": r["display_name"],
            }
    except requests.RequestException as e:
        print(f"    [HTTP ERROR] {e}")
    return None


def auto_query(name: str) -> str:
    """Fallback: convert node name to a search string."""
    readable = name.replace("_", " ")
    return f"{readable}, Vietnam"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN AUDIT LOOP
# ─────────────────────────────────────────────────────────────────────────────

def audit_pool(pool_name: str, nodes: list, results: list):
    print(f"\n{'─'*60}")
    print(f"  Auditing {pool_name}  ({len(nodes)} nodes)")
    print(f"{'─'*60}")

    for stored_lat, stored_lon, name in nodes:
        query = QUERY_MAP.get(name, auto_query(name))
        print(f"  [{name}]  query: \"{query}\"")

        geo = nominatim_geocode(query)
        time.sleep(SLEEP_S)   # respect Nominatim rate limit

        if geo is None:
            print(f"    ⚠  NO RESULT from Nominatim — cannot verify")
            results.append({
                "pool": pool_name, "name": name,
                "stored": [stored_lat, stored_lon],
                "osm": None, "delta_km": None,
                "status": "NO_RESULT",
            })
            continue

        osm_lat, osm_lon = geo["lat"], geo["lon"]
        delta = haversine(stored_lat, stored_lon, osm_lat, osm_lon)

        if delta >= ERROR_KM:
            status = "ERROR"
            tag = f"✗ ERROR   Δ={delta:.1f} km"
        elif delta >= WARN_KM:
            status = "WARNING"
            tag = f"△ WARNING Δ={delta:.1f} km"
        else:
            status = "OK"
            tag = f"✓ OK      Δ={delta:.1f} km"

        print(f"    stored=({stored_lat}, {stored_lon})  "
              f"osm=({osm_lat:.4f}, {osm_lon:.4f})  {tag}")
        if status != "OK":
            print(f"    osm place: {geo['display_name'][:90]}")

        results.append({
            "pool":       pool_name,
            "name":       name,
            "query":      query,
            "stored":     [stored_lat, stored_lon],
            "osm":        [osm_lat, osm_lon],
            "delta_km":   round(delta, 2),
            "status":     status,
            "osm_place":  geo["display_name"],
        })


def main():
    print("=" * 60)
    print("  DRND Node Coordinate Audit — Nominatim / OSM")
    print("=" * 60)
    print(f"  WARN threshold : {WARN_KM} km")
    print(f"  ERROR threshold: {ERROR_KM} km")

    results = []

    # Audit all three pools
    audit_pool("ORIGIN",  ORIGIN_NODES,  results)
    audit_pool("HUB",     HUB_NODES,     results)
    audit_pool("DEMAND",  DEMAND_NODES,  results)

    # ── Summary ───────────────────────────────────────────────────────────────
    errors   = [r for r in results if r["status"] == "ERROR"]
    warnings = [r for r in results if r["status"] == "WARNING"]
    no_res   = [r for r in results if r["status"] == "NO_RESULT"]
    ok       = [r for r in results if r["status"] == "OK"]

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Total audited : {len(results)}")
    print(f"  ✓ OK          : {len(ok)}")
    print(f"  △ WARNING     : {len(warnings)}")
    print(f"  ✗ ERROR       : {len(errors)}")
    print(f"  ⚠ NO_RESULT   : {len(no_res)}")

    if errors:
        print(f"\n  Nodes requiring correction (ERROR ≥ {ERROR_KM} km):")
        for r in sorted(errors, key=lambda x: -x["delta_km"]):
            print(f"    [{r['pool']:6s}] {r['name']:35s}  "
                  f"stored=({r['stored'][0]}, {r['stored'][1]})  "
                  f"osm=({r['osm'][0]:.4f}, {r['osm'][1]:.4f})  "
                  f"Δ={r['delta_km']:.1f} km")

    # ── Write JSON report ─────────────────────────────────────────────────────
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "audit_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"results": results,
                   "summary": {
                       "total": len(results),
                       "ok": len(ok),
                       "warning": len(warnings),
                       "error": len(errors),
                       "no_result": len(no_res),
                   }}, f, indent=2, ensure_ascii=False)
    print(f"\n  Full report written to: {out_path}")
    print("  Done.")


if __name__ == "__main__":
    main()
