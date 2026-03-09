import json
d = json.load(open('tmp/smoke_f4f7f8.json'))
pf = d['pareto_front']
print(f'PF size: {len(pf)}')
for i, s in enumerate(pf):
    print(f'Sol {i}: Z1={s["Z1"]:.2f} Z2={s["Z2"]:.2f} X={s["X"]} R={[round(r,3) for r in s["R"]]} W={[round(w,3) for w in s["W"]]}')

print()
af = d.get('all_feasible', [])
xs = [tuple(s['X']) for s in af]
unique_x = set(xs)
print(f'All feasible: {len(af)}, unique X configs: {len(unique_x)}')
for ux in sorted(unique_x):
    print(f'  {list(ux)}: {xs.count(ux)} times')

# R diversity
print('\nR diversity (all feasible):')
for k in range(len(af[0]['R'])):
    vals = [s['R'][k] for s in af]
    print(f'  R[{k}]: min={min(vals):.4f} max={max(vals):.4f} range={max(vals)-min(vals):.4f}')

print('\nW diversity (all feasible):')
for k in range(len(af[0]['W'])):
    vals = [s['W'][k] for s in af]
    print(f'  W[{k}]: min={min(vals):.4f} max={max(vals):.4f} range={max(vals)-min(vals):.4f}')
