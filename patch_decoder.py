import re

with open("solver/decoder.hpp", "r", encoding="utf-8") as f:
    text = f.read()

# 1. Signature
text = text.replace(
    "void decode(Individual &ind, const DRNDInstance &inst) {",
    "void decode(Individual &ind, const DRNDInstance &inst, FlowDetails* flow_out = nullptr) {"
)

# 2. Init flow_out
init_injection = """
  if (flow_out) {
    flow_out->z_iks.assign(num_S, vector<int>(num_I, -1));
    flow_out->z_iks_m.assign(num_S, vector<int>(num_I, -1));
    flow_out->z_jks.assign(num_S, vector<int>(num_J, -1));
    flow_out->z_jks_m.assign(num_S, vector<int>(num_J, -1));
    flow_out->f_khms.assign(num_S, vector<TransshipmentFlow>());
    flow_out->y_ks.assign(num_S, vector<bool>(num_H, false));
    flow_out->inventory_held.assign(num_S, vector<double>(num_H, 0.0));
  }
"""
text = text.replace(
    "  ind.CV = 0.0;",
    "  ind.CV = 0.0;\n" + init_injection
)

# 3. Demand best mode var
text = text.replace("      double best_travel_time  = inst.big_M;", "      double best_travel_time  = inst.big_M;\n      int    chosen_m          = -1;")

# Pass 1 + Pass 2 capture inner loops:
# Find: bool   reachable = false;
# replaced by matching block and injected chosen_m updates.
# For Pass 1 & Pass 2, it looks like:
def replace_inner_loop(match):
    before = match.group(1)
    return before.replace(
        "if (sc.acc(m, i, k)) { reachable = true; umin(best_t, inst.C_time[m][i][k]); }",
        "if (sc.acc(m, i, k)) { reachable = true; if(inst.C_time[m][i][k] < best_t) { best_t = inst.C_time[m][i][k]; b_m = m; } }"
    )

p1 = re.compile(r"(int\s+k\s*=\s*inst.hub_idx\[ki\];\s*double\s*best_t\s*=\s*inst.big_M;\s*bool\s*reachable\s*=\s*false;\s*for\s*\(int\s*m\s*=\s*0;\s*m\s*<\s*num_M;\s*m\+\+\)\s*\{\s*if\s*\(sc\.acc\(m,\s*i,\s*k\)\)\s*\{\s*reachable\s*=\s*true;\s*umin\(best_t,\s*inst\.C_time\[m\]\[i\]\[k\]\);\s*\}\s*\})")
text = p1.sub(r"int k = inst.hub_idx[ki]; double best_t = inst.big_M; bool reachable = false; int b_m = -1; for(int m=0; m<num_M; m++) { if(sc.acc(m,i,k)) { reachable = true; if(inst.C_time[m][i][k] < best_t) { best_t = inst.C_time[m][i][k]; b_m = m; } } }", text)

# Pass 1 select update
text = text.replace(
    "          best_travel_time = best_t;\n        }",
    "          best_travel_time = best_t;\n          chosen_m = b_m;\n        }"
)

# Pass 2 select update
text = text.replace(
    "          best_travel_time = best_t;\n          break;\n        }",
    "          best_travel_time = best_t;\n          chosen_m = b_m;\n          break;\n        }"
)

# Forced Reactive update
p_react = re.compile(r"(double\s*best_t\s*=\s*inst\.big_M;\s*int\s*bk\s*=\s*inst\.hub_idx\[ki\];\s*for\s*\(int\s*m\s*=\s*0;\s*m\s*<\s*num_M;\s*m\+\+\)\s*if\s*\(sc\.acc\(m,\s*i,\s*bk\)\)\s*umin\(best_t,\s*inst\.C_time\[m\]\[i\]\[bk\]\);)")
text = p_react.sub(r"double best_t=inst.big_M; int bk=inst.hub_idx[ki]; int b_m = -1; for(int m=0; m<num_M; m++) { if(sc.acc(m,i,bk)) { if(inst.C_time[m][i][bk] < best_t) { best_t=inst.C_time[m][i][bk]; b_m=m; } } } chosen_m = b_m;", text)

# Assign chosen_m
assign_demand = """
      } else {
        z_ik[ii]         = best_ki;
        hub_load[best_ki] += D_kg;
        if (flow_out) {
            flow_out->z_iks[si][ii] = best_ki;
            flow_out->z_iks_m[si][ii] = chosen_m;
        }
"""
text = text.replace(
    "      } else {\n        z_ik[ii]         = best_ki;\n        hub_load[best_ki] += D_kg;",
    assign_demand
)

# 4. Origin Assignment
origin_inj = """
      if (best_ki != -1) {
        int    k      = inst.hub_idx[best_ki];
        double best_c = inst.best_cost(j, k, si);
        Z1_s         += best_c * O;
        net_inv[best_ki] += O;
        if (flow_out) {
            int cm = -1;
            for(int m=0; m<num_M; m++) {
                if(sc.acc(m,j,k) && abs(inst.C_cost[m][j][k] - best_c) < 1e-6) { cm = m; break; }
            }
            flow_out->z_jks[si][jj] = best_ki;
            flow_out->z_jks_m[si][jj] = cm;
        }
      }
"""
p_orig = re.compile(r"      if \(best_ki != -1\) \{\s*int    k      = inst\.hub_idx\[best_ki\];\s*double best_c = inst\.best_cost\(j, k, si\);\s*Z1_s         \+= best_c \* O;\s*net_inv\[best_ki\] \+= O;\s*\}")
text = p_orig.sub(origin_inj.strip("\n"), text)

# 5. Transshipment Flow
trans_inj = """
      if (best_c >= inst.big_M) break;
      double flow = std::min(max_surplus, max_deficit);
      Z1_s           += inst.alpha * best_c * flow;
      net_inv[src_ki] -= flow;
      net_inv[dst_ki] += flow;
      if (flow_out) {
          int cm = -1;
          for(int m=0; m<num_M; m++) {
              if(sc.acc(m,k,h) && abs(inst.C_cost[m][k][h] - best_c) < 1e-6) { cm = m; break; }
          }
          flow_out->f_khms[si].push_back({src_ki, dst_ki, cm, flow});
      }
"""
p_trans = re.compile(r"      if \(best_c >= inst\.big_M\) break;\s*double flow = std::min\(max_surplus, max_deficit\);\s*Z1_s           \+= inst\.alpha \* best_c \* flow;\s*net_inv\[src_ki\] -= flow;\s*net_inv\[dst_ki\] \+= flow;")
text = p_trans.sub(trans_inj.strip("\n"), text)


# 6. End of Scenario
end_scen_inj = """
    // Residual deficits → CV
    for (int ki = 0; ki < num_H; ki++)
      if (net_inv[ki] < -EPS) ind.CV += -net_inv[ki];

    if (flow_out) {
        for(int ki=0; ki<num_H; ki++) {
            flow_out->y_ks[si][ki] = y[ki];
            flow_out->inventory_held[si][ki] = inventory[ki];
        }
    }
"""
text = text.replace(
    "    // Residual deficits → CV\n    for (int ki = 0; ki < num_H; ki++)\n      if (net_inv[ki] < -EPS) ind.CV += -net_inv[ki];",
    end_scen_inj
)


with open("solver/decoder.hpp", "w", encoding="utf-8") as f:
    f.write(text)
print("Decoder patched successfully")
