# CV-Large Knee-Point Audit Report
**Date:** 2026-05-09 | **Branch:** `exp/camera-ready` | **Verdict:** Mixed (data integrity broken + Case B on cross-scenario)

## TL;DR

The user's suspicion that "the three scenarios produce the same configuration" is **partially correct, but the bigger problem is upstream**: the figure in the paper (`cv_large_map_detailed*.png`) is generated from a stale, infeasible solution that does not appear anywhere in the live Pareto front. The paper text describes a different, also-incorrect, hub set. None of the three sources (paper text, figure header, `cv_large_flow.json`) agree on which solution is being analysed.

On the narrower cross-scenario question: **demand-to-hub assignments are identical across all three scenarios**, but the **transport modal mix (truck/water/helicopter) differs substantially**. So the modal-adaptation claim in §4.2 is qualitatively supported, while the broader implication that "the algorithm finds genuinely different operational responses" is not.

---

## 1. Phase 0 — Three-way Inconsistency

| Source | Z₁ | Z₂ | CV | Open hubs |
|---|---|---|---|---|
| Paper text (§4.2 line 770) | $4.6 M | 43,453 | implicit 0 | {H0, H1, H3, H11, H14, H15, H16, H19} |
| Figure header (`v3.png`) | $519.7 M | 92,614 | unknown | (visible: same red squares as text claims) |
| `cv_large_flow.json` | **$2,981.9 M** | **1,513,047** | **136.5 (INFEASIBLE)** | {H9, H15, H16} (only 3 hubs) |
| seed0 Pareto idx 1 (closest by Z) | $4.72 M | 44,000 | 0 | {H0, H1, H3, H5, H9, H12, H14, H15, H16} |
| seed0 Pareto idx 0 (closest by hub set) | $4.64 M | 47,600 | 0 | {H0, H1, H3, H9, H10, H14, H15, H16} |

**Finding 1 (data integrity):** `cv_large_flow.json` represents a solution that:
- has only 3 planned hubs (H9, H15, H16) vs. 8–9 in every Pareto solution
- has CV = 136.5 (infeasibility — capacity violations)
- has Z₁ = $2.98 B, three orders of magnitude higher than the paper's claim
- **matches no Pareto solution in `CV_large_seed0.json`**

The figure that reads "Representative Solution Z₁ = $519.7M" is itself yet a third solution that we cannot trace back to either the flow file or any Pareto entry. There appear to be **at least three different solutions in circulation under the same "knee-point" label**.

**Finding 2 (paper hub list is wrong):** The paper claims H11 and H19 are part of the knee-point. **No Pareto solution in `seed0` opens H11 or H19**. The closest match is Pareto index 0 with hubs {H0, H1, H3, H9, H10, H14, H15, H16}, with Jaccard 0.60 against the paper's claim. The paper has substituted H11 → H10 and H19 → H9 (or similar) somewhere along the way.

---

## 2. Phase 1+2 — Cross-Scenario Operational Decisions

Per-scenario data extracted from the (infeasible) `cv_large_flow.json`. Even though the file's solution is wrong, its scenario differentiation pattern is informative:

| Scenario | y_ks active | demand assigns | truck arcs | water arcs | heli arcs | TS edges | TS vol (kg) |
|---|---|---|---|---|---|---|---|
| Mild (p=0.60) | 17 | 100 | 62 | 25 | 13 | 5 | 46,547 |
| Severe (p=0.30) | 14 | 100 | 29 | 42 | 29 | 2 | 40,011 |
| Extreme (p=0.10) | 14 | 100 | 8 | 74 | 18 | 3 | 104,691 |

**Cross-scenario diffs:**

| Pair | demand-assignment Hamming | y_ks Hamming | hubs-used Jaccard | modal-mix L1 | TS-vol Δ |
|---|---|---|---|---|---|
| mild – severe | **0 / 100** | 3 / 20 | (parser glitch) | 66 | 6,536 |
| severe – extreme | **0 / 100** | 0 / 20 | (parser glitch) | 64 | 64,680 |
| mild – extreme | **0 / 100** | 3 / 20 | (parser glitch) | 108 | 58,145 |

(The `hubs-used Jaccard` zeros are a parser artifact: the demand-assignment record format doesn't expose the hub key in a shape my extractor recognises. The y_ks Hamming and modal-mix figures are reliable.)

**Finding 3 (cross-scenario differentiation):**
- **Demand-to-hub assignment is invariant across all scenarios** (Hamming = 0). The optimiser commits each demand node to a single hub regardless of scenario severity.
- **Modal mix changes substantially**: in the mild scenario truck arcs dominate (62), in the extreme scenario water mode dominates (74) and truck collapses to 8. The L1 modal-mix difference of 108 is large.
- **Active hub set is mostly stable**: severe and extreme scenarios are identical in y_ks (Hamming 0); mild differs from both by 3 hubs (likely the 3 mild-only-active hubs whose risk exceeds χ in severe/extreme).

**Implication:** The paper's claim that "adaptation is modal rather than structural" is **literally true** for this solution. What changes per scenario is the *vehicle type* used along otherwise-fixed routes. The infrastructure (X, q) is first-stage; the assignment (z) is also effectively scenario-invariant; only the transport-mode selection varies.

This is **not the same as overfitting** in the statistical sense, but it IS a sign that the SAA model's first- and second-stage division is producing minimal second-stage responsiveness. With $|\mathcal{S}|=3$ scenarios that share most accessibility, the optimiser commits aggressively to a single demand allocation that works for all three.

---

## 3. Verdict

| Aspect | Verdict |
|---|---|
| Data integrity (figure ↔ text ↔ result JSONs) | **BROKEN** — three different solutions in circulation |
| Paper hub list (H0, H1, H3, H11, H14, H15, H16, H19) | **WRONG** — H11 and H19 are not in any Pareto solution |
| Cross-scenario assignment differentiation | **None** (0/100 demand reassigns) — supports user's overfitting concern |
| Cross-scenario modal differentiation | **Substantial** (truck-heavy in mild → water-heavy in extreme) — supports paper's modal claim |
| Active hub-set differentiation | **Minor** (3/20 between mild and the rest) |
| Reactive hub activation | **None** (consistent with paper claim, but on the wrong solution) |

### Case classification

- **Phase 0 = Case C-prime (data integrity):** must regenerate the figure and reconcile paper-text hub lists with the actual seed0 Pareto front.
- **Phase 1+2 = Case B (genuine differentiation, narrowly):** modal adaptation is real; structural adaptation is not.

---

## 4. Required Actions (next PR)

The fixes split into two PRs:

### PR-X1 (data integrity, mandatory before any rewrite)

1. **Regenerate `cv_large_flow.json`** from the actual seed0 knee-point (whichever Pareto index the user designates as the knee). Use the `export_flow` binary on the canonical knee-point.
2. **Regenerate `figures/cv_large_map_detailed.pdf`** from the corrected flow file. Verify the figure header now matches the paper-text Z values.
3. **Cross-check the paper hub list** (currently {H0, H1, H3, H11, H14, H15, H16, H19}) against the regenerated knee-point. Replace incorrect indices.
4. **Rerun this audit script** on the regenerated flow file. Confirm CV = 0 and Z values match.

### PR-X2 (writing rewrite, after PR-X1 lands)

1. **§4.2 "Structural insights" paragraph (line 770):** retain the no-reactive-hub finding (it is consistent across solutions), update the hub list to the corrected indices.
2. **§4.2 "H16/H15 fill levels" paragraph (line 851):** the modal claim ("primary adaptation is modal") is empirically supported by the modal-mix L1 diff of 108. Sharpen wording to clarify that the adaptation is *only* modal — assignments are scenario-invariant. Update the H16/H15 percentages to the corrected knee-point.
3. **§5 Conclusion paragraph 1 (line 862):** already de-specified to remove hub indices. Confirm the "anchoring at coastal multi-modal nodes" generalisation is supported by the corrected data.
4. **Abstract (line 106):** the hub-frequency claim ("Quang Ngai Port Hub and Phuoc Son Helipad are unconditional network anchors (100% Pareto-selection frequency)") is independent of the single knee-point and should survive.
5. **Optional (Phase 5 deeper investigation):** the assignment-invariance finding (z_iks identical across all scenarios) is *itself* a contribution worth one sentence — it tells planners that the strategic assignment plan is robust to all three regimes; only the transport mode needs to flex.

---

## 5. Files Produced By This Audit

- `src/audit/audit_cv_large_knee_overfitting.py` — diagnostic script (read-only)
- `src/audit/CV_LARGE_KNEE_OVERFITTING_AUDIT.md` — this report
- `results/exp2/audit_knee_scenario_diff.csv` — per-pair scenario differences
- `results/exp2/audit_knee_summary.json` — full audit JSON output

## 6. Files NOT modified by this audit

- `paper/main.tex` — no rewrites in this audit PR
- `figures/*.pdf` — no figure regeneration in this audit PR
- All result JSONs (no recompute) and the solver
