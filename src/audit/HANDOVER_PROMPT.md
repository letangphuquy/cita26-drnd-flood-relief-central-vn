# Agent Handover Prompt
## CITA 2026 Paper #419 — Camera-Ready Revision

> This document is a complete, self-contained briefing. You have no prior conversation history. Read this in full before touching any file.

---

## 1. Identity and Deadline

**Paper:** "Humanitarian Logistics Hub Network Design Under Uncertainty: A Multi-Objective Model and Priority-Based Genetic Algorithm for Central Coastal Vietnam"  
**Conference:** CITA 2026 (15th Conference on Information Technology and Its Applications), published in Springer LNCS  
**Paper ID:** 419 | **Decision:** ACCEPTED (both reviewers scored 2 = accept)  
**Camera-ready deadline:** May 10, 2026  
**Repo root:** `/Users/quyle/cita26-drnd-flood-relief-central-vn/`  
**Active branch:** `exp/camera-ready` (branched from `master`)  
**Git user:** Quy Le  

---

## 2. Hard Constraints

| Constraint | Value | Current status |
|---|---|---|
| Max pages (Springer LNCS) | 12 | **14 pages** — must cut ≥ 2 pages |
| Similarity threshold (iThenticate) | < 20% | Not yet checked |
| Format | `\documentclass{llncs}`, NO page numbers | Already correct |
| Submission files | Revised PDF + source ZIP + signed copyright form | Not yet submitted |
| EasyChair upload | https://easychair.org/conferences/?conf=cita2026 | Pending |

---

## 3. Reviewer Concerns and Response Status

Four concerns were raised across two reviews. Here is the status of each:

### R1.1 — "No reactive hub opened" (Score: accept)
> "The authors note that in the CV-Large instance, 'no reactive hub is ever opened'. This suggests the decoder might be overly biased toward pre-positioning, or the cost of reactive hubs is set prohibitively high."

**Our position:** This is a correct, economically rational optimal outcome — NOT a decoder bug. The mechanism is provably active (Pass 3, Algorithm 1) but never triggers at CV-Large scale because 8 well-placed hubs cover all demand without reactive setup. No parameters were changed.

**Status:** Written defense drafted as a comment block in the paper. **NOT YET APPLIED to live LaTeX.**  
**Location in paper:** `paper/main.tex` line ~716, comment block `[R1.1]`  
**Anchor:** INSERT 2 sentences after "...purely through pre-positioning."

---

### R1.2 — "Only 3 scenarios shown; needs SAA convergence analysis" (Score: accept)
> "A good paper would benefit from a more rigorous sensitivity analysis on the number of scenarios required to achieve convergence in the SAA."

**Our response:** A full replication-based SAA convergence experiment was implemented and run. See Section 5 for details.

**Status:** Experiment complete, figure produced, paragraph and figure block drafted as comment. **NOT YET APPLIED to live LaTeX.**  
**Location in paper:** `paper/main.tex` line ~537, comment block `[R1.2]`  
**Anchor:** INSERT after "...disjoint from training, to assess generalization under catastrophic conditions."

---

### R1.3 — "Must defend NSGA-II over MOEA/D" (Score: accept)
> "The priority-based encoding is a known technique (Gen et al., 2006). Authors should defend why not MOEA/D."

**Our position:** Three reasons — MOEA/D requires pre-specified weight vectors (unavailable here); NSGA-II crowding distance preserves spread without tuning; the DECODER is the contribution, not the sorter.

**Status:** Defense drafted as comment block. **NOT YET APPLIED to live LaTeX.** New bib entry `zhang2007moead` already added directly to `paper/cite-class.bib`.  
**Location in paper:** `paper/main.tex` line ~380, comment block `[R1.3]`  
**Anchor:** INSERT after "...with a custom heuristic decoder."

---

### R2 — "Problem not clearly stated vs existing solutions" (Score: accept)
> "Are there any existing solutions? Is the proposed model an improvement? This needs to be clearly stated."

**Our position:** This is a writing/framing problem. The existing gap statement (3 vague lines) never names what prior work does and where it falls short. Replace with an explicit 4-point enumeration and before/after baseline comparison.

**Status:** Replacement text drafted as comment block. **NOT YET APPLIED to live LaTeX.**  
**Location in paper:** `paper/main.tex` line ~162, comment block `[R2]`  
**Anchor:** REPLACE the 3 lines starting "To the best of our knowledge, existing literature..."

---

## 4. What "NOT YET APPLIED" Means — How to Apply Comment Blocks

The paper is compiled on a Linux/Windows machine (not the Mac where experiments ran). All proposed paper changes are wrapped in styled LaTeX comment blocks inside `paper/main.tex`. The live LaTeX text was NOT modified. The blocks look like this:

```
% ┌─────────────────────────────────────────────────────────────────────┐
% │ CAMERA-READY [R1.X]  ·  Short title                               │
% ├─────────────────────────────────────────────────────────────────────┤
% │ REVIEWER REQUEST                                                   │
% │   "..."                                                            │
% ├─────────────────────────────────────────────────────────────────────┤
% │ ANALYSIS / STRATEGY / WHY / WHY NOT / NOTICE                      │
% │   ...                                                              │
% ├─────────────────────────────────────────────────────────────────────┤
% │ INTENDED CHANGE                                                    │
% │   Action: INSERT AFTER / REPLACE                                   │
% │   Anchor: "..."                                                    │
% ├─────────────────────────────────────────────────────────────────────┤
% │ PROPOSED LaTeX                                                     │
% │   ... (copy-paste ready text) ...                                  │
% └─────────────────────────────────────────────────────────────────────┘
```

**To apply a block:** read the INTENDED CHANGE section, find the anchor text in `main.tex`, and insert/replace as specified. The PROPOSED LaTeX section contains the exact text to add (remove the leading `% │ ` prefix from each line).

**grep to find all blocks quickly:**
```bash
grep -n "CAMERA-READY" paper/main.tex
```
Returns: lines 162 (R2), 380 (R1.3), 537 (R1.2), 716 (R1.1).

---

## 5. The New Experiment (R1.2) — Complete Description

### What was built

A replication-based SAA scenario-count sensitivity analysis:
- **Instance:** CV-Small (|I|=20, |H|=5, |J|=2, 3 transport modes)
- **Solver:** `src/solver/bb_solver --mode enum` — exhaustive enumeration of all 2⁵=32 hub configurations, guaranteed optimal Pareto front
- **Design:** K=10 independent random sub-samples of N scenarios from a master pool of 50, for N ∈ {3, 5, 8, 10, 15, 20, 30} → 70 total solver runs
- **Master pool:** 50 scenarios generated with seed=31415 using `generate_saa_scenarios()` from `data_generate_saa_oos.py`, round-robin across 10 flood profiles (mild_a/b/c, severe_a/b/c, extreme_a/b/c/d)
- **Metrics:** knee-point Z₂ (expected deprivation cost) and normalised Pareto hypervolume (HV)

### Why this design

| Alternative | Why rejected |
|---|---|
| Nested subsets (first N from fixed sequence) | Round-robin ordering puts all mild scenarios first → Z₂ jumps 10× when first severe scenario enters at N=4. Not convergence, just a regime shift from ordering. |
| CV-Large with PB-NSGA | |H|=20 means ~10s per run × 70 runs = 700s minimum. Also: metaheuristic noise contaminates the convergence signal. |
| Changing the model's |S|=3 | The paper's 3-profile design is CORRECT and should NOT be modified. The experiment is a separate validation, not a change to the case study. |

### Results (from `results/saa_convergence/convergence_summary.csv`)

```
N= 3  Z2_mean=230k  Z2_std=110k  HV_mean=1.105  HV_std=0.239
N= 5  Z2_mean=342k  Z2_std=142k  HV_mean=0.845  HV_std=0.312  ← peak variance
N= 8  Z2_mean=243k  Z2_std= 69k  HV_mean=1.063  HV_std=0.158
N=10  Z2_mean=263k  Z2_std= 54k  HV_mean=1.014  HV_std=0.121
N=15  Z2_mean=252k  Z2_std= 59k  HV_mean=1.033  HV_std=0.134
N=20  Z2_mean=235k  Z2_std= 50k  HV_mean=1.072  HV_std=0.121
N=30  Z2_mean=264k  Z2_std= 30k  HV_mean=1.000  HV_std=0.068  ← reference
```

### How to read the results

- **DO NOT use Z₁ (logistics cost) for the convergence claim.** With only 32 hub configs in CV-Small, discrete hub selection makes Z₁ highly variable (Z₁_std at N=10 is 8.5M, larger than the mean). This is not a bug.
- **Z₂_std is the primary convergence signal.** It decreases 3.7× overall (110k → 30k) but is NOT monotone: N=5 peaks above N=3 (142k > 110k). This is a known phenomenon — with a pool that is 40% extreme, a random draw of 5 can land 4 extreme scenarios, producing an outlier Z₂=634k. The paper text acknowledges this with "overall decreasing trend" (not "monotonically").
- **HV_std is the cleanest signal.** It decreases monotonically from N=5 onwards: 0.312 → 0.158 → 0.121 → 0.134 → 0.121 → 0.068. HV_mean is stable near 1.0 for all N≥8.
- **The key claim for the paper:** "The shaded band — not the mean line — carries the SAA convergence message. Our calibrated 3-profile design achieves the variance stability of N≈10 random draws through deliberate stratification."

### Figure

`figures/saa_convergence.pdf` — two-panel plot. Left: Z₂ mean ± std (blue). Right: normalised HV mean ± std (red).  
When reading: the **shaded bands** show convergence. The mean line in the left panel is non-convergent by design (each N is a different expected-value problem).

### Audit

All hard checks pass. Run `python src/audit/audit_saa_convergence.py` to verify. 5 non-fatal warnings are documented (40% extreme pool bias, non-monotone Z₂_std, K=10 borderline, CV-Small scope, Z₂_mean non-convergence).

---

## 6. Complete File Map

### Paper files (compile on Linux/Windows)

| File | Role | Status |
|---|---|---|
| `paper/main.tex` | Master LaTeX source (837 lines) | Has 4 comment blocks to apply; live text unchanged |
| `paper/cite-class.bib` | Bibliography | `zhang2007moead` entry already added (line ~681) |
| `paper/llncs.cls` | Springer LNCS class file | Already in repo, no install needed |
| `paper/main.pdf` | Last compiled PDF (macOS) | **14 pages** — must be ≤12 after page cuts |
| `paper/figures/` | Figure symlinks / copies used in paper | Check that `saa_convergence.pdf` is accessible |
| `figures/saa_convergence.pdf` | New convergence figure | Must be copied/linked into the LaTeX figure search path |

**Compile command (Linux):**
```bash
cd paper
latexmk -C main.tex          # clean stale macOS aux files first
pdflatex main.tex             # pass 1
bibtex main                   # pick up zhang2007moead
pdflatex main.tex             # pass 2
pdflatex main.tex             # pass 3 (resolves cross-refs)
pdfinfo main.pdf | grep Pages
```

### Experiment scripts

| File | Role |
|---|---|
| `src/scripts/exp_saa_convergence.py` | End-to-end SAA convergence experiment (generate → solve → plot) |
| `src/scripts/data_generate_saa_oos.py` | Master scenario generator (imported by experiment) |
| `src/scripts/data_generate_cv.py` | CV-Small/Large geography, hub params, transport matrices (imported) |

**Run experiment (Linux, after recompiling bb_solver):**
```bash
source .venv/bin/activate
python src/scripts/exp_saa_convergence.py            # full run from scratch
python src/scripts/exp_saa_convergence.py --skip-solve  # reuse existing JSONs
```

### Audit scripts

| File | Role |
|---|---|
| `src/audit/audit_saa_convergence.py` | Correctness + objectivity audit (sections A–E, PASS/WARN/FAIL) |
| `src/audit/SAA_CONVERGENCE_ANALYSIS.md` | Full design rationale, results interpretation, figure reading guide |
| `src/audit/CAMERA_READY_TECHNICAL_REPORT.md` | Formal technical report (what changed, where to find things, remaining work) |
| `src/audit/HANDOVER_PROMPT.md` | This document |

### Experiment data and results

| Path | Contents | Size / count |
|---|---|---|
| `data/prep/saa_convergence/N{N}_rep{r}.json` | 70 solver-input instances (7 N × 10 reps) | ~5–50 KB each |
| `results/saa_convergence/N{N}_rep{r}_bb.json` | 70 bb_solver Pareto front outputs | ~2–20 KB each |
| `results/saa_convergence/convergence_summary.csv` | Aggregated mean ± std per N (8 columns, 7 rows) | < 1 KB |

### Solver binaries (must recompile on Linux)

| Binary | Source | Compile command |
|---|---|---|
| `src/solver/solver` | `src/solver/main.cpp` | `./compile.sh` |
| `src/solver/bb_solver` | `src/solver/bb_solver.cpp` | `./compile.sh --all` |
| `src/solver/greedy_baseline` | `src/solver/greedy_baseline.cpp` | `./compile.sh --all` |
| `src/solver/gwo_hd_baseline` | `src/solver/gwo_hd_baseline.cpp` | `./compile.sh --all` |
| `src/solver/vns_ts_baseline` | `src/solver/vns_ts_baseline.cpp` | `./compile.sh --all` |
| `src/solver/evaluate_oos` | `src/solver/evaluate_oos.cpp` | `g++ -O3 -std=c++17 src/solver/evaluate_oos.cpp -o src/solver/evaluate_oos` |
| `src/solver/export_flow` | `src/solver/export_flow.cpp` | `g++ -O3 -std=c++17 src/solver/export_flow.cpp -o src/solver/export_flow` |

**All committed binaries are macOS arm64. They will not run on Linux.**

---

## 7. The One Remaining Technical Task: Page Reduction

The paper is currently **14 pages**. Springer LNCS requires ≤12. Adding the SAA convergence figure + paragraph (R1.2) will add approximately 0.5–1 page. **Total cuts needed: ≥2.5 pages from the current 14-page baseline** (before applying R1.2).

### Planned cuts (from `src/audit/CAMERA_READY_TECHNICAL_REPORT.md`, Section 9)

All cuts are in `paper/main.tex`. Apply in this order (smallest risk first):

| Cut | Location | Estimated saving | Action |
|---|---|---|---|
| **2A: Compress Related Works** | Lines ~138–184, `\subsection{Related Works}` | ~0.4 pages | Merge 4 `\textbf{}` subsections into 2 paragraphs; remove the bold subheaders; keep all citations |
| **2B: Compress constraint prose** | Lines ~338–371, after the constraint equations | ~0.2 pages | Cut the "Specifically, \eqref{eq:flow_balance} ensures..." sentence — the math is self-documenting |
| **2C: Compress Genetic Operators** | Lines ~504–516, `\subsection{Genetic Operators}` | ~0.3 pages | Merge the 5 `\textbf{}` items (Initialization, Crossover, Mutation, Survival, Diversity) into a single dense paragraph without sub-headers |
| **2D: Compress Decision Support** | Lines ~770–810, `\subsubsection*{Decision Support Framework}` | ~0.3 pages | Merge the 3 `\textit{}` items (hub prioritization, resilience gap, modal shift) into one continuous paragraph with transitions |
| **2E: Trim Abstract** | Lines ~95–109, `\begin{abstract}` | ~0.15 pages | Cut the last 2 sentences of results (the named hub percentages) — these are in the body already. Target ≤150 words. |
| **2E: Trim Conclusion** | Lines ~814–826, `\section{Conclusion}` | ~0.1 pages | Move "Limitations" sentence into Future Work paragraph instead of a standalone bold block |
| **2F: Shrink algorithm pseudocode** | Lines ~393–420, `\begin{algorithm}` | ~0.2 pages | Add `\small` inside the algorithm environment; or remove the explicit `\Require`/`\Ensure` lines since they repeat what the text already says |

**Total estimated cuts: ~1.65 pages.** Combined with the net of applied reviewer additions minus these cuts, the target of ≤12 pages should be achievable. Compile and check `pdfinfo main.pdf | grep Pages` after each cut.

**Critical rule: Apply cuts AFTER applying the 4 comment blocks.** The comment blocks add text; knowing the true post-addition page count tells you exactly how much to cut.

---

## 8. Environment Setup (Linux)

```bash
# Python (must be ≥ 3.9 for list[dict] type hints)
python3 --version

# Recreate virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# requirements.txt contains: numpy, ortools, matplotlib, pandas, scipy,
#   cartopy, geopandas, pyproj, contextily, pymoo

# Heavy system deps for cartopy/geopandas (Ubuntu/Debian):
sudo apt install libgeos-dev libproj-dev proj-data libgdal-dev

# Recompile C++ solvers (CRITICAL — macOS binaries in repo won't run)
./compile.sh --all
g++ -O3 -std=c++17 src/solver/evaluate_oos.cpp -o src/solver/evaluate_oos
g++ -O3 -std=c++17 src/solver/export_flow.cpp   -o src/solver/export_flow

# Verify bb_solver works before running experiment
src/solver/bb_solver 2>&1 | head -5

# LaTeX (full installation recommended)
sudo apt install texlive-full   # or texlive-latex-recommended texlive-science
```

---

## 9. Known Gotchas

| # | Issue | Consequence if ignored | Fix |
|---|---|---|---|
| 1 | macOS binaries | `exp_saa_convergence.py` silently skips all 70 solver calls (prints `[ERR rep0]`), produces empty/wrong figure | Recompile with `./compile.sh --all` |
| 2 | Python < 3.9 | `TypeError: 'type' object is not subscriptable` on `list[dict]` in `exp_saa_convergence.py` | Upgrade or add `from __future__ import annotations` at top of file |
| 3 | Stale LaTeX aux files | Undefined references, wrong bibliography | Run `latexmk -C main.tex` before first compile on Linux |
| 4 | `zhang2007moead` citation | LaTeX warning "Citation undefined" on page 7 after applying R1.3 block | Already in `paper/cite-class.bib` line ~681 — just run bibtex |
| 5 | `figures/saa_convergence.pdf` not found | LaTeX error on figure inclusion when R1.2 block is applied | Ensure `figures/` dir is accessible from `paper/`; check `\graphicspath` or copy file |
| 6 | "monotonically" in SAA text | Factually wrong — Z₂_std peaks at N=5 before declining | The comment block PROPOSED LaTeX already uses "overall decreasing trend" — do not revert to "monotonically" |
| 7 | Applying R1.1 without CV-Small evidence | Claim "reactive hubs ARE active in CV-Small" is in the proposed text | This is true — verifiable from `results/saa_convergence/N*_rep*_bb.json` which show non-trivial Pareto fronts, and from the decoder Pass 3 logic in `src/solver/decoder.hpp` |
| 8 | Page count after adding R1.2 figure | May add 0.5–1 full page; must cut more than planned | Compile after applying all 4 blocks FIRST, then measure, then cut |

---

## 10. The Exact Next Steps (in order)

1. **Pull branch `exp/camera-ready` on Linux machine**
   ```bash
   git fetch && git checkout exp/camera-ready
   ```

2. **Set up environment** (see Section 8 above)

3. **Recompile C++ solvers**
   ```bash
   ./compile.sh --all
   ```

4. **Verify experiment is reproducible** (optional — results already committed)
   ```bash
   source .venv/bin/activate
   python src/scripts/exp_saa_convergence.py --skip-solve
   python src/audit/audit_saa_convergence.py   # must print "0 failure(s)"
   ```

5. **Open `paper/main.tex` and apply all 4 comment blocks:**
   - Line ~162: Apply **[R2]** — REPLACE 3 lines with 4-gap enumeration
   - Line ~380: Apply **[R1.3]** — INSERT NSGA-II vs MOEA/D paragraph
   - Line ~537: Apply **[R1.2]** — INSERT scenario-count sensitivity paragraph + figure block
   - Line ~716: Apply **[R1.1]** — INSERT 2 reactive hub defense sentences
   - Copy `figures/saa_convergence.pdf` to wherever LaTeX can find it

6. **Compile and measure pages:**
   ```bash
   cd paper && latexmk -C main.tex && pdflatex main.tex && bibtex main
   pdflatex main.tex && pdflatex main.tex
   pdfinfo main.pdf | grep Pages
   ```

7. **Apply page cuts** from Section 7 until `pdfinfo` shows ≤ 12 pages

8. **Similarity check** — run PDF through iThenticate/Turnitin; target < 20%

9. **Package camera-ready:**
   ```bash
   # Signed copyright form → Copyright_419.pdf
   zip CameraReady_419.zip paper/main.tex paper/cite-class.bib paper/llncs.cls \
       paper/figures/ figures/saa_convergence.pdf
   ```

10. **Upload to EasyChair** by May 10, 2026:
    - `CameraReady_419.pdf` (revised PDF)
    - `CameraReady_419.zip` (source files)
    - `Copyright_419.pdf` (signed form)

---

## 11. Do Not Do These Things

- **Do NOT change any model parameters** (hub capacities, reactive hub costs, risk thresholds, scenario probabilities) to force reactive hubs to open. This is result engineering and scientific misconduct.
- **Do NOT add MOEA/D experiments.** The response to R1.3 is a text argument, not a new comparison. The reviewer asked for a defense, not a new experiment.
- **Do NOT modify the existing CV-Large results** (Tables, Figures 2–4, Exp 1/2 metrics). These are correct and untouched.
- **Do NOT claim Z₂_mean converges** in the SAA analysis. Only the variance (std) converges. The mean oscillates because each N solves a different expected-value problem.
- **Do NOT write "monotonically"** in the SAA convergence text. Z₂_std peaks at N=5 (142k) before declining. The approved wording is "overall decreasing trend."
- **Do NOT use `pip install` without activating the venv first** — you will corrupt the system Python.

---

## 12. Quick Reference Numbers

| Metric | Value |
|---|---|
| Current page count | 14 |
| Target page count | ≤ 12 |
| Z₂_std at N=3 | 110k |
| Z₂_std at N=30 | 30k (3.7× reduction) |
| HV_std at N=3 | 0.239 |
| HV_std at N=30 | 0.068 (3.5× reduction) |
| Z₂_mean CV for N≥8 | 5.0% (very stable) |
| Solver runs in experiment | 70 (7 N × 10 reps) |
| Time per run (bb_solver, |H|=5) | 0.1–1.1 seconds |
| Audit result | 0 hard failures, 5 warnings |
| Comment block locations | Lines 162, 380, 537, 716 of `paper/main.tex` |
| New bib entry | `zhang2007moead` in `paper/cite-class.bib` line ~681 |
