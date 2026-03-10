import re
import subprocess

cfgs = [(120, 8, 5, 3), (120, 8, 7, 3), (160, 10, 7, 3)]
best = None

for it, st, tt, km in cfgs:
    subprocess.run([
        './src/solver/vns_ts_baseline', 'data/cv/cv_small_drnd.json', '--seed', '42',
        '--iter', str(it), '--time-limit', '60', '--tabu-tenure', str(tt),
        '--kmax', str(km), '--starts', str(st), '--out', 'results/exp1/cv_small_vns_ts.json'
    ], check=True, capture_output=True, text=True)

    e = subprocess.run([
        'python3', 'src/scripts/exp1_evaluate_cv_small.py',
        '--milp-aws', 'results/exp1/cv_small_milp_aws.json',
        '--milp-eps', 'results/exp1/cv_small_milp_eps.json',
        '--bb', 'results/exp1/cv_small_bb.json',
        '--greedy', 'results/exp1/cv_small_greedy.json',
        '--vns-ts', 'results/exp1/cv_small_vns_ts.json',
        '--ours', 'results/exp1/cv_small_pb_nsga.json',
    ], capture_output=True, text=True)

    m = re.search(r'^\s*VNS-TS\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)', e.stdout, re.M)
    if not m:
        print('PARSE_FAIL', it, st, tt, km)
        continue

    hv = float(m.group(1))
    igd = float(m.group(2))
    wall = float(m.group(3))
    print(it, st, tt, km, '=>', hv, igd, wall)

    rec = (hv, -igd, -wall, it, st, tt, km)
    if best is None or rec > best[0]:
        best = (rec, (it, st, tt, km, hv, igd, wall))

print('BEST', best[1] if best else None)
