import json

with open("central_vietnam_small_drnd.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"=== SMALL INSTANCE DIMENSIONS ===")
print(f"Nodes total: {len(data['nodes']['coords'])}")
print(f"Demands (I): {data['dimensions']['num_I']}")
print(f"Hubs (H): {data['dimensions']['num_H']}")
print(f"Origins (J): {data['dimensions']['num_J']}")
print(f"Scenarios (S): {data['dimensions']['num_S']}")

print("\n=== CAPACITY VALIDATION ===")
max_demand = 0
for sc in data["scenarios"]:
    sc_demand = sum(list(sc['demand'].values()))
    # demand values are float
    if sc_demand > max_demand:
        max_demand = sc_demand
total_kappa = sum(data["hub_params"]["capacity"].values())
print(f"Max Scenario Persons: {max_demand:.0f}")
print(f"Max Scenario Demand (kg, Gamma=3): {max_demand * 3:.0f}")
print(f"Total Hub Capacity kappa_k (kg): {total_kappa}")
print(f"Capacity Coverage Ratio: {total_kappa / (max_demand * 3):.2f}x (should be 3x-6x)")
