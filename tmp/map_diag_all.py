import json
import os
import sys

sys.path.append(os.path.abspath('src/scripts'))
import exp2_map_solution as m

inst = json.load(open('data/cv/cv_large_drnd.json'))
res = json.load(open('results/exp2/cv_large_seed0.json'))
pf = res.get('pareto_front', []) or res.get('all_feasible', [])
print('n', len(pf))

z1 = [s['Z1'] for s in pf]
z2 = [s['Z2'] for s in pf]

def nz(v, a, b):
    return 0 if b - a < 1e-12 else (v - a) / (b - a)

knee = min(
    pf,
    key=lambda s: (nz(s['Z1'], min(z1), max(z1)) - 0.5) ** 2
    + (nz(s['Z2'], min(z2), max(z2)) - 0.5) ** 2,
)

for tag, sol in [
    ('minZ1', min(pf, key=lambda s: s['Z1'])),
    ('knee', knee),
    ('minZ2', min(pf, key=lambda s: s['Z2'])),
]:
    print('\n', tag, sol['Z1'], sol['Z2'])
    for si in range(inst['dimensions']['num_S']):
        dec = m.decode_exact(sol, inst, si)
        print(' s', si, 'reactive', len(dec['reactive_hubs']), 'trans', len(dec['transshipments']))

cnt = 0
for sol in pf:
    t = 0
    for si in range(inst['dimensions']['num_S']):
        t += len(m.decode_exact(sol, inst, si)['transshipments'])
    if t > 0:
        cnt += 1
print('\nsolutions_with_any_trans', cnt)
