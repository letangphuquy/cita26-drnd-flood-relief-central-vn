# CV Large — v2 (OSRM-validated) solver output

Placeholder. `data/cv/v2/cv_large_drnd.json` (== top-level
`data/cv/cv_large_drnd.json`) has not been solved yet — it is a different
problem instance from the `v1` dataset behind `results/exp2/CV_large_seed0.json`
(different `transport`, `theta`, `demand`, `hub_risk`, `accessibility`, etc.).

## To populate

1. Run the solver (PB-NSGA / MILP / etc.) against
   `data/cv/v2/cv_large_drnd.json`, saving the output as
   `results/exp2/v2/CV_large_seed0.json`.
2. Generate per-solution flow detail:
   ```
   python visualizer/preprocess_flows.py \
       --instance data/cv/v2/cv_large_drnd.json \
       --result   results/exp2/v2/CV_large_seed0.json \
       --out-dir  results/exp2/v2/flows
   ```

`visualizer/app.py` auto-detects `results/exp2/v2/CV_large_seed0.json` and
enables the "CV Large — v2" Solution Explorer once it exists.
