import json
import urllib.request
import time

# fmt: off
ALL_REAL_NODES = [
    (15.8732, 108.3341, "Hoi_An_City",            "demand"),
    (15.9374, 108.3036, "Dien_Ban_District",       "demand"),
    (15.4300, 108.2073, "Nui_Thanh_District",      "demand"),
    (15.7562, 108.2461, "Thang_Binh_District",     "demand"),
    (16.0752, 108.1491, "Dai_Loc_District",        "demand"),
    (15.9867, 107.9883, "Dong_Giang_District",     "demand"),
    (16.2114, 108.0243, "Tay_Giang_District",      "demand"),
    (16.3012, 107.8631, "A_Luoi_District",         "demand"),
    (16.2321, 108.1572, "Nam_Giang_District",      "demand"),
    (16.1004, 107.7321, "A_Vuong_Commune",         "demand"),
    (15.9421, 108.2631, "Viet_An_Commune",         "demand"),
    (16.0123, 108.0961, "Que_Son_District",        "demand"),
    (16.1543, 108.2871, "Phu_Ninh_District",       "demand"),
    (15.5600, 108.3600, "Tam_Ky_City",             "demand"),
    (16.4321, 107.9321, "Huong_Tra_District",      "demand"),
    (16.4612, 107.7832, "Huong_Thuy_District",     "demand"),
    (16.3421, 108.0012, "Nam_Dong_District",       "demand"),
    (16.5612, 107.8741, "Phu_Loc_District",        "demand"),
    (16.4001, 107.6521, "A_Luoi_Mountain",         "demand"),
    (16.2812, 107.5321, "Nam_Dong_Highland",       "demand"),
    (16.0543, 108.2022, "Da_Nang_City",            "demand"),
    (15.9123, 108.1541, "Cam_Le_District",         "demand"),
    (16.1232, 108.1982, "Lien_Chieu_District",     "demand"),
    (16.0012, 108.2401, "Son_Tra_District",        "demand"),
    (15.8721, 108.0841, "Thanh_Khe_District",      "demand"),
    (16.2432, 108.0762, "Hoa_Vang_District",       "demand"),
    (15.7321, 108.1432, "Phu_Yen_Commune",         "demand"),
    (15.3200, 107.8341, "Bac_Tra_My",              "demand"),
    (15.8453, 107.9872, "Nam_Tra_My",              "demand"),
    (15.6721, 108.0341, "Hiep_Duc_District",       "demand"),
    (15.5631, 108.2541, "Tien_Phuoc_District",     "demand"),
    (15.4321, 108.4012, "Nui_Thanh_South",         "demand"),
    (15.6012, 108.3341, "Tam_Ky_South",            "demand"),
    (16.5123, 107.6012, "Phu_Loc_West",            "demand"),
    (16.6321, 107.7821, "Phu_Vang_District",       "demand"),
    (16.5543, 107.9321, "Quang_Dien_District",     "demand"),
    (16.4872, 108.1012, "Phong_Dien_District",     "demand"),
    (16.4631, 108.2621, "Hue_City_South",          "demand"),
    (16.4631, 107.4321, "Khe_Tre_Commune",         "demand"),
    (15.7143, 107.8101, "Tra_Don_Commune",         "demand"),
    (15.5832, 107.9431, "Tra_Nam_Commune",         "demand"),
    (16.7012, 107.5831, "Lang_Co_Area",            "demand"),
    (16.6012, 107.3541, "Truoi_Lake_Area",         "demand"),
    (15.9432, 107.5932, "Vu_Gia_River_South",      "demand"),
    (16.1321, 107.4531, "Song_Bung_Lake",          "demand"),
    (16.0743, 107.3021, "A_Sap_Valley",            "demand"),
    (15.8123, 107.6321, "Phuoc_Son_District",      "demand"),
    (15.6831, 107.7851, "Tra_My_Highlands",        "demand"),
    (16.3012, 107.2321, "Bach_Ma_Forest",          "demand"),
    (16.5412, 107.1081, "A_Luoi_Valley",           "demand"),
    (16.7832, 107.4231, "Huong_An_Commune",        "demand"),
    (16.0231, 108.3491, "Tho_Quang_Ward",          "demand"),
    (15.9812, 108.1721, "Hoa_Cuong_Ward",          "demand"),
    (15.8342, 108.0012, "An_Tan_Commune",          "demand"),
    (16.1891, 107.9341, "Lac_My_Commune",          "demand"),
    (16.3543, 107.6521, "Hong_Ha_Commune",         "demand"),
    (16.5014, 107.8031, "Quang_An_Ward",           "demand"),
    (16.2231, 107.3041, "Huong_Xuan_Commune",      "demand"),
    (15.6521, 108.1341, "Tam_Viet_Commune",        "demand"),
    (15.4832, 108.3031, "Tam_Hiep_Commune",        "demand"),
    (15.7981, 108.4201, "Binh_Duong_Commune",      "demand"),
    (16.8012, 107.5321, "Phu_Dien_Ward",           "demand"),
    (16.0821, 108.4312, "My_Khe_Beach_Area",       "demand"),
    (16.9321, 107.3012, "A_Dot_Commune",           "demand"),
    (15.3301, 108.5501, "Tam_Quan_Town",           "demand"),
    (15.2431, 108.4231, "Nuoc_Trong_Reservoir",    "demand"),
    (15.1241, 108.3121, "Duc_Pho_District",        "demand"),
    (16.9541, 107.1231, "A_Bat_Commune",           "demand"),
    (17.0231, 107.2031, "A_La_Commune",            "demand"),
    (17.1012, 107.0231, "Huong_Lap_Commune",       "demand"),
    (16.8501, 107.2501, "Cao_Ngan_Commune",        "demand"),
    (15.0541, 108.6541, "Mo_Duc_District",         "demand"),
    (15.1831, 108.7801, "Minh_Long_District",      "demand"),
    (15.8712, 108.5041, "Chu_Lai_Port",            "demand"),
    (15.4012, 107.8501, "Son_Ha_District",         "demand"),
    (15.2831, 107.7021, "Son_Tay_District",        "demand"),
    (15.0001, 107.9231, "Tra_Bong_District",       "demand"),
    (14.9321, 108.1431, "Nghia_Hanh_District",     "demand"),
    (14.8541, 108.3201, "Tu_Nghia_District",       "demand"),
    (15.1200, 108.4801, "Quang_Ngai_City",         "demand"),
    (14.9012, 108.5601, "Son_Tinh_District",       "demand"),
    (15.1231, 108.6271, "Binh_Son_District",       "demand"),
    (15.6121, 107.4031, "Khue_Trung_Valley",       "demand"),
    (16.7231, 107.6851, "Phu_Thuong_Ward",         "demand"),
    (16.9001, 107.4581, "Truong_Giang_Commune",    "demand"),
    (17.0721, 107.6231, "Son_Qua_Commune",         "demand"),
    (15.9301, 108.4521, "Xuan_Ha_Ward",            "demand"),
    (16.0051, 108.5201, "Man_Thai_Ward",           "demand"),
    (15.7231, 108.5501, "Phuoc_Hiep_Commune",      "demand"),
    (16.1751, 108.4201, "Hoa_Lien_Commune",        "demand"),
    (16.3121, 108.3721, "Hoa_Tien_Commune",        "demand"),
    (16.0321, 107.6531, "Zuoih_Commune",           "demand"),
    (15.8901, 107.4581, "Bha_Le_Commune",          "demand"),
    (15.6812, 107.2541, "Tra_Vie_Commune",         "demand"),
    (15.4981, 107.1081, "Ca_Dy_Commune",           "demand"),
    (15.2341, 107.0231, "Tra_Bui_Commune",         "demand"),
    (16.2521, 107.8951, "Ta_Lang_Commune",         "demand"),
    (16.4012, 107.4081, "Thuong_Quang_Commune",    "demand"),
    (16.6721, 107.2541, "A_Ngo_Commune",           "demand"),
    (16.8341, 107.0931, "A_Tuc_Commune",           "demand"),
    (15.5321, 107.5031, "Ca_Lu_Commune",           "demand"),
    # ── Hub candidates
    (16.0544, 108.2022, "Da_Nang_Airport_Hub",     "hub"),
    (15.5600, 108.3300, "Tam_Ky_Logistics_Hub",    "hub"),
    (16.4601, 107.5961, "A_Luoi_Relief_Center",    "hub"),
    (15.9700, 107.8600, "Dong_Giang_Rescue_Stn",   "hub"),
    (15.6400, 108.2100, "Thang_Binh_Depot",        "hub"),
    (16.3300, 108.0070, "Nam_Giang_Forward_Base",  "hub"),
    (16.5600, 107.8600, "Phu_Loc_Staging_Area",    "hub"),
    (15.4500, 108.4200, "Nui_Thanh_Reserve",       "hub"),
    (16.7200, 107.5900, "Lang_Co_Forward_Post",    "hub"),
    (15.2200, 108.6000, "Binh_Son_Warehouse",      "hub"),
    (16.9300, 107.2500, "A_Dot_Mountain_Base",     "hub"),
    (15.0500, 108.4000, "Quang_Ngai_Depot",        "hub"),
    (16.1500, 107.6200, "A_Sap_Helipad",           "hub"),
    (15.7800, 108.0500, "Que_Son_Facility",        "hub"),
    (16.8600, 107.8300, "Huong_Viet_Depot",        "hub"),
    (14.8700, 108.7900, "Quang_Ngai_Port",         "hub"),
    (15.6200, 107.7200, "Phuoc_Son_Helipad",       "hub"),
    (17.0500, 107.4300, "Rao_Trang_Base",          "hub"),
    (16.2800, 107.5100, "Bac_Tra_My_Depot",        "hub"),
    (15.4100, 107.5600, "Son_Ha_Hub",               "hub"),
    # ── Origins
    (16.1124, 108.1948, "Hai_Van_Pass_North",      "origin"),
    (15.4000, 108.3100, "Dung_Quat_Port",          "origin"),
    (15.7500, 108.4700, "Chu_Lai_Airport",         "origin"),
    (16.8800, 107.5500, "Thuan_An_Port",           "origin"),
    (14.7600, 108.6900, "Sa_Ky_Port",              "origin"),
    (17.1900, 107.0700, "Khe_Sanh_Entry",          "origin"),
    (15.3600, 107.8900, "Tra_Bong_Supply",         "origin"),
    (16.0100, 108.6400, "Da_Nang_Seaport",         "origin"),
    (16.9700, 107.7700, "Hue_Train_Station",       "origin"),
    (15.3800, 109.1000, "Ly_Son_Island_Supply",    "origin"),
    (16.4900, 108.2300, "Lang_Co_Beach_Base",      "origin"),
    (14.5700, 108.9800, "Duc_Pho_Harbor",          "origin"),
]
# fmt: on

bad = []
for lat, lon, name, typ in ALL_REAL_NODES:
    url = f"http://router.project-osrm.org/nearest/v1/driving/{lon},{lat}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get("code") == "Ok":
                dist = data["waypoints"][0]["distance"]
                # print(f"{name}: {dist}m")
                # If nearest road is > 2000m away, it's very likely in the sea or deep jungle
                # Sea coordinates typically map to the closest coastal road which is >5km away.
                if dist > 5000:
                    bad.append((name, lat, lon, dist))
    except Exception as e:
        print(e)
    # Be polite to demo server
    time.sleep(0.3)

print("\n--- SUSPICIOUS NODES (Nearest road > 5km) ---")
for b in bad:
    print(b)
