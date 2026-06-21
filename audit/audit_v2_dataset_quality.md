# V2 Dataset Quality Audit

**Date:** 2026-06-21

---

## 1. Near-full Inventory Pre-positioning (R ≈ 1) on v2

### Observation
PB-NSGA solutions on both CV-Small and CV-Large v2 fill most open hubs to R = 0.85–1.00, far higher than v1 solutions. This raised the question: algorithm weakness or data necessity?

### Answer: primarily data-driven, with one systematic exception

**Raw saturation looks benign** — extreme-scenario demand is only ~44–46% of total hub capacity on both instances. Naively, hubs should only need ~45% fill.

**Accessibility constraints change everything.** V2 has 47 air-only hub-demand pairs (vs 12 on v1). Air-only demand nodes have no routing alternative; the sole accessible hub must hold enough inventory to fund all vehicle trips. With air vehicle cap = 10 and ~15K demand per node, a single air-only demand node can consume 1,500 trip-equivalents of hub inventory. This saturates small-to-medium hubs (e.g., A_Luoi at 77K capacity) even before addressing other demand nodes.

**The capacity-demand squeeze.** V2 hub capacity is 4.7× smaller than v1 (population-anchored redesign) while demand is 1.6× higher. Per-hub demand/capacity ratio is ~7.7× tighter. Hubs that had comfortable slack on v1 are genuinely near-saturation on v2.

**MILP ground truth (CV-Small).** Comparing MILP-AWS's exact R allocation against PB-NSGA's:

| Hub | Cap | PB-NSGA R | MILP R | Verdict |
|---|---|---|---|---|
| Dong_Giang_Rescue_Stn | 108,724 | 1.00 | 0.96–1.00 | data-driven |
| Thang_Binh_Depot | 104,651 | 1.00 | 0.85–1.00 | data-driven |
| A_Luoi_Relief_Center | 77,256 | 0.86–1.00 | 0.77–1.00 | data-driven |
| Da_Nang_Airport_Hub | 164,561 | 0.89–1.00 | 0.64–0.94 | mixed |
| **Tam_Ky_Logistics_Hub** | **207,168** | **0.45–1.00** | **0.25–0.43** | **algorithm weakness** |

The three smallest hubs are genuinely near-full by data necessity. Tam_Ky — the *largest* hub — is the systematic exception: MILP proves 25–43% suffices, yet PB-NSGA fills it 45–100%.

**Why PB-NSGA over-fills Tam_Ky.** Tam_Ky has the highest capacity (207K) and broad accessibility, meaning its marginal Z2 gain per unit of inventory is low — it covers demand nodes already reachable from other hubs. MILP's LP dual prices detect this instantly. PB-NSGA's evolutionary operators on R vectors have no such signal; the population converges to a "fill everything" heuristic.

**CV-Large corroborates.** Only 1 of 14 PF solutions fills ALL open hubs to R > 0.95. Per-hub R ranges are wide (e.g., A_Luoi: 0.19–1.00, Phuoc_Son: 0.29–1.00), showing the algorithm does explore partial fill on the larger instance. Hubs that stay consistently near-full across the front (Nam_Giang, Binh_Son, Que_Son, Quang_Ngai_Port) are those with concentrated, accessibility-constrained demand — genuine data pressure, not algorithm bias.

### Implication for the paper
Near-full R on v2 is not a sign of a degenerate dataset. It is the correct response to tighter capacity and restricted accessibility. The only algorithmically-caused over-fill is at the single largest-capacity hub, which is the same failure mode identified in `evaluate_pbnsga_v2data.md` (§3b).

---

## 3. The Z1/Z2 Tradeoff: Why More Expensive Pre-positioning Yields Less Deprivation

### Observation

MILP-AWS solutions on v2 CV-Small occupy Z1 ∈ [$11.08M, $17.84M] yet achieve Z2 ∈ [67,859, 109,923] — far below PB-NSGA's Z2 ∈ [114,693, 128,154] at lower Z1 ∈ [$9.50M, $11.06M]. Counterintuitively, the more expensive supply-chain solutions produce less deprivation, not more.

### Root cause: geography of supply vs. geography of demand

Z1 is the cost of transporting supplies from the two coastal origin depots (Hai_Van_Pass_North and Dung_Quat_Port) to hub staging areas. Z2 is the Daganzo deprivation cost of moving rescue resources from hubs to demand nodes. These are **geographically opposed gradients**:

| Hub | Min supply cost ($/trip from nearest origin) | Mean rescue theta (extreme sc) | Hub type |
|---|---|---|---|
| Da_Nang_Airport_Hub | **$52** (cheapest) | 758,160 | Coastal |
| Tam_Ky_Logistics_Hub | $80 | 896,893 (worst) | Coastal-plain |
| Thang_Binh_Depot | $152 | 620,560 | Midland |
| Dong_Giang_Rescue_Stn | $203 | **508,734 (best)** | Highland |
| A_Luoi_Relief_Center | $352 (most expensive) | 3,898,541* | Deep highland |

*A_Luoi's high mean is skewed by a few BIG_M-adjacent pairs; its minimum theta is 112, best-in-class for the demand nodes it uniquely serves.

**The coastal hubs are cheap to supply because they are close to the origin depots — but for the same geographic reason, they are far from the highland demand zones.** In the extreme scenario (road network severely disrupted), Da_Nang has road access to only 1 of 20 demand nodes. All other serves require air transport at $40/km, which inflates theta enormously for distant demand nodes.

**The inland hubs are expensive to supply because they are far from the coastal origins — but for the same reason, they are located among the highland demand nodes.** Dong_Giang and A_Luoi have direct water-route access to nearby highland communes at low travel cost, yielding the lowest theta values per served unit.

### How each algorithm responds

**MILP-AWS** (via LP dual prices): detects that Da_Nang's marginal Z2 return per unit of inventory is poor — it can barely serve any demand node cheaply in the extreme scenario. MILP redirects supply budget to Dong_Giang and A_Luoi, paying more Z1 ($200–640/trip vs. $52/trip) but recovering far more Z2 per dollar. The LP dual price on the Z2 constraint resolves this exchange precisely.

**PB-NSGA**: stocks Da_Nang heavily because it is the cheapest hub to fill, and evolutionary R-vector crossover has no mechanism to attribute Z2 improvement to specific hub-inventory decisions. The algorithm discovers the cheap Z1 region but cannot escape it.

### Why Da_Nang being open isn't just bad

Da_Nang's one road-accessible demand node (Dien_Ban_District, theta = 43,414 from Da_Nang vs. 229,252 from the next-best hub) and second-best theta for Phu_Loc_District mean it IS useful for 2 of 20 demand nodes. The MILP solutions that include Da_Nang are not wrong — they simply allocate it a lower inventory ratio (64–94%) rather than filling it to 100% the way PB-NSGA does. The error is not in opening Da_Nang; it is in oversupplying it at the expense of inland hubs.

### Implication for the paper

The Z1/Z2 tradeoff on v2 is not an artifact — it faithfully represents the central-Vietnam geography: coastal logistics infrastructure vs. highland population exposure. A decision-maker choosing a high-Z1 MILP solution is explicitly paying for better inland hub coverage, which is the correct pre-positioning strategy for reducing humanitarian deprivation in an extreme highland flood.

---

## 2. Pareto Front Size: v2 CV-Small has 31 solutions vs v1's 9

### Observation
PB-NSGA finds 31 CV=0 Pareto-front solutions on v2 CV-Small vs 9 on v1, across 5 distinct hub configurations vs 2.

### Explanation: two independent effects

**Effect 1 — More hub configurations are mutually non-dominated (2 → 5).** On v1, hub costs and theta are small, so one configuration quickly dominates another. On v2, theta is 9× larger: swapping one hub for another causes dramatic, asymmetric Z1/Z2 shifts. Configurations that were dominated in v1's compact objective space are now well-separated and genuinely non-dominating.

**Effect 2 — Wider objective space accommodates more R variations per configuration.** Within v1's best configuration, 7 solutions span Z1 $1.6M–$2.6M and Z2 78,600–81,600 (a Z2 width of ~3,000). The equivalent v2 configuration spans Z1 $9.5M–$16.4M and Z2 94,337–128,154 (Z2 width ~33,800 — 11× wider). NSGA-II's crowding-distance mechanism preserves solutions spread across this larger space; on v1's narrow front they would have been crowded out.

### Implication
A larger Pareto front is not evidence of better algorithm performance — it reflects a richer, more fragmented objective landscape on v2. The front is wider but not necessarily higher quality (MILP still dominates the Z2-optimal half; see `evaluate_pbnsga_v2data.md`).
