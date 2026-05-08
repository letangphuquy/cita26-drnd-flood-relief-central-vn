I’m folding the external-review corrections into a v3 plan now so the new file is internally consistent, executable against the current repo, and honest about what can actually fit in the paper.

Deleted memory [](file:///Users/quyle/Library/Application%20Support/Code/User/workspaceStorage/dbe5d7b51ac780e182f3404320982c8d/GitHub.copilot-chat/memory-tool/memories/NzA3ZDk3NTAtYTM2NC00ODFkLTlmOWItMWIzNzQzZDkwYzM4/plan.md)

I’m replacing the old session plan completely rather than patching it again; the earlier version had too many cross-section contradictions to safely edit incrementally.

Created memory file [](file:///Users/quyle/Library/Application%20Support/Code/User/workspaceStorage/dbe5d7b51ac780e182f3404320982c8d/GitHub.copilot-chat/memory-tool/memories/NzA3ZDk3NTAtYTM2NC00ODFkLTlmOWItMWIzNzQzZDkwYzM4/plan.md)

CAMERA_READY_PLAN.md

```markdown
# Camera-Ready Revision Plan — CITA 2026 Paper #419
# Deadline: May 10, 2026 23:59 (EasyChair)
# Last updated: 2026-05-08
# Status: v3 after external methodological review

## 0. Objective

**Paper:** Humanitarian Logistics Hub Network Design Under Uncertainty: A Multi-Objective Model and Priority-Based Genetic Algorithm for Central Coastal Vietnam

**Format:** Springer LNCS. Current working assumption: the manuscript is 14 pages and must be reduced to 12 pages.

**Goal:** Produce a camera-ready revision that is both scientifically defensible and realistically executable before the deadline. This plan resolves the main weaknesses in the prior version:
1. Scope contradiction around retraining with more scenarios.
2. Unfair or non-executable comparison fallback logic.
3. Ambiguous N=10 comparator design.
4. Missing uncertainty rules for the key N=3 vs N=10 claim.
5. Command/path mismatches with the actual repo.
6. Page-budget assumptions that were too optimistic.

## 1. Scientific Claims and Evidence Boundaries

The paper must keep these claims logically separate. No section should merge them.

| Claim | Meaning | Required Evidence | Publication Priority |
|---|---|---|---|
| A | PB-NSGA outperforms baseline algorithms | Matched-budget Exp2 comparison | Must-have |
| B | Solutions trained on 3 scenarios remain robust on broader and harder scenario sets | Multi-seed CV-Large SAA/OOS reevaluation | Must-have |
| C | The 3-profile design is competitive with larger random-scenario training | One clean N=3 vs N=10 comparator study | Should-have |

**Rule:** If Claim C evidence is weak or incomplete, the paper must still publish A and B cleanly. Claim C is not allowed to weaken A or B.

## 2. Verified Repo State

These are treated as confirmed facts.

| Item | Verified State |
|---|---|
| PB-NSGA CV-Large outputs | 20 seeds already exist: `results/exp2/cv_large_seed0.json` to `cv_large_seed19.json` |
| VNS-TS CV-Large outputs | 5 seeds already exist: `results/exp2/cv_large_vns_ts_seed0.json` to `seed4.json` |
| GWO-HD CV-Large outputs | 5 seeds already exist: `results/exp2/cv_large_gwo_hd_seed0.json` to `seed4.json` |
| Multi-seed OOS/SAA evaluation | Not done; only seed 0 has been reevaluated |
| Current SAA/OOS analyzer | `src/scripts/exp2_analyze_saa_oos.py` is single-seed and does not compute OOS Z2 gap |
| CV-Large SAA/OOS generator | `src/scripts/data_generate_saa_oos.py` hard-codes CV-Large dimensions `(100, 20, 12)` |
| CV-Small SAA study | 70 exact fronts already exist in `results/saa_convergence/` and include `pareto_front` |
| OOS evaluator | `src/solver/evaluate_oos.cpp` is the correct reevaluation tool |
| Experiment runner | `run_exp2_case_study.sh` uses binaries under `src/solver/`, not `./build/` |
| Comment blocks in paper | Four reviewer-response blocks exist in `paper/main.tex` but are not yet applied to live text |
| Bib support | `zhang2007moead` already exists in `paper/cite-class.bib` |

## 3. Scope Rules

### Included
- Multi-seed reevaluation of existing PB-NSGA CV-Large results on SAA100 and OOS10.
- One bounded retraining comparator on CV-Large using N=10 scenarios.
- Fairness repair for Exp2 baseline comparison.
- Integration of reviewer-response text into the manuscript.
- Page reduction, compile, validation, and packaging.

### Excluded
- Any broad sweep over many CV-Large scenario counts.
- Any reformulation of the optimization model.
- Any parameter tampering to force reactive hubs on CV-Large.
- Any new MOEA/D implementation or experimental comparison.
- Any paper claim that depends on unpublished or incomplete evidence.

### Important correction to prior plan
The prior plan forbade retraining with more scenarios and then proposed an N=10 retraining ablation. That contradiction is removed here. Exactly one bounded comparator retraining is allowed: **N=10 only**.

## 4. Decision Rules Before Running Anything

These rules are set before execution to prevent overclaiming.

1. **Claim A publication rule**
   Publish only matched-budget algorithm comparisons.
   If all three methods are not brought to the same run budget, do not publish a mixed-budget shared-reference claim.

2. **Claim C publication rule**
   Strong wording such as “the 3-profile design is sufficient” is allowed only if the N=3 design is practically competitive with N=10 on both:
   - feasibility rate
   - Z2 gap
   across both SAA100 and OOS10.

3. **Weaker fallback wording**
   If N=10 is clearly better, write:
   “The 3-profile design provides competitive robustness within a minimal-scenario budget, while denser scenario sets may further improve generalization.”

4. **Uncertainty rule**
   The N=3 vs N=10 comparison must report uncertainty on the **difference**, not only row-wise means.
   Minimum acceptable option: bootstrap CI for delta feasibility and delta Z2 gap.

5. **Paper priority rule**
   Must-have in paper:
   - fairness-repaired Exp2 comparison
   - multi-seed CV-Large robustness table
   - four comment-block integrations
   - page-limit compliance

   Should-have in paper:
   - one clean Claim C validation result

   Nice-to-have only if space remains:
   - second Claim C validation result

## 5. Phase 1 — Repair Exp2 Fairness

### Problem
The current comparison mixes:
- 20 PB-NSGA runs
- 5 VNS-TS runs
- 5 GWO-HD runs

That is not a clean basis for a shared-reference comparison.

### Step 1.1 — Extend GWO-HD to 20 runs
This is low-cost and should be done unconditionally.

Use the actual repo pipeline conventions:
- Binary: `src/solver/gwo_hd_baseline`
- Outputs: `results/exp2/cv_large_gwo_hd_seed{seed}.json`

### Step 1.2 — Decide the VNS-TS branch
Two valid branches exist.

**Preferred branch**
- Run VNS-TS seeds 5 to 19.
- Then PB-NSGA, VNS-TS, and GWO-HD all have 20 runs.
- Publish one matched-budget shared-reference comparison.

**Fallback branch**
- If time is too tight, analyze a matched 5-run subset for **all three** algorithms:
  - PB-NSGA seeds 0 to 4
  - VNS-TS seeds 0 to 4
  - GWO-HD seeds 0 to 4
- Publish only the matched-budget comparison based on that subset.

### Step 1.3 — Tooling correction needed
The current `src/scripts/exp2_analyze_case_study.py` does **not** support a seed filter CLI. Therefore the fallback branch is not executable unless the script is first extended with an explicit seed-selection option.

### Step 1.4 — Manuscript rule for Claim A
Every algorithm-comparison paragraph or table must explicitly state:
- algorithm names
- number of seeds used
- whether the comparison is matched-budget

No wording should imply fairness if budgets remain unequal.

## 6. Phase 2 — Strengthen Claim B with Multi-Seed CV-Large Robustness

### Problem
Only seed 0 has been reevaluated on SAA100 and OOS10. That is insufficient for a paper-level robustness claim.

### Step 2.1 — Batch reevaluate all PB-NSGA seeds
Create a batch script that loops seeds 0 to 19 and calls:

- `src/solver/evaluate_oos data/prep/cv_large_saa100.json results/exp2/cv_large_seed{seed}.json results/exp2/CV_large_seed{seed}_saa_eval.json`
- `src/solver/evaluate_oos data/prep/cv_large_oos10.json results/exp2/cv_large_seed{seed}.json results/exp2/CV_large_seed{seed}_oos_eval.json`

Expected new artifacts:
- 20 SAA eval JSONs
- 20 OOS eval JSONs

### Step 2.2 — Extend the analyzer
`src/scripts/exp2_analyze_saa_oos.py` must be upgraded to:
1. process all 20 seeds
2. compute OOS Z2 gap
3. aggregate at **seed level first**
4. report mean ± std across seeds
5. optionally export CSV and JSON summaries for manuscript use

### Step 2.3 — Required statistics
For each seed and evaluation set:
- number of evaluated Pareto solutions
- mean Z1 gap
- mean Z2 gap
- feasible count
- feasibility rate

Then aggregate across seeds.

### Step 2.4 — Paper-facing table
Produce one compact robustness table with rows:
- In-sample training (3 scenarios)
- SAA reevaluation (100 scenarios)
- OOS reevaluation (10 adversarial scenarios)

Columns:
- scenario count
- mean Z1 gap
- mean Z2 gap
- feasibility rate
- n_seeds

### Step 2.5 — Framing rule for Claim B
The **primary** robustness claim is feasibility maintenance, not small cost drift.

Every caption or paragraph using the OOS row must remind the reader:
- OOS scenarios are deliberately more severe than training scenarios
- large cost increases are structurally expected under adversarial stress
- feasibility preservation is the key robustness criterion

## 7. Phase 3 — Clean N=10 Comparator for Claim C

This phase replaces the earlier “hybrid 5 structured + 5 fully random” primary design. That hybrid is not a clean scientific control and is too hard to interpret.

### Step 3.1 — Use one primary comparator only
The paper’s main Claim C comparator should be:

**N=10 tier-balanced random training**

Meaning:
- 10 training scenarios
- random within the established scenario framework
- balanced across mild, severe, and extreme tiers
- interpretable as a larger stochastic-training design without mixing in a second mechanism

### Step 3.2 — Preserve the baseline instance
The comparator must preserve all non-scenario fields from the original CV-Large training instance wherever possible:
- same node sets
- same transport matrices
- same hub capacities
- same fixed costs
- same holding costs
- same non-scenario metadata

Only these should change:
- `scenarios`
- `num_S`
- `theta`
- `lambda`

### Step 3.3 — Generator design rule
Do **not** simply call `build_instance_variant()` and assume the result is a clean ablation. The current generator reconstructs a full CV-Large instance from code. The new comparator-generation script must intentionally preserve baseline instance structure and replace only scenario-dependent fields.

### Step 3.4 — Train the N=10 comparator
Run PB-NSGA for 20 seeds on the N=10 tier-balanced random training instance using the actual solver path under `src/solver/`.

Outputs:
- `results/exp2/cv_large_n10_seed{seed}.json`

### Step 3.5 — Evaluate on both SAA100 and OOS10
This is mandatory. OOS-only is too narrow.

For each N=10-trained front, evaluate on:
- `data/prep/cv_large_saa100.json`
- `data/prep/cv_large_oos10.json`

Outputs:
- `results/exp2/CV_large_n10_seed{seed}_saa_eval.json`
- `results/exp2/CV_large_n10_seed{seed}_oos_eval.json`

### Step 3.6 — Aggregate exactly as in Phase 2
Use seed-level aggregation first, then mean ± std across seeds.

### Step 3.7 — Runtime reporting
The same generation count is not compute-fair when `num_S` changes from 3 to 10. Therefore the paper must report runtime for:
- N=3 training
- N=10 training

If no matched wall-clock design is used, the discussion must explicitly note the runtime premium of N=10.

### Step 3.8 — Required comparison outputs
Create one training-design comparison artifact, ideally a compact table with two rows:
- 3-profile calibrated training
- N=10 tier-balanced random training

And grouped columns for:
- SAA100 feasibility rate
- SAA100 Z2 gap
- OOS10 feasibility rate
- OOS10 Z2 gap
- runtime

### Step 3.9 — Statistical comparison
Report:
- delta feasibility with CI
- delta Z2 gap with CI

Do not rely only on overlapping row-wise standard deviations.

### Step 3.10 — Interpretation rule
If N=10 clearly dominates on both SAA100 and OOS10, downgrade Claim C.
If N=3 is similar or better at much lower training burden, use the stronger wording that deliberate severity-range coverage matters more than scenario count alone.

## 8. Phase 4 — Optional Secondary Claim C Support from Existing CV-Small Exact Fronts

This phase is valuable but is secondary to the N=10 comparator for the paper.

### Step 4.1 — Generate CV-Small OOS holdout cleanly
Do not use the current CV-Large-only helper directly.
Instead, reuse the CV-Small base-building logic from `src/scripts/exp_saa_convergence.py` so that the OOS test stays consistent with the exact-study infrastructure.

### Step 4.2 — Reevaluate the 70 existing exact fronts
Use `src/solver/evaluate_oos` on:
- `results/saa_convergence/N{3,5,8,10,15,20,30}_rep{0..9}_bb.json`

### Step 4.3 — Aggregate by N
For each N, compute mean OOS Z2 gap ± std across the 10 reps.

### Step 4.4 — Interpretation rule
This phase is supporting evidence about scenario-count robustness.
It should not replace the CV-Large N=3 vs N=10 comparator if that comparator is available.

### Step 4.5 — Section-title rule
Rename the current SAA section to something like:

**Scenario-Count Robustness Analysis**

And explicitly separate:
- in-sample variance contraction
- out-of-sample behavior

## 9. Phase 5 — Writing Integration

Apply the four drafted comment blocks in this order:
1. R2 problem/gap rewrite
2. R1.3 NSGA-II justification
3. R1.1 reactive-hub defense
4. R1.2 robustness / scenario-design response

### Writing constraints
1. No claim that the SAA study proves mean convergence.
2. No unconditional statement that N=3 is equivalent to N=10.
3. NSGA-II should be described as appropriate for this problem class, not superior to MOEA/D in general.
4. The reactive hub mechanism should be described as active but not triggered in CV-Large under the calibrated 20-hub setting.
5. Run counts must be explicit in any experiment section or caption.

### Priority rule for R1.2
Lead with the strongest evidence in this order:
1. multi-seed CV-Large robustness
2. matched-budget fairness repair
3. one Claim C validation result

Do not let the paper spend more words defending Claim C than it spends presenting Claim B.

## 10. Phase 6 — Page-Budget Discipline

The prior plan assumed too much would fit. This version imposes a strict priority ladder.

### Guaranteed paper content
- one fairness-repaired comparison result
- one multi-seed CV-Large robustness table
- one compact Claim C result
- integrated reviewer-response text
- 12-page compliance

### Cuts to apply first
1. Compress Related Works.
2. Remove redundant post-constraint prose.
3. Compress genetic-operator explanation.
4. Compress decision-support prose.
5. Trim the abstract.
6. Merge limitations into future work.
7. Shrink pseudocode if needed.

### If still over 12 pages
1. Keep the multi-seed CV-Large robustness table.
2. Keep only one Claim C artifact in the main paper.
3. Drop or compress the second Claim C artifact.
4. Prefer the direct N=3 vs N=10 comparator over the secondary CV-Small OOS-across-N result.

## 11. Phase 7 — Validation and Submission

### Verification checklist
- fairness branch chosen and executable
- seed-filter tooling added before using the matched 5-run fallback
- 40 PB-NSGA reevaluation JSONs exist for Claim B
- N=10 comparator preserves non-scenario fields from the baseline instance
- N=10 comparator evaluated on both SAA100 and OOS10
- uncertainty intervals computed for N=3 vs N=10 differences
- every numeric sentence in the paper traced to an output file
- final compile is 12 pages or less

### Final packaging
1. Compile with `latexmk`.
2. Resolve references, figures, and bibliography.
3. Run similarity check after wording stabilizes.
4. Package PDF, source, figures, bibliography, and copyright form.
5. Submit before the deadline.

## 12. Relevant Files

| File | Role |
|---|---|
| `run_exp2_case_study.sh` | Actual experiment-2 runner and true binary/output conventions |
| `src/scripts/exp2_analyze_case_study.py` | Needs seed-filter support if matched-budget fallback is used |
| `src/scripts/exp2_analyze_saa_oos.py` | Must be extended to multi-seed analysis and OOS Z2 reporting |
| `src/scripts/data_generate_saa_oos.py` | Useful utilities, but instance builder is currently CV-Large-only |
| `src/scripts/exp_saa_convergence.py` | Reusable CV-Small base logic and existing exact-study outputs |
| `src/solver/evaluate_oos.cpp` | Reevaluation tool for Claim B and optional Phase 4 support |
| `paper/main.tex` | Live manuscript receiving the four comment blocks and page cuts |
| `results/exp2/` | Existing CV-Large solver outputs and future robustness artifacts |
| `results/saa_convergence/` | Existing exact fronts for optional CV-Small support analysis |

## 13. Final Decisions

- Claim B is non-negotiable and must be in the paper.
- Only one Claim C result should be assumed to fit in the paper unless page count proves otherwise.
- Preferred Claim C result for the paper: N=3 vs N=10 tier-balanced random retraining on CV-Large, evaluated on both SAA100 and OOS10.
- Preferred fairness branch: 20 runs for all three algorithms if time permits; otherwise matched 5-run subset for all three.
- Strong wording about the 3-profile design is allowed only if the pre-registered decision rules are satisfied.
```