# Project Rules — CITA26 DRND Flood Relief (Central Vietnam)

## 1. Commit discipline

- **Always split commits between code changes and data/JSON changes.**
  Never mix `*.py`, `*.cpp`, `*.hpp` edits with `*.json` result or flow file
  changes in the same commit. JSON files are large diffs that bury code review.
- **Solver result JSONs** (`results/exp*/CV_large_seed*.json`, etc.) are
  immutable ground truth produced by the C++ binary. Never hand-edit them.
- **Flow JSONs** (`results/exp*/flows/solution_*.json`) are derived artifacts.
  Regenerate with `preprocess_flows.py --force`; commit only after the
  validator passes (see §4).
- `.DS_Store`, `paper/main.pdf`, and `_archive/` are never committed.

## 2. Python environment

- **Always use the project venv.** Run scripts as:
  ```
  ./.venv/bin/python3 visualizer/preprocess_flows.py
  ```
  Never `pip install` globally. Add new packages with:
  ```
  ./.venv/bin/pip install <pkg> && ./.venv/bin/pip freeze > requirements.txt
  ```
- The venv lives at `.venv/` (gitignored). Recreate with:
  ```
  python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
  ```

## 3. Two-layer trust model

The codebase has two strictly separated layers:

| Layer | Files | Trust |
|---|---|---|
| **Ground truth** | `results/exp*/CV_large_seed*.json` — `Z1`, `Z2`, `CV`, `X`, `R`, `A` | Immutable C++ solver output. Cite these in the paper. |
| **Derived / visual** | `results/exp*/flows/solution_*.json` — mode assignments, hub assignments | Python postprocessor heuristic. Label as "postprocessed estimate" in the UI, never as solver output. |

Rules that follow from this:
- Paper-reportable numbers (Z1, Z2, CV, active hub count, Pareto ratio) must
  be read directly from the solver JSON, not from flow files.
- Mode counts shown in the KPI dashboard (Road / Water / Air) come from flow
  files and must be presented as estimates, not algorithmic results.
- The `A` vector in a solution (`solution.A[i]`) encodes the **anchor hub
  local index** (0–19), NOT a transport mode. Never read it as a mode.

## 4. Flow file integrity protocol

Before committing any regenerated flow files:

1. **Run the validator:**
   ```
   ./.venv/bin/python3 visualizer/verify_flows.py
   ```
   It checks: every demand node assigned, all assigned hubs have `X=1`, no
   mode assignment violates the accessibility matrix, mode counts match the
   locked snapshot.

2. **If mode counts change**, update `results/exp*/flows_snapshot.json`
   deliberately and explain why in the commit message.

3. **Never force-push flow files without a passing validator run.**

## 5. Postprocessor consistency with the C++ decoder

`preprocess_flows.py` must mirror `src/solver/decoder.hpp::best_mode_time()`:

- Road (0) and Water (1) are evaluated first; pick fastest by `C_time`.
- Air (2) is used only when no road/water hub is reachable
  (`acc[m][d][h] == 1` AND `C_time[m][d][h] < 1e8` for m ∈ {0,1}).
- Hub selection uses **minimum C_time** across all active hubs, not geometric
  distance. Geometric distance is not a proxy for travel time in this terrain.
- The `chi` risk threshold for reactive hub activation must come from
  `instance["global_params"]["chi"]`, never hardcoded.

When the decoder logic in `decoder.hpp` changes, update the postprocessor to
match and regenerate + validate all flow files.

## 6. Paper editing

- Never edit `paper/main.tex` directly. Proposed changes must be wrapped as
  clearly marked comment blocks for the author to review and apply manually
  (the author compiles on Windows/Linux, not this machine).
- Cross-check every quantitative claim in the paper against the solver JSON
  before finalising a section. Past errors found: A-vector misread as mode,
  infeasible flow file used for Figure 4-4, Pareto ratio overstated (1.15×
  actual vs 3.5× claimed).

## 7. Working session conduct

- **Investigate fully before acting.** When an error or anomaly is reported,
  complete all analysis and root-cause investigation independently. Present
  findings and options to the user.
- **Always stop before implementation.** Do not write, edit, or regenerate
  any file until the user has reviewed the diagnosis and explicitly approved
  an option. "Go ahead" or selecting an option counts; ambiguity does not.
- **Never push code unprompted.** `git push` (including `--force-with-lease`)
  requires an explicit "go" from the user in that same message. Auto-mode
  does not change this rule.
- **Auto-mode is not a license to be aggressive.** Even when auto-mode is
  active, do not chain multiple destructive or hard-to-reverse steps without
  pausing for confirmation at each decision point.

## 8. Running the solver

```bash
./src/solver/solver <instance.json> --pop 200 --gen 500 --seed 0 --out <result.json>
```

- Use `--pop 200 --gen 500` for CV Large (Exp 2) and `--pop 150 --gen 300`
  for CV Small (Exp 1) to match paper reproduction settings.
- After a solver run, immediately regenerate flow files and run the validator.
- v1 result files are canonical. Re-running v1 requires explicit intent;
  the UI enforces an overwrite checkbox for this reason.
