# CV Small — v2 (OSRM-validated) solver output

Placeholder. `data/cv/v2/cv_small_drnd.json` (== top-level
`data/cv/cv_small_drnd.json`) has not been solved yet — it is a different
problem instance from the `v1` dataset behind
`results/exp1/cv_small_pb_nsga.json` (different `transport`, `theta`,
`demand`, `hub_risk`, `accessibility`, etc.).

## To populate

1. Run the solver (PB-NSGA / MILP / etc.) against
   `data/cv/v2/cv_small_drnd.json`, saving the output as
   `results/exp1/v2/cv_small_pb_nsga.json`.
2. Generate per-solution flow detail:
   ```
   python visualizer/preprocess_flows.py \
       --instance data/cv/v2/cv_small_drnd.json \
       --result   results/exp1/v2/cv_small_pb_nsga.json \
       --out-dir  results/exp1/v2/flows
   ```

`visualizer/app.py` auto-detects `results/exp1/v2/cv_small_pb_nsga.json` and
enables the "CV Small — v2" Solution Explorer once it exists.
