import json

def analyze():
    print("--- SAA EVALUATION (Seed 0) ---")
    with open("../results/exp2/CV_large_seed0_saa_eval.json", "r") as f:
        saa_data = json.load(f)["evaluations"]
        
    z1_diffs = []
    z2_diffs = []
    cvs = []
    for sol in saa_data:
        z1_diffs.append((sol["new_Z1"] - sol["orig_Z1"]) / max(1, sol["orig_Z1"]) * 100)
        z2_diffs.append((sol["new_Z2"] - sol["orig_Z2"]) / max(1, sol["orig_Z2"]) * 100)
        cvs.append(sol["new_CV"])
        
    print(f"Mean Z1 difference : {sum(z1_diffs)/len(z1_diffs):.2f}%")
    print(f"Mean Z2 difference : {sum(z2_diffs)/len(z2_diffs):.2f}%")
    print(f"Mean CV in SAA     : {sum(cvs)/len(cvs):.2f}")

    print("\n--- OOS DOUBLE TYPHOON EVALUATION (Seed 0) ---")
    with open("../results/exp2/CV_large_seed0_oos_eval.json", "r") as f:
        oos_data = json.load(f)["evaluations"]
        
    cvs_oos = []
    for sol in oos_data:
        cvs_oos.append(sol["new_CV"])
    
    print(f"Mean CV in OOS     : {sum(cvs_oos)/len(cvs_oos):.2f}")
    
    valid_oos = sum(1 for c in cvs_oos if c == 0)
    print(f"Valid OOS solutions: {valid_oos} / {len(oos_data)}")

if __name__ == "__main__":
    analyze()
