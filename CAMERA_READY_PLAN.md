# CAMERA_READY_PLAN.md
# Camera-Ready Revision Plan — CITA 2026 Paper #419
# Deadline: May 10, 2026 23:59 (EasyChair)
# Last updated: 2026-05-08

---

## 0. Overview

**Paper:** "Humanitarian Logistics Hub Network Design Under Uncertainty: A Multi-Objective Model and Priority-Based Genetic Algorithm for Central Coastal Vietnam"

**Format:** Springer LNCS (`\documentclass{llncs}`). Current page count: **14 pages**. Hard limit: **12 pages**. Every added result must displace weaker prose.

**Objective:** Respond to three reviewer concerns while also strengthening the experimental methodology enough to survive independent audit. The plan repairs these in parallel, not sequentially.

---

## 1. Three Scientific Claims — Kept Logically Separate

The current paper conflates Claims B and C, and addresses Claim A with an unfair run-count comparison. This plan repairs all three independently.

| # | Claim | Evidence Required | Status |
|---|-------|-------------------|--------|
| A | PB-NSGA finds better Pareto fronts than GWO-HD and VNS-TS | Exp 2 comparison under matched run budgets | **Partially done — 20 PB vs 5 baselines (unfair)** |
| B | Solutions trained on 3 scenarios remain structurally robust on unseen scenarios | CV-Large multi-seed SAA/OOS reevaluation | **Only seed 0 done** |
| C | 3 strategically calibrated profiles are sufficient for stable optimization | CV-Small OOS stability across N values + ablation vs N=10 hybrid | **Not done** |

---

## 2. Confirmed Repo State (Ground Truth)

| Item | Status |
|------|--------|
| PB-NSGA CV-Large seeds | 20 seeds on disk: `results/exp2/CV_large_seed{0..19}.json` |
| GWO-HD seeds | 5 seeds on disk: `results/exp2/cv_large_gwo_seed{0..4}.json`, ~5s each |
| VNS-TS seeds | 5 seeds on disk: `results/exp2/cv_large_vns_seed{0..4}.json`, ~180s each |
| SAA/OOS evaluation | Seed 0 only: 6 Pareto solutions, 100% feasible (CV=0), Z1 gap +174%, Z2 gap +911% |
| CV-Small exact Pareto fronts | 70 fronts: `results/saa_convergence/N{3,5,8,10,15,20,30}_rep{0..9}_bb.json` |
| SAA100 dataset | `data/prep/cv_large_saa100.json` (seed 2127, balanced profiles) |
| OOS10 dataset | `data/prep/cv_large_oos10.json` (seed 2228, adversarial: sev_mult 3.4–4.2) |
| evaluate_oos binary | Must be compiled: `src/solver/evaluate_oos.cpp` |
| 4 comment blocks | Drafted in `paper/main.tex` (lines ~162, ~380, ~537, ~716) — NOT yet applied to live LaTeX |
| `zhang2007moead` bib entry | Already in `paper/cite-class.bib` |

---

## 3. Execution Plan

### Phase 0 — Scope Freeze (Prerequisite, 5 min)

Lock excluded scope before writing a single line of code or LaTeX:

- ❌ Parameter tampering to force reactive hub activations on CV-Large
- ❌ MOEA/D implementation or comparison
- ❌ Retraining PB-NSGA on CV-Large with a different (larger) training scenario count
- ❌ Model reformulation of any kind

These exclusions protect methodological credibility and are infeasible before the deadline.

**Acceptable scope:** Adding post-hoc robustness evaluation and ablation on top of existing trained solutions. The model, its parameters, and the 20 existing PB-NSGA seeds are frozen.

---

### Phase 1 — Fix GWO-HD Fairness (parallel with all other phases, ~2 min)

**Problem:** Exp2 compares 20 PB-NSGA seeds vs 5 GWO-HD and 5 VNS-TS seeds. The shared reference front is dominated by PB-NSGA solutions, making the comparison unfair.

**Action:** Extend GWO-HD from 5 to 20 seeds. Each seed runs in ~5 seconds.

```bash
# In run_exp2_case_study.sh, find the GWO-HD loop block and change {0..4} to {5..19}
# Then run only Step 4 (GWO-HD):
for seed in {5..19}; do
    ./build/gwo_hd_baseline data/cv/cv_large.json \
        --seed $seed --output results/exp2/cv_large_gwo_seed${seed}.json
done
```

**Decision gate — VNS-TS:** Running 15 additional VNS-TS seeds costs ~45 minutes (15 × 180s).
- **Preferred path:** If time allows, run seeds 5–19. Recompute shared-reference HV/IGD+ with 20 runs each.
- **Fallback path:** Filter PB-NSGA analysis to seeds 0–4 at analysis time (`exp2_analyze_case_study.py` with `--max-seed 4`). Recompute metrics under matched 5-run budgets.
- **Either way:** The manuscript must explicitly state run counts per algorithm in the experimental setup paragraph. Do not use language implying fair comparison if budgets remain unequal.

**Verification:** Check `n_runs` field in the metrics output matches the chosen branch for all three algorithms.

---

### Phase 2 — Strengthen Claim B: CV-Large Multi-Seed Robustness (parallel with Phase 3, ~5 min compute)

**Problem:** Only seed 0 has been evaluated on SAA100 and OOS10. A single seed is not a valid robustness claim.

#### Step 2.1 — Batch evaluate_oos across all 20 seeds

Write `src/scripts/exp_oos_multiseed.py`:

```python
import subprocess, json, pathlib

BUILD = "./build/evaluate_oos"
SAA = "data/prep/cv_large_saa100.json"
OOS = "data/prep/cv_large_oos10.json"
SEEDS_DIR = pathlib.Path("results/exp2")
OUT_DIR = pathlib.Path("results/exp2")

for seed in range(20):
    front_file = SEEDS_DIR / f"CV_large_seed{seed}.json"
    if not front_file.exists():
        print(f"WARNING: missing {front_file}")
        continue
    for variant, dataset in [("saa", SAA), ("oos", OOS)]:
        out_file = OUT_DIR / f"CV_large_seed{seed}_{variant}_eval.json"
        if out_file.exists():
            continue  # skip already done
        subprocess.run([BUILD, str(dataset), str(front_file), str(out_file)], check=True)
        print(f"  Done: seed {seed} {variant}")
```

Expected outputs: 40 JSON files (`CV_large_seed{0..19}_{saa,oos}_eval.json`).

#### Step 2.2 — Extend exp2_analyze_saa_oos.py

The current script:
- Only processes seed 0
- Computes Z1/Z2 gap for SAA but NOT for OOS (missing new_Z2 aggregation)
- Does not aggregate at seed level

Required extensions:
1. Add OOS Z2 gap computation (field `new_Z2` already exists in eval JSON output)
2. Loop all 20 seeds, compute per-seed summary: `{seed, n_solutions, z1_gap_mean, z2_gap_mean, z1_gap_std, z2_gap_std, feasible_count, feasibility_rate}`
3. Aggregate across seeds: report `mean ± std` of each metric across the 20 seeds
4. **Do NOT pool all Pareto solutions** — seeds with larger fronts would dominate the headline statistic

#### Step 2.3 — Produce the robustness table

Paper-facing artifact — one compact table:

| Evaluation set | N scenarios | Z1 gap (%) | Z2 gap (%) | Feasibility rate | Seeds |
|---|---|---|---|---|---|
| In-sample training | 3 | — | — | 100% | 20 |
| SAA reevaluation | 100 | µ ± σ | µ ± σ | µ ± σ | 20 |
| OOS reevaluation (adversarial) | 10 | µ ± σ | µ ± σ | µ ± σ | 20 |

**CRITICAL FRAMING — must appear in table caption:**
> "The OOS set uses adversarially hard scenarios with severity multipliers 3.4–4.2×, compared to 0.95–3.0× in training. Large cost gaps are therefore structurally expected; the primary claim is feasibility maintenance (CV = 0) across all seeds."

The **primary claim is the feasibility rate column**, not the Z2 gap. The adversarial severity gap explains the cost numbers.

---

### Phase 2b — Stratified-vs-Random Scenario Design Ablation (parallel with Phase 2, ~10–15 min)

**Why:** The paper claims 3 calibrated profiles are sufficient. A reviewer can legitimately ask: "why not use 10 random scenarios instead?" This phase answers that question empirically.

**What:** Train PB-NSGA on a hybrid N=10 instance and compare OOS generalization head-to-head against the stratified 3-profile training. Both are evaluated on the same `cv_large_oos10.json` holdout.

#### Step 2b.1 — Generate `data/prep/cv_large_n10_hybrid.json`

The hybrid design (as agreed):
- **5 distribution-matched random scenarios:** Use the existing `_profile_bank()` (10 profiles covering mild/severe/extreme tiers) with a fresh random seed. Round-robin through all 10 profiles with `num_scenarios=10` via `generate_saa_scenarios(..., num_scenarios=10)`. This gives one scenario per profile, respecting tier bounds while randomizing parameters within them.
- **5 fully random scenarios:** Generate 5 scenarios with no profile constraint — random parameters drawn uniformly from the full range: `n_epi ∈ {1..5}`, `I_lo ∈ [0.2,1.0]`, `I_hi ∈ [I_lo, 1.2]`, `sev_mult ∈ [0.8,3.5]`, `beta ∈ [0.1,0.99]`, `phi ∈ [0.5,0.98]`, `risk_noise ∈ [0.01,0.07]`.

Create `src/scripts/data_generate_n10_hybrid.py` as a standalone script that:
1. Imports `build_instance_variant` infrastructure from `data_generate_saa_oos.py`
2. Builds the 10-scenario list (5 from `generate_saa_scenarios(..., num_scenarios=10)` + 5 fully random using `_scenario_from_profile` with a synthetic random-profile tuple)
3. Shuffles the combined list with a fixed seed (seed=9999) to avoid ordering bias
4. Assigns equal probabilities (1/10 each)
5. Writes to `data/prep/cv_large_n10_hybrid.json` in the same format as `cv_large.json`

**Important:** The fully random half must use a seed (e.g., 8888) that is documented and reproducible.

#### Step 2b.2 — Run PB-NSGA on the hybrid instance for 20 seeds

```bash
for seed in {0..19}; do
    ./build/solver data/prep/cv_large_n10_hybrid.json \
        --seed $seed \
        --generations 500 \
        --output results/exp2/cv_large_n10hybrid_seed${seed}.json
done
```

Estimated compute: ~20 × (same per-seed time as CV-Large ≈ 10s) = ~3–4 minutes.

#### Step 2b.3 — Evaluate all 20 hybrid-trained fronts on the OOS holdout

```bash
for seed in {0..19}; do
    ./build/evaluate_oos \
        data/prep/cv_large_oos10.json \
        results/exp2/cv_large_n10hybrid_seed${seed}.json \
        results/exp2/cv_large_n10hybrid_seed${seed}_oos_eval.json
done
```

#### Step 2b.4 — Aggregate and compare

Compute the same seed-level summary as Phase 2: per-seed feasibility rate, Z1 gap, Z2 gap, then mean ± std across 20 seeds. Add a row to the robustness table:

| Training design | Train scenarios | OOS Z1 gap | OOS Z2 gap | OOS feasibility |
|---|---|---|---|---|
| 3-profile stratified | 3 | µ ± σ | µ ± σ | µ ± σ |
| N=10 hybrid random | 10 | µ ± σ | µ ± σ | µ ± σ |

#### Step 2b.5 — Reporting paragraph (template)

Fill with actual numbers:

> "To empirically validate the scenario design, we trained PB-NSGA on a hybrid N=10 set (five scenarios drawn uniformly within severity-tier bounds and five fully unconstrained random draws) across 20 independent runs, and evaluated the resulting Pareto solutions on the same adversarial holdout. The stratified 3-profile design achieved [X]% feasibility with mean Z2 gap [Y]%, compared to [X′]% and [Y′]% for N=10 hybrid training. [If stratified ≥ hybrid:] The comparable — or superior — generalization of the calibrated design confirms that deliberate severity-range coverage, rather than scenario volume, is the operative factor in this problem class. [If hybrid is clearly better by >5 pp:] The marginal improvement from N=10 suggests the minimal-profile design provides competitive robustness within a data-scarce budget; extended scenario sets may further improve generalization in operational deployments."

**Contingency clause:** If N=10 hybrid OOS feasibility significantly exceeds the 3-profile design (>5 percentage points), report this honestly. The paper's primary contribution is the model formulation (MO-IHLNDP) and the PB-NSGA decoder architecture; the scenario design claim is secondary. Downgrade it to a limitation note.

---

### Phase 3 — Upgrade Claim C: CV-Small OOS Stability Across N (parallel with Phase 2, ~30 min)

**Problem:** The current SAA convergence section only shows that in-sample quality variance contracts as N grows. It never tests the key question: *do solutions trained on N=3 scenarios perform worse out-of-sample than solutions trained on N=10 or N=30?*

**Key insight:** 70 exact Pareto fronts already exist in `results/saa_convergence/`. They can be directly tested against a new OOS holdout at essentially zero compute cost.

#### Step 3.1 — Generate `data/prep/cv_small_oos10.json`

Use `data_generate_saa_oos.py` adapted for CV-Small (|H|=5, |I|=20, |J|=2):
- The existing generator hard-codes CV-Large size in `build_instance_variant`. Either add a `--small` flag or call `generate_oos_scenarios` directly with CV-Small node arrays.
- Use a different seed (e.g., seed=7777) that is disjoint from the training master pool seed (31415).
- Use 10 adversarial scenarios with the existing `oos_profiles` bank (sev_mult 3.4–4.2).

Verify disjointness: the training pool for CV-Small SAA used seed=31415 and the profile-bank SAA profiles; this OOS set uses a different seed and the adversarial-only profiles. They are disjoint by construction.

#### Step 3.2 — Run evaluate_oos on all 70 existing Pareto fronts

```bash
for N in 3 5 8 10 15 20 30; do
    for rep in {0..9}; do
        ./build/evaluate_oos \
            data/prep/cv_small_oos10.json \
            results/saa_convergence/N${N}_rep${rep}_bb.json \
            results/saa_convergence/N${N}_rep${rep}_oos_eval.json
    done
done
```

70 calls, each taking milliseconds. Total: under 5 seconds.

#### Step 3.3 — Aggregate by N

For each N: compute mean OOS Z2 gap ± std across the 10 reps. Plot or tabulate OOS Z2 gap as a function of N.

#### Step 3.4 — Interpret and report

Two scientifically honest outcomes:

**Outcome A (expected):** OOS gap is approximately flat across N values.
→ Report as: "OOS solution quality is stable across scenario counts, directly supporting the use of N=3 calibrated profiles. The stratified design achieves coverage that random up-sampling does not proportionally improve."

**Outcome B:** OOS gap worsens at small N.
→ Report honestly: "While in-sample variance contracts with N, OOS quality shows modest degradation at N=3, suggesting that profile stratification mitigates but may not fully eliminate the effect of limited scenario coverage. This is acknowledged as a boundary condition on the calibrated-profile claim."

**Do not suppress Outcome B.** Honest disclosure of a boundary condition is more credible than a paper that overstates its findings.

#### Step 3.5 — Rename the section

Change section title from "SAA Scenario Sensitivity Analysis" (or similar) to **"Scenario-Count Robustness Analysis"**.

Revised narrative structure:
1. In-sample: "Z2 variance contracts as N grows from 3 to 30 (Fig. X), with the exception of an N=5 spike attributable to the finite-pool sampling distribution."
2. OOS stability (new): "When solutions are evaluated against an independent adversarial holdout, OOS performance is [stable/shows the pattern described above], confirming that [the calibrated design's severity-range stratification provides equivalent generalization / acknowledging the limitation]."

---

### Phase 4 — Writing Integration (depends on Phases 2 and 3)

Apply the four drafted comment blocks from `paper/main.tex` to the live LaTeX in this order:

| Block | Location | Content |
|-------|----------|---------|
| R2 | Line ~162 | Problem/gap rewrite — apply first, no dependencies |
| R1.3 | Line ~380 | NSGA-II justification — apply second, no dependencies |
| R1.1 | Line ~716 | Reactive-hub defense — apply third, no dependencies |
| R1.2 | Line ~537 | SAA/robustness response — apply last, depends on Phase 2+3 outputs |

#### Tone-Down Contract (apply before committing any live LaTeX change)

Every sentence in the comment blocks must pass these tests before going live:

1. **SAA section:** No mean convergence claims. Allowed: "overall decreasing variance trend" + "OOS performance stability." Not allowed: "the model converges," "N=3 is equivalent to N=10."

2. **N=3 sufficiency:** The strong version ("N=3 is sufficient") is only valid if Phase 3 Outcome A holds AND the Phase 2b ablation shows competitive parity. Otherwise soften to "the calibrated design provides competitive generalization within a minimal-scenario budget."

3. **NSGA-II defense:** Say "appropriate for this problem class and consistent with the multi-objective humanitarian logistics literature." Do not claim superiority to MOEA/D in general. Cite the zhang2007moead bib entry in a comparative sentence, e.g., "While decomposition-based methods such as MOEA/D [zhang2007moead] have theoretical advantages in regular Pareto front approximation, NSGA-II's selection pressure is well-matched to the irregular, discontinuous fronts arising from incomplete hub network constraints."

4. **Reactive hub defense:** Say "a condition that does not arise under the current 20-hub CV-Large configuration — hub density is sufficient to absorb disruption without reactive activation — but is observable on CV-Small under severe and extreme scenarios where hub redundancy is lower." Do not say "the mechanism works perfectly."

5. **Run counts:** Add to Exp2 experimental setup paragraph: "PB-NSGA was run for R=20 independent seeds. [GWO-HD was extended to R=20 seeds / VNS-TS was run for R=5 seeds] to ensure a fair comparison." Whichever branch from Phase 1 was taken.

#### Page Budget Reconciliation

Starting point: 14 pages. Target: ≤ 12 pages.
Net additions: robustness table (~0.35p) + OOS stability paragraph + figure panel (~0.20p) + ablation paragraph (~0.15p) + writing additions (~0.20p) ≈ **+0.90 pages**.
Required cuts: 14 − 12 + 0.90 = **2.90 pages**.

Cuts in order of lowest risk:

| Cut | Location | Estimated saving |
|-----|----------|-----------------|
| Compress Related Works: merge 4 bold subheadings into 2 continuous paragraphs; keep all citations | Lines ~162–220 in main.tex | −0.40p |
| Remove post-constraint prose: constraint explanations after the equation block are largely redundant with the math | After constraint block | −0.20p |
| Compress Genetic Operators: merge 5 bold sub-items into one dense paragraph | Genetic operators section | −0.30p |
| Compress Decision Support: merge 3 italic subheadings into continuous prose | Decision support section | −0.30p |
| Trim abstract to ≤150 words: drop hub percentage figures (they appear in the body) | lines 115–130 | −0.15p |
| Merge Limitations into Future Work: one combined paragraph | Conclusion section | −0.10p |
| `\small` on algorithm pseudocode, or drop Require/Ensure lines | Algorithm environment | −0.20p |
| **Subtotal** | | **−1.65p** |

If still over after prose cuts: **replace the SAA variance figure with a compact inline 2-row table** and fold the OOS stability plot as a second panel within the existing figure space. Net saving: ~0.40p additional.

**Total target:** 1.65 + 0.40 = 2.05p cuts from compression + reduction in figure overhead. If the paper is still over by a margin, revisit the benchmark section (Exp1 tables can often be made more compact).

---

### Phase 5 — Compile, Validate, Submit

1. **Compile:** Run `latexmk -pdf paper/main.tex`. Check for undefined references, missing figures.
2. **Verify page count:** Must be ≤ 12. If over, apply the next cut from the ranked list above.
3. **Bibliography check:** Confirm `zhang2007moead` resolves; confirm all new `\cite{}` keys in the comment blocks exist in `paper/cite-class.bib`.
4. **Figures check:** Every `\includegraphics{...}` path must resolve under `paper/figures/`.
5. **Similarity check:** Run on compiled PDF. Paraphrase only regions that are actually flagged.
6. **Package:** `paper/main.pdf` + source ZIP (main.tex, cite-class.bib, figures/) + signed copyright transfer form.
7. **Submit:** EasyChair — https://easychair.org/conferences/?conf=cita2026 — before **May 10, 2026 23:59**.

---

## 4. File Map

| File | Action |
|------|--------|
| `run_exp2_case_study.sh` | Change GWO-HD loop to `{5..19}`; add VNS-TS extension if time permits |
| `src/scripts/exp_oos_multiseed.py` | **Create:** batch evaluate_oos for 20 PB-NSGA seeds (Phase 2.1) |
| `src/scripts/exp2_analyze_saa_oos.py` | **Extend:** add OOS Z2 gap + seed-level aggregation (Phase 2.2) |
| `src/scripts/data_generate_n10_hybrid.py` | **Create:** hybrid N=10 training instance generator (Phase 2b.1) |
| `src/scripts/exp_cv_small_oos_stability.py` | **Create:** run evaluate_oos on 70 fronts, aggregate by N (Phase 3.2–3.3) |
| `data/prep/cv_large_n10_hybrid.json` | **Generate:** output of data_generate_n10_hybrid.py |
| `data/prep/cv_small_oos10.json` | **Generate:** CV-Small adversarial holdout (Phase 3.1) |
| `results/exp2/CV_large_seed{0..19}_{saa,oos}_eval.json` | **Generate:** 40 eval outputs from exp_oos_multiseed.py |
| `results/exp2/cv_large_n10hybrid_seed{0..19}.json` | **Generate:** 20 PB-NSGA runs on hybrid training |
| `results/exp2/cv_large_n10hybrid_seed{0..19}_oos_eval.json` | **Generate:** OOS eval of hybrid-trained fronts |
| `results/saa_convergence/N{N}_rep{r}_oos_eval.json` | **Generate:** 70 OOS evals for CV-Small stability test |
| `paper/main.tex` | **Modify:** apply 4 comment blocks (R2, R1.3, R1.1, R1.2 in that order) + prose cuts |

---

## 5. Verification Checklist

- [ ] GWO-HD seeds 5–19 present in `results/exp2/` and n_runs=20 in metrics
- [ ] Fairness branch documented: same n_runs for all algorithms in shared reference front
- [ ] 40 CV-Large eval JSONs exist (20 × SAA + 20 × OOS)
- [ ] Robustness aggregation is at seed level (not pooled solutions)
- [ ] CV=0 threshold applied uniformly for feasibility rate across all eval JSONs
- [ ] `data/prep/cv_small_oos10.json` uses seed ≠ 31415 (training pool seed)
- [ ] 70 CV-Small OOS eval JSONs generated
- [ ] OOS stability result reported with mean ± std per N; no suppression of adverse trends
- [ ] 20 hybrid-trained PB-NSGA fronts generated and OOS-evaluated
- [ ] Every number in the paper traced to a specific output file on disk
- [ ] Robustness table caption contains adversarial severity context
- [ ] Tone-down contract applied to all 4 comment blocks before live LaTeX
- [ ] `latexmk` compiles clean (no undefined refs, no missing figures)
- [ ] Page count ≤ 12 after final compile
- [ ] Similarity check completed
- [ ] Submission packaged with copyright form

---

## 6. Key Framing Constraints (Non-Negotiable)

These must be respected throughout every writing step:

1. **Feasibility rate first.** The Z2 cost gap is secondary and must always be accompanied by the sentence: "adversarial scenarios use sev_mult 3.4–4.2×, compared to 0.95–3.0× in training; cost increases are structurally expected."

2. **No mean convergence claims.** The SAA study proves variance contraction under random sampling. It does not prove that the objective mean has converged.

3. **N=3 defense is evidence-conditional.** The strong form ("equivalent to N=10") is only defensible if Phase 3 Outcome A and Phase 2b competitive parity both hold. Otherwise use the weaker, honest form.

4. **NSGA-II is "appropriate," not "superior."** Cite MOEA/D constructively, not dismissively.

5. **Reactive hub is "not triggered at CV-Large scale," not "works perfectly."** Mechanism is observed on CV-Small. This is an honest statement about the problem instance, not a bug.

6. **Run counts must be explicit.** Never publish a comparison table without stating n_runs per algorithm in the caption or setup paragraph.