# Writing Review — manuscript `paper/main.tex`
## Reviewer: Claude (Writing Assistant)
## Date: 2026-03-11

---

## Section-by-Section Assessment

### Title
**Good.** Concise, contains all key terms (humanitarian logistics, hub network, uncertainty, multi-objective, PB-NSGA, Central Vietnam). Appropriate for a conference proceedings paper.

---

### Abstract
**Mostly good, one critical inconsistency.**

The abstract claims:
> "PB-NSGA defines the combined reference Pareto front (normalized HV = 1.000, IGD+ = 0.000) in 0.5 s -- surpassing the exact Branch-and-Bound (HV = 0.443) and the MILP solver (HV = 0.000, 208.9 s)"

But Table 1 in the body shows PB-NSGA with HV = **0.589 ± 0.219**. The distinction is between *per-run* HV and *combined front* HV, but this is never clarified in the abstract. A reviewer will flag this immediately.

**Fix needed:** Clarify in the abstract that HV=1.000 refers to the combined front across 20 runs, while the per-run mean is 0.589 ± 0.219.

The sentence about the case study hub names (Quang Ngai Port, Phuoc Son Helipad, Tam Ky) is specific and strong — keep it.

---

### Introduction

#### §1.1 Problem Motivation
**Good.** Real statistics (2025 floods, 98.7 trillion VND), specific operational failures (170 trains cancelled, Route 1 severed). Opens with a compelling hook.

**Minor:** The phrase "supply chain weaknesses" in line 1 is generic. A more specific phrase like "pre-positioned relief inventory shortfalls" would be more precise.

#### §1.2 Related Works (4 thematic subsections)
**Adequate but thin.** The four-paragraph structure (HL/facility location, hub/incomplete networks, stochastic/robust, MOEAs) is correct. Citations are appropriate.

**Issues:**
- No comparison table. For a paper citing ~10 references in the lit review, a table with columns (objective, uncertainty, method, case study, gap) is expected at this venue level.
- Each subsection is only 2–3 sentences. The gap analysis in particular is weak: "no study has simultaneously considered incomplete hub network design, two-stage stochastic programming, multi-objective humanitarian objectives, and a flood-disaster case study" is a valid gap but stated too briefly. The gap is earned — it should be expanded into 3–4 sentences showing exactly how each of the four cited streams is insufficient on its own.
- Constraint: SPACE. If space is tight, the comparison table can be compacted. Even a half-page table counts more than prose.

#### §1.3 Contributions
**MISSING as a standalone list.** Contributions are buried in the last paragraph of Related Works:
> "This paper closes the gap by formulating the MO-IHLNDP and solving it via our proposed PB-NSGA..."

This is one sentence for potentially 4 distinct contributions. The writing guidelines and every reference paper use a numbered/bulleted list.

**Recommended contributions list (draft):**
1. MO-IHLNDP: a two-stage stochastic bi-objective hub network model with incomplete networks, multimodal transport, deprivation cost, and pre-positioned inventory — the first to jointly address all four features for flood contexts.
2. PB-NSGA: a priority-based NSGA-II with a custom decoder that reduces search-space from O(|S|×|V|) to O(|H|), with stagnation-aware diversity mechanisms.
3. Computational validation on CV-Small against exact solvers (MILP, BB) confirming near-optimal quality at 0.5 s.
4. Managerial insights from CV-Large: quantified cost-deprivation trade-off and robust hub investment hierarchy for four flood-prone provinces.

**Constraint: SPACE.** If space is too tight, condense to 3 contributions.

#### §1.4 Paper Organization
**MISSING.** "The remainder of this paper is organized as follows..." paragraph is absent. Required by convention and by venue formatting.

**Constraint: SPACE.** This is 1–2 sentences. Always include.

---

### Section 2: Problem Description and Mathematical Model

**Generally strong.** The model is correct, well-structured, constraints are numbered, and the linearization of Z₂ via auxiliary variable W_s is handled cleanly.

**Issues:**
- No **network diagram**. The guidelines and every reference paper with a hub-and-spoke model include a diagram showing origins → hubs → demands with multi-modal links. This is absent. Even a simple TikZ figure would suffice.
- Constraint explanations (the paragraph after Eq. 17) are present but thin. Each sentence covers multiple constraints in one breath. Consider 1 sentence per constraint group.
- Z₂ formula: The linearized form introduces W_s but Eq. (deprivation_cost) still uses k as if single-allocation holds. This is correct (it does hold) but the subscript makes it look like k is fixed — add a clarifying note.
- The parameter table uses two separate tabular environments for first-phase and second-phase parameters. This is fine for readability but inconsistent with the notation table guidelines (Symbol | Definition | Unit/Domain columns). Units are missing entirely.

---

### Section 3: Proposed Algorithm PB-NSGA

**The strongest section.**

**Good:** Chromosome encoding is clearly described. The four-segment chromosome (X, R, A, W) is novel and the decoder's four-step structure is well-explained. The constrained dominance principle citation (Deb 2002) is appropriate.

**Issues:**
- **No top-level flowchart.** Algorithm 1 shows the decoder only. The outer NSGA-II loop (initialization → evaluation → selection → crossover/mutation → stagnation check → next generation) is described in §3.3 prose but has no figure. At minimum, a compact flowchart of the full PB-NSGA loop is needed.
- The stagnation mechanism paragraph in §3.3 is dense. The trigger conditions (20 generations unchanged, 3-way tournament, W hypermutation) are buried in one long sentence. A short numbered list or sub-paragraph would improve clarity.
- The Hamming-distance tiebreak and X-niche quota are mentioned in passing ("tiebreaking proceeds by (1)... (2)... (3)...") but not explained. Reviewers familiar with NSGA-II will want to know what "X-niche quota" means.

---

### Section 4: Computational Experiments

#### §4.1 Experimental Setup
**Good** on hardware specs and parameter reporting.

**Issue:** `p_c = 0.9` stated here, but `main.cpp` defaults show `pc = 0.98`. These must match.

Also: `η_c = η_m = 20` — but `main.cpp` shows `sbx_eta_rw = 1.5` and `pm_eta_rw = 8.0`. If these are different parameters (one for X/A, one for R/W) that distinction must be stated.

#### §4.2 Dataset Description
**Good.** Real province names, node counts, transport modes, helicopter cap (15% of links) are specific and credible.

#### §4.3 Experiment 1: Baseline Comparison

**Critical issue — Table 1 inconsistency:**

| Source | PB-NSGA HV |
|---|---|
| Abstract | 1.000 (combined), implied also per-run |
| Table 1 | 0.589 ± 0.219 |
| Narrative below Table 1 | 1.000 |

The narrative says "PB-NSGA converges to the optimal region... reaching a hypervolume of 1.000" — this is true for the *combined* front but contradicts the per-run mean shown in the same table. This MUST be clarified.

**Secondary issue:** Table 1 caption says the reference front is "BB ∪ Greedy ∪ PB-NSGA" but the text mentions VNS-TS and GWO-HD exist as baselines (they're in the metrics CSV). These are not in Table 1 nor the reference front. If they were run, include them; if excluded, state why.

**Positive note:** The finding that MILP ε-constraint returns HV=0.000 is interesting and worth expanding. The explanation ("Big-M numerical difficulties on non-linear deprivation objectives") is plausible but should cite something or show the solver output (time limit, gap).

Also: "MILP failed to return any feasible Pareto solution within 1800 s" contradicts "CPU Time = 208.9 s" in Table 1. This needs reconciliation — was 208.9 s the time before timeout? Or was the time limit 208.9 s?

#### §4.4 Experiment 2: Case Study

**Critical issues — Table 2:**

1. HV > 1.0: CV-Small shows **1.190 ± 0.015**, CV-Large shows **1.049 ± 0.045**. Normalized HV cannot exceed 1.000. This means the normalization reference in Exp 2 differs from Exp 1. Explain or fix.

2. Narrative contradicts table:
   - Narrative: "mean IGD+ of **0.117 ± 0.051** and a combined Pareto front of **17**"
   - Table 2: IGD+ = **0.076 ± 0.059**, combined = **24**
   These are completely different numbers. One set must be stale/copy-pasted from an earlier run.

3. **No baseline comparison.** Exp 2 only reports PB-NSGA. There is no comparison against VNS-TS or Greedy on CV-Large. Even one comparison strengthens the section significantly.

**SAA/OOS Sub-section:**
The methodology is described in three steps but presents **zero results** — no actual gap values, no table. Options:
- (A) Run the SAA/OOS protocol and report the gap (requires data generation + recourse evaluation per OOS scenario)
- (B) Remove the section and describe it as a future work item in the Conclusion
- (C) Reframe as a methodological description of how the existing 3-scenario model functions as a limited SAA instance (weakest option but keeps the text)

**Positive:** The hub frequency analysis (100%/70.6%/38.3%) and the transport modal shift discussion are the best managerial insights in the paper. The Figure 1 description is vivid and specific.

---

### Section 5: Conclusion

**Adequate.** Covers the main findings and provides 4 future directions.

**Issues:**
- The summary repeats what was *done* rather than what was *learned*. ("This paper presented a model and solver...") — the guidelines say to state the key *answer* to the research question.
- Managerial implications paragraph lacks concrete quantitative claims. Compare: "identifies a robust hub core" (current) vs. "the Quang Ngai Port Hub, appearing in 100% of Pareto solutions, reduces expected maximum deprivation cost by X% vs. the next-best alternative" (target).
- Limitations section is honest but brief. The statement about synthetic data calibration is good; consider adding: (a) single-commodity assumption, (b) static (non-dynamic) demand, (c) single-period planning horizon.
- Future work: the four directions are specific and actionable — this is done well.

---

## Summary of Issues by Priority

### 🔴 Critical (likely to cause rejection or major revision)
1. Table 1 narrative says HV=1.000 but table shows 0.589 ± 0.219 — clarify combined vs. per-run HV
2. Table 2 narrative numbers (IGD+ 0.117, combined=17) do not match table (0.076, 24) — fix stale copy-paste
3. HV > 1.0 in Table 2 — normalization reference is inconsistent between experiments
4. MILP time: "1800 s timeout" vs. "208.9 s" in table — reconcile

### 🟠 High (reviewer will flag, weakens contribution)
5. No numbered contributions list in Introduction
6. Missing "paper organized as follows" paragraph
7. SAA/OOS section presents methodology but zero results — add results or remove
8. Exp 2 has no baseline comparison (only PB-NSGA vs. itself)
9. p_c parameter inconsistency: 0.9 (text) vs. 0.98 (code)

### 🟡 Medium (improves clarity and completeness)
10. No network diagram showing origins → hubs → demands structure
11. No top-level PB-NSGA flowchart (only decoder pseudocode)
12. No comparison table in literature review
13. No sensitivity analysis on key parameters (χ, α, scenario count, budget)
14. Units missing from parameter tables
15. BB baseline not clearly explained (how does it handle multi-objective without W weights?)

### 🟢 Low (polish)
16. Acronym CA not defined on first use in abstract
17. "supply chain weaknesses" opening line — too generic
18. Managerial insights lack quantitative backing numbers
19. Limitations section could be expanded (single-commodity, static demand, single-period)

---

## Open Discussion: SAA/OOS Section

### What we have
- 3 training scenarios (Mild, Severe, Extreme) → used for in-sample optimization
- PB-NSGA's 20-run results represent the combined in-sample Pareto front
- The combinatorial SAA dataset with N=100 scenarios (mentioned in text) — does this exist as actual data, or is it only described?

### Option A: Run the protocol (strongest)
1. For each Pareto solution (first-stage X, q), fix these decisions
2. Evaluate on N'=100 or N'=1000 new out-of-sample scenarios (easy with the decoder — it's O(|I|) per scenario)
3. Compute Z1_OOS, Z2_OOS for each Pareto solution
4. Report: SAA-OOS gap = (Z_OOS - Z_SAA) / Z_SAA × 100%
5. Plot the in-sample Pareto front vs. the OOS-evaluated Pareto front on the same axes
- **Result**: Show that the PB-NSGA solutions generalize (small gap = robust design)

### Option B: Remove the section (safest if data unavailable)
Move SAA/OOS to Future Work in the Conclusion as:
> "A formal Sample Average Approximation analysis with out-of-sample validation on a larger scenario set remains a direction for future work."

### Option C: Reframe as SAA justification
Describe the existing 3-scenario model as a minimal SAA instance, cite the SAA convergence theory (Shapiro & Homem-de-Mello), and explain that the 20-run stochastic evaluation with different seeds partially compensates. This is the weakest option but requires no new computation.

**Recommendation:** Option A is within reach using the existing decoder. Generate 100 random OOS scenarios, fix first-stage decisions from each Pareto solution, run the decoder per scenario, report the gap. This is fast (decoder runs in milliseconds) and elevates the paper's methodological quality significantly.
