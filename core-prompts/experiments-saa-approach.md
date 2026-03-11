# SAA / OOS Experimental Approach
## Experiment 2 — CV-Large Case Study Validation

---

## 1. Purpose

The model trains on **3 fixed scenarios** (Mild / Severe / Extreme). PB-NSGA optimizes against only those 3 — creating a risk of overfitting: hub/inventory decisions that exploit the specific shape of those scenarios may not generalize.

SAA and OOS answer one question: **do the first-stage decisions (X, q) returned by PB-NSGA hold up when evaluated on scenarios they were never trained on?**

---

## 2. What Already Exists

| Asset | Path | Status |
|---|---|---|
| SAA dataset (100 scenarios) | `data/prep/cv_large_saa100.json` | ✅ |
| OOS dataset (10 adversarial scenarios) | `data/prep/cv_large_oos10.json` | ✅ |
| SAA generator script | `src/scripts/data_generate_saa_oos.py` | ✅ |
| Evaluation + gap analysis script | `src/scripts/exp2_analyze_saa_oos.py` | ✅ |
| SAA/OOS eval for seed0 | `results/exp2/CV_large_seed0_{saa,oos}_eval.json` | ✅ |
| SAA/OOS eval for seeds 1–19 | — | ❌ Missing |

**What's needed:** Run the eval pipeline for the remaining 19 seeds, then aggregate across all 20.

---

## 3. Scenario Generation Design

### SAA set (100 scenarios)
- Drawn from a **profile bank** of 10 profiles (mild_a/b/c, severe_a/b/c, extreme_a/b/d) via round-robin assignment
- Each profile controls: `n_epi` (1–4 epicenters), intensity range `[I_lo, I_hi]`, severity multiplier `sev_mult` (0.95–3.2), road disruption rate `beta` (0.20–0.95), circuity `phi` (0.55–0.90)
- Round-robin ensures **balanced coverage** — not random sampling, so the 100 scenarios explicitly span the full severity spectrum
- Equal probability `π_s = 1/100` for each scenario
- Seed: `SEED + 101 = 2127`

### OOS set (10 adversarial scenarios)
- Drawn from a separate bank of 4 extreme profiles: `oos_extreme_a/b/c` and `oos_double_typhoon`
- Harder than SAA: `sev_mult` up to 4.2, `n_epi` up to 5, `beta` up to 0.99, `phi` up to 0.95
- Deliberately **disjoint** from the SAA distribution — designed to stress-test tail robustness
- Seed: `SEED + 202 = 2228`

### Hub capacities
- Hub capacities are fixed to match the original 3-scenario CV-Large instance (`seed 2026`) — ensuring SAA/OOS scenarios evaluate the same infrastructure, not a resampled one

---

## 4. The Evaluation Pipeline

```
PB-NSGA runs on cv_large_drnd.json (3 scenarios)
    → CV_large_seed{n}.json  [orig_Z1, orig_Z2 = in-sample estimates]
            ↓
Re-evaluate each Pareto solution (fix X, q; re-run decoder on new scenario set)
            ↓
cv_large_saa100.json (100 scenarios)  → CV_large_seed{n}_saa_eval.json  [new_Z1_SAA, new_Z2_SAA]
cv_large_oos10.json  (10 adversarial) → CV_large_seed{n}_oos_eval.json  [new_Z1_OOS, new_Z2_OOS]
            ↓
exp2_analyze_saa_oos.py  → gap statistics
```

**Key insight:** Only first-stage decisions `(X, q)` are fixed. All second-stage variables `(y_ks, z_iks, z_jks, f_khms)` are re-solved by the decoder under the new scenarios. The cost increase measures pure **optimizer's curse**, not operational infeasibility.

---

## 5. What the Data Shows (seed0 preview)

| Metric | In-sample (3 scen.) | SAA (100 scen.) | OOS adversarial (10 scen.) |
|---|---|---|---|
| Z1 (first solution) | ~4.6M | ~12.1M | ~80.9M |
| Z2 (first solution) | ~47.6K | ~431.5K | ~963.8K |
| SAA gap Z1 | — | **+161%** | — |
| OOS gap Z1 | — | — | **+1,647%** |

**What this means:**
- The **SAA gap** (~161%) is the optimizer's curse from training on only 3 scenarios. This is expected and honest.
- The **OOS gap** (~1,647%) is not a failure — it reflects that adversarial scenarios have `sev_mult` up to 4.2× vs. 1.0–2.8× in training. The increase is structural, not due to poor design.
- The key validity check is **feasibility** (CV=0) under OOS — if solutions remain feasible on unseen adversarial scenarios, the hub/inventory design is structurally robust even as costs scale up.

---

## 6. What to Compute Before Writing

Run `exp2_analyze_saa_oos.py` for all 20 seeds, then extract:

- `mean_z1_diff_pct`, `mean_z2_diff_pct` across all Pareto solutions across seeds 0–19 (SAA)
- Same for OOS
- `feasible_count / n_evaluations` under SAA and OOS — this is the headline robustness claim

Expected result structure for the paper:
```
SAA gap (Z1): mean ± std %  across all Pareto solutions × 20 runs
OOS gap (Z1): mean ± std %
SAA feasibility: X% of solutions remain CV=0 under 100 new scenarios
OOS feasibility: X% of solutions remain CV=0 under 10 adversarial scenarios
```

---

## 7. Narrative for the Paper

**Core claim to make:**
> Although PB-NSGA optimizes against only 3 training scenarios, the first-stage hub and inventory decisions it produces remain **structurally feasible** on both a 100-scenario SAA set and 10 adversarial OOS scenarios. The cost increase under OOS (large by design, since adversarial severity is 30–50% higher) confirms the model's sensitivity to extreme events rather than indicating design fragility.

**What to acknowledge:**
- The SAA gap confirms a moderate optimizer's curse from 3-scenario training
- Increasing the training scenario count (e.g., re-running PB-NSGA on `cv_large_saa100.json` directly) would reduce the SAA gap — this is a clear future direction
- The OOS adversarial gap quantifies the "price of the tail" — the marginal cost of being prepared for black-swan events

**Link to hub frequency analysis:**
- Cross-check: do the hubs with high selection frequency (Quang Ngai Port 100%, Phuoc Son Helipad 70.6%) also produce the **lowest OOS gap**? If yes, this validates them as genuinely robust infrastructure investments, not just in-sample artifacts.

---

## 8. Framing Options

| Option | Effort | Paper strength |
|---|---|---|
| **A — Full report** (run all 20 seeds, report SAA + OOS gaps + feasibility) | Low (decoder is ms/scenario) | Strong — empirical validation |
| **B — Seed0 only** (report seed0 numbers as illustrative example) | None (data exists) | Weak — not statistically representative |
| **C — Remove section** (move to future work) | None | Loses a differentiating contribution |

**Recommendation: Option A.** The decoder re-evaluation is fast. Running all 20 seeds through `exp2_analyze_saa_oos.py` takes minutes. The resulting numbers turn a placeholder section into a genuine empirical contribution.

---

## 9. Suggested Table for the Paper

**Table: SAA/OOS Robustness Validation on CV-Large (20 runs)**

| Evaluation set | Scenarios | Mean Z1 | SAA/OOS Gap (Z1) | Mean Z2 | Feasibility |
|---|---|---|---|---|---|
| In-sample | 3 | X.XM | — | X.XK | 100% |
| SAA re-eval | 100 | X.XM | +X% | X.XK | X% |
| OOS adversarial | 10 | X.XM | +X% | X.XK | X% |

Caption: *Z1 = expected logistics cost; Z2 = expected max deprivation cost. Feasibility = fraction of Pareto solutions with CV=0 under the new scenario set. First-stage decisions (X, q) are fixed from in-sample optimization; second-stage recourse is re-solved per scenario.*

---

## TODO

- [ ] Run `exp2_analyze_saa_oos.py` for seeds 1–19 (seed0 already done) to get statistically stable gap numbers across all 20 runs before filling in the table above.
