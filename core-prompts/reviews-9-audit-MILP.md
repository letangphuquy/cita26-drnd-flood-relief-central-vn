NOTE: SOLUTIONs to the below issues
- Since in the planning phase, we will not know before hand the actual risk after the disaster struck.
- For clarity, I would split risk into two parts:
    - Intrinsic geographical risk (type I)
    - Scenario-specific risk (type II)
- Planned hub safety is defined by type I risk
- Scenario-specific safety is defined by type II risk
- Fix the hard-constraints on hub safety, easily.
- To account for the effects of scenario-specific risk on planned hubs: Deduct the inventory amount, or increasing routing cost, processing time, etc. ... by a lambda

- Important: These insights should be saved as response against reviewers's comment or for future work.

===========
Tiến hành quá trình audit và fact-check đối chiếu giữa mã nguồn MILP (Python) và formulation toán học (LaTeX). Dưới đây là báo cáo kiểm tra chi tiết từng khối logic.

### 1. Hàm mục tiêu (Objectives)

#### Khối 1: Objective 1 - Expected Logistics Cost ($Z_1$)

**Code block định vị:**

```python
z1_expr = solver.Sum(F_hub[ki] * x[ki] + C_hub[ki] * q[ki] for ki in range(num_H))
# ... (vòng lặp kịch bản s)
z1_expr += pi * solver.Sum(sc["hub_reactive_cost"]... * y[ki, si] ...)
z1_expr += pi * (min_c * supply_j * z_jks[ji, ki, si])
z1_expr += pi * (alpha * c_thm * f_khms[ki, hi, m, si])
z1_expr += pi * (theta_val * z_iks[ii, ki, si])
z1_expr += pi * (sum(u_is[ii, si]...) * big_M) + pi * (sum(v_js[ji, si]...) * big_M)

```

**Ý nghĩa & Toán học:** Tính tổng chi phí logistics bao gồm 2 giai đoạn: Chi phí quy hoạch cố định ($F_k x_k + c_k q_k$) và kỳ vọng chi phí vận hành trong thảm họa (Thiết lập hub tạm $y_{ks}$, Cung ứng nguồn $z_{jks}$, Trung chuyển $f_{khms}$, và Phân phối Last-mile $z_{iks}$). Đồng thời, phạt rất nặng (Big-M) đối với lượng cung/cầu không được phục vụ ($u_{is}, v_{js}$).
Toán học: $Z_1 = \sum (F_k x_k + c_k q_k) + \sum \pi_s \Big[ \sum F_{ks}^a y_{ks} + \sum c_{jks} O_{js} z_{jks} + \sum \alpha C_{khm} f_{khms} + \sum \Theta_{kis} z_{iks} + M \sum(u_{is} + v_{js}) \Big]$
**Formulation trong Paper:** Phương trình (1) `\text{Min } Z_1 = \dots`
**Điểm khác biệt:** Code bổ sung thêm thành phần phạt biến slack `u_is` và `v_js` nhân với `big_M`. Trong paper hoàn toàn không có hàm phạt này vì paper sử dụng Hard Constraints để ép mạng lưới phải phục vụ 100% demand.

#### Khối 2: Objective 2 - Expected Maximum Deprivation Cost ($Z_2$)

**Code block định vị:**

```python
z2_expr = solver.Sum(inst["scenarios"][si]["probability"] * z2_max_s[si] for si in range(num_S))

```

**Ý nghĩa & Toán học:**
Tính giá trị kỳ vọng của chi phí thiếu hụt (deprivation cost) tồi tệ nhất trong mạng lưới dựa trên biến phụ $W_s$ (ở đây code đặt tên là `z2_max_s`).
Toán học: $Z_2 = \sum \pi_s W_s$
**Formulation trong Paper:** Phương trình (8) `Z_2^{\text{linear}} = \sum_{s \in \mathcal{S}} \pi_s \cdot W_s`
**Điểm khác biệt:** Hoàn toàn khớp.

---

### 2. Ràng buộc (Constraints)

#### Khối 3: Ràng buộc chứa Tồn kho (Inventory Capacity)

**Code block định vị:**

```python
solver.Add(q[ki] <= K_hub[ki] * x[ki])

```

**Ý nghĩa & Toán học:** $q_k \le \kappa_k x_k$. Lượng hàng tồn kho tại hub $k$ không được vượt quá sức chứa $\kappa_k$ và chỉ được phép phân bổ nếu hub $k$ được quyết định xây dựng từ giai đoạn 1 ($x_k = 1$).
**Formulation trong Paper:** Constraint (12) `q_k \le \kappa_k \cdot x_k`
**Điểm khác biệt:** Hoàn toàn khớp.

#### Khối 4: Cơ chế kích hoạt Hub (Planned Hub Activation)

**Code block định vị:**

```python
is_safe_or_best = (sc["risk"][k_node] <= chi or sc["risk"][k_node] <= min_risk_s + 1e-7)
if not is_safe_or_best: solver.Add(x_act[ki, si] == 0)
else: solver.Add(x_act[ki, si] <= x[ki])

```

**Ý nghĩa & Toán học:** Giới thiệu một biến trạng thái ẩn $x\_act_{ks} \in [0,1]$ nhằm vô hiệu hóa hub quy hoạch $x_k$ trong các kịch bản có rủi ro vượt ngưỡng an toàn $\chi$ (trừ khi nó là lựa chọn duy nhất/an toàn nhất). Toán học: $x\_act_{ks} \le x_k$ và $x\_act_{ks} = 0 \text{ nếu } r_{ks} > \chi$.
**Formulation trong Paper:** Không tồn tại biến $x\_act_{ks}$. Ràng buộc an toàn trong paper là Constraint (13): $r_{ks} \cdot (x_k + y_{ks}) \le \chi$.
**Điểm khác biệt nghiêm trọng:** Paper định nghĩa sai logic toán học. Constraint (13) của paper bắt buộc $x_k = 0$ nếu tồn tại **bất kỳ** kịch bản $s$ nào làm $r_{ks} > \chi$. Mã Python đã cố tình tạo ra biến `x_act` để "lách" lỗi này, cho phép $x_k$ vẫn bằng 1 nhưng chỉ tạm ngưng hoạt động ở kịch bản $s$. Cần sửa lại công thức trong paper để đồng bộ với code.

#### Khối 5: Độc quyền vị trí (Mutual Exclusivity)

**Code block định vị:**

```python
solver.Add(x[ki] + y[ki, si] <= 1)

```

**Ý nghĩa & Toán học:** $x_k + y_{ks} \le 1$. Tại một toạ độ $k$, chỉ có thể tồn tại cơ sở hạ tầng được xây dựng sẵn ($x_k$) hoặc một trạm dã chiến được dựng lên sau thảm họa ($y_{ks}$), không thể chồng chéo.
**Formulation trong Paper:** Constraint (11) `x_k + y_{ks} \le 1`
**Điểm khác biệt:** Hoàn toàn khớp.

#### Khối 6: Ràng buộc an toàn cho Hub phản ứng nhanh (Reactive Safety)

**Code block định vị:**

```python
if risk_k > chi: solver.Add(y[ki, si] == 0)
else: solver.Add(risk_k * y[ki, si] <= chi)

```

**Ý nghĩa & Toán học:** Trạm dã chiến $y_{ks}$ tuyệt đối không được thiết lập tại vùng có rủi ro $r_{ks} > \chi$. Toán học: $r_{ks} \cdot y_{ks} \le \chi$.
**Formulation trong Paper:** Constraint (13) `r_{ks} \cdot (x_k + y_{ks}) \le \chi`
**Điểm khác biệt:** Code Python chỉ ràng buộc điều kiện rủi ro trực tiếp lên biến $y_{ks}$, bỏ qua $x_k$ (đã được xử lý qua $x\_act_{ks}$ ở Khối 4).

#### Khối 7: Single-Allocation & Rớt mạng (Demand / Origin Assignment)

**Code block định vị:**

```python
solver.Add(sum(z_iks[ii, ki, si] for ki in range(num_H)) + u_is[ii, si] == 1)
# Và tương tự cho Origin:
solver.Add(sum(z_jks[ji, ki, si] for ki in range(num_H)) + v_js[ji, si] == 1)

```

**Ý nghĩa & Toán học:** $\sum_k z_{iks} + u_{is} = 1$ và $\sum_k z_{jks} + v_{js} = 1$. Mỗi nạn nhân $i$ hoặc nguồn cung $j$ phải được điều phối tới chính xác 1 hub $k$. Nếu bất khả thi, hệ thống sẽ đẩy giá trị vào biến slack $u_{is}, v_{js}$ (đồng nghĩa với việc rớt mạng / bỏ rơi nạn nhân).
**Formulation trong Paper:** Constraints (14) và (15): $\sum_{k \in \mathcal{H}} z_{iks} = 1$ và $\sum_{k \in \mathcal{H}} z_{jks} = 1$.
**Điểm khác biệt:** Giống như Khối 1, mã Python nới lỏng bài toán thành Soft Constraint để chống Infeasible bằng biến slack, trong khi formulation LaTeX đang ép hệ thống vào trạng thái lý tưởng tuyệt đối (Hard Constraint).

#### Khối 8: Điều kiện liên kết khả thi (Valid Assignment)

**Code block định vị:**

```python
solver.Add(z_iks[ii, ki, si] <= x_act[ki, si] + y[ki, si])
solver.Add(z_jks[ji, ki, si] <= x_act[ki, si] + y[ki, si])

```

**Ý nghĩa & Toán học:** $z_{iks} \le x\_act_{ks} + y_{ks}$. Dòng người và hàng hóa chỉ được phép điều hướng về hub $k$ nếu hub này đang trong trạng thái mở cửa hoạt động.
**Formulation trong Paper:** Constraints (16) và (17): $z_{iks} \le x_k + y_{ks}$.
**Điểm khác biệt:** Mã Python sử dụng trạng thái kích hoạt cục bộ `x_act` thay vì trạng thái xây dựng vật lý `x_k`.

#### Khối 9: Ràng buộc Vật lý Tuyến đường (Path Accessibility)

**Code block định vị:**

```python
acc_sum = sum(sc["accessibility"][m][k_node][i_node] for m in range(num_M))
solver.Add(z_iks[ii, ki, si] <= acc_sum)
# Tương tự cho z_jks và f_khms

```

**Ý nghĩa & Toán học:** $z_{iks} \le \sum_m a_{ikms}$. Chỉ phân bổ khi tồn tại ít nhất một phương tiện $m$ có thể vượt qua địa hình để tiếp cận nạn nhân. Với tuyến trung chuyển: $f_{khms} \le M \cdot a_{khms}$.
**Formulation trong Paper:** Constraints (18), (19) và (20).
**Điểm khác biệt:** Hoàn toàn khớp.

#### Khối 10: Cân bằng Dòng chảy (Flow Balance)

**Code block định vị:**

```python
inventory_s = q[ki] + 0.5 * K_hub[ki] * y[ki, si]
solver.Add(inventory_s + sum_supply_items + sum_trans_in >= sum_demand_items + sum_trans_out)

```

**Ý nghĩa & Toán học:** Tổng Tồn kho + Tổng Cung bên ngoài + Tổng nhận Trung chuyển $\ge$ Tổng Cầu + Tổng gửi Trung chuyển. Đáng chú ý, Python tự động bơm một lượng hàng hóa ảo bằng 50% sức chứa cho các hub phản ứng nhanh (`0.5 * K_hub[ki] * y[ki, si]`).
**Formulation trong Paper:** Constraint (21)
**Điểm khác biệt nghiêm trọng:** 1. Paper không hề cấp tồn kho $q_k$ cho hub $y_{ks}$ (vì $q_k$ bị chặn bởi $x_k$ ở Constraint 12). Code Python lại "lén" bơm $0.5 \kappa_k$ cho $y_{ks}$.
2. Bất đẳng thức trong paper bị viết ngược dấu. Paper ghi: `Tổng Cầu + Gửi Trung chuyển <= Tồn kho + Tổng Cung + Nhận Trung chuyển`. Logic thực tế phải là "Nguồn lực có sẵn $\ge$ Nhu cầu tiêu thụ", python code dùng đúng dấu `>=` nhưng biểu thức trong paper bị sắp xếp ngược vế logic.

#### Khối 11: Thông lượng tối đa (Throughput capacity)

**Code block định vị:**

```python
solver.Add(q[ki] + sum(...) + sum(...) <= K_hub[ki] * (x_act[ki, si] + y[ki, si]))

```

**Ý nghĩa & Toán học:** Lượng hàng hóa lưu chuyển qua hub không được vỡ quỹ đạo sức chứa vật lý $\kappa_k$.
**Formulation trong Paper:** Constraint (22)
**Điểm khác biệt:** Lại xuất hiện biến `x_act` trong code thay cho `x_k` ở paper.

#### Khối 12: Hạn mức Trực thăng (Helicopter Quota)

**Code block định vị:**

```python
solver.Add(heli_assign_i + heli_assign_j + heli_trans <= 0.15 * total_links_s + 0.999)

```

**Ý nghĩa & Toán học:** Khống chế tổng số chuyến bay trực thăng không được vượt quá 15% tổng lưu lượng toàn tuyến mạng lưới.
**Formulation trong Paper:** KHÔNG TỒN TẠI.
**Điểm khác biệt nghiêm trọng:** Đây là một Hard Constraint nằm trong mã nguồn MILP (và Decoder C++ như dữ liệu trước đó) nhưng hoàn toàn bị lãng quên trong bản thảo LaTex.

#### Khối 13: Tuyến tính hóa Z2 (Z2 Linearization)

**Code block định vị:**

```python
solver.Add(z2_max_s[si] >= c_dep * z_iks[ii, ki, si])
solver.Add(z2_max_s[si] >= u_is[ii, si] * penalty)

```

**Ý nghĩa & Toán học:** Định nghĩa biến cận trên $W_s \ge C^{dep}_{iks} z_{iks}$. Nếu nạn nhân bị bỏ rơi ($u_{is} = 1$), phạt $W_s$ vọt lên ngưỡng kịch trần (tương đương 24h chờ đợi).
**Formulation trong Paper:** Constraint (10) `W_s \ge C^{\text{dep}}_{is} \cdot z_{iks}`
**Điểm khác biệt:** Paper thiếu mất ràng buộc ép góc (epigraph) rớt demand $u_{is}$ cho biến $W_s$.



# MORE CONTEXT: THE PROMPT
Bây giờ nhé. Tôi dán vào đây 2 file. Một là MILP solver in Python, hai là bản formulation gốc của tôi (LaTex). Bạn hãy hỗ trợ tôi audit và fact-check code trong AI. Format: Định vị và re-state Mỗi block of code trong MILP solver có chức năng là define objective hoặc define constraint, dịch ý nghĩa ra thành ngôn ngữ tự nhiên và toán. Sau đó tìm constraint gần giống nhất trong paper của tôi và chỉ ra có những điểm nào khác biệt. Thực hiện audit đầy đủ với tất cả constraints và objectives.

import json
import argparse
import sys
import math
import time
import numpy as np
from ortools.linear_solver import pywraplp

def load_instance(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def calc_theta_is_constant(D_is, A_i, kim, C_m, Q_m, Phi, eta):
    """Calculate the deterministic last-mile cost per assigning grid i to hub k via mode m in scenario s."""
    if D_is <= 1e-6:
        return 0.0
    line_haul = 2.0 * kim * math.ceil(D_is / Q_m)
    local_detour = C_m * Phi * math.sqrt(math.ceil(D_is / eta) * A_i)
    return line_haul + local_detour

def build_and_solve_milp(inst, w1=1.0, w2=0.0, eps_z1=None, eps_z2=None, time_limit_s=600):
    """
    Builds the MO-IHLNDP MILP using OR-Tools (SCIP).
    Minimizes Z = w1 * Z1 + w2 * Z2

    Decision variables follow the paper formulation exactly:
      x_k         : binary, planned hub establishment
      y_ks        : binary, reactive hub in scenario s
      z_iks       : binary, demand i assigned to hub k in scenario s  (NO mode dimension)
      z_jks       : binary, origin j supplies hub k in scenario s      (NO mode dimension)
      q_k         : continuous, inventory pre-positioned at hub k
      f_khms      : continuous, lateral transshipment flow k->h via mode m in scenario s
      w_trans_khms: binary, indicator that the transshipment arc k->h/m/s is used
      u_is, v_js  : continuous slack for unassigned demand/supply (penalized)
      W_s (z2_max_s): continuous, epigraph variable for max deprivation per scenario
    """
    solver = pywraplp.Solver.CreateSolver('SCIP')
    if not solver:
        print("SCIP solver not available.")
        return None

    solver.SetTimeLimit(time_limit_s * 1000)

    dims = inst["dimensions"]
    num_H = dims["num_H"]
    num_I = dims["num_I"]
    num_S = dims["num_S"]
    num_J = dims["num_J"]
    num_M = dims["num_M"]

    chi   = inst["global_params"]["chi"]
    # NOTE: big_M lives under global_params, not at root level
    big_M = inst["global_params"].get("big_M", 1e7)
    gamma = inst["global_params"]["gamma"]
    alpha = inst["global_params"]["alpha"]
    Phi   = inst["global_params"]["daganzo_phi"]
    eta   = inst["global_params"]["daganzo_eta"]

    F_hub = [inst["hub_params"]["fixed_cost"][str(k)] for k in inst["nodes"]["hub_indices"]]
    C_hub = [inst["hub_params"]["hold_cost"][str(k)]  for k in inst["nodes"]["hub_indices"]]
    K_hub = [inst["hub_params"]["capacity"][str(k)]   for k in inst["nodes"]["hub_indices"]]

    # Tight upper bound on flow variables
    tot_cap = sum(K_hub)

    # -------------------------------------------------------------------------
    # 1. Decision Variables
    # -------------------------------------------------------------------------
    x = {}  # x_k ∈ {0,1}: planned hub
    q = {}  # q_k >= 0   : pre-positioned inventory
    for ki in range(num_H):
        x[ki] = solver.IntVar(0, 1, f'x_{ki}')
        q[ki] = solver.NumVar(0, K_hub[ki], f'q_{ki}')
        # (C2) inventory only if hub is built: q_k <= kappa_k * x_k
        solver.Add(q[ki] <= K_hub[ki] * x[ki])

    y        = {}  # y_{k,s} ∈ {0,1}
    # z_iks  : demand i -> hub k in scenario s  (single variable, no mode index)
    z_iks    = {}
    # z_jks  : origin j -> hub k in scenario s  (single variable, no mode index)
    z_jks    = {}
    f_khms   = {}  # lateral transshipment flow
    w_trans  = {}  # binary arc-use indicator
    u_is     = {}  # unassigned demand slack
    v_js     = {}  # unassigned supply slack
    z2_max_s = {}  # W_s (epigraph for Z2)

    for si in range(num_S):
        z2_max_s[si] = solver.NumVar(0, solver.infinity(), f'W_{si}')
        for ki in range(num_H):
            y[ki, si] = solver.IntVar(0, 1, f'y_{ki}_{si}')
            for ii in range(num_I):
                z_iks[ii, ki, si] = solver.IntVar(0, 1, f'z_i{ii}_k{ki}_s{si}')
            for ji in range(num_J):
                z_jks[ji, ki, si] = solver.IntVar(0, 1, f'z_j{ji}_k{ki}_s{si}')
            for hi in range(num_H):
                for m in range(num_M):
                    f_khms[ki, hi, m, si] = solver.NumVar(0, tot_cap, f'f_{ki}_{hi}_{m}_{si}')
                    w_trans[ki, hi, m, si] = solver.IntVar(0, 1, f'w_trans_{ki}_{hi}_{m}_{si}')
        for ii in range(num_I):
            u_is[ii, si] = solver.NumVar(0, solver.infinity(), f'u_{ii}_{si}')
        for ji in range(num_J):
            v_js[ji, si] = solver.NumVar(0, solver.infinity(), f'v_{ji}_{si}')

    # -------------------------------------------------------------------------
    # Scenario-dependent planned hub activation
    # x_act[k,s] = 1 iff hub k was built AND its risk <= chi in scenario s.
    # Implemented as a continuous variable in [0,1] tightened by two inequalities
    # rather than an integer var, to avoid branching overhead.
    # -------------------------------------------------------------------------
    x_act = {}
    for si in range(num_S):
        sc = inst["scenarios"][si]
        # Find the minimum risk among ALL hub candidates in this scenario
        min_risk_s = min(inst["scenarios"][si]["risk"][inst["nodes"]["hub_indices"][h]] for h in range(num_H))
        for ki in range(num_H):
            x_act[ki, si] = solver.IntVar(0, 1, f'x_act_{ki}_{si}')
            # (a) can only be active if hub was built
            # Match C++ decoder: A hub is "active" if it was built AND (it's safe OR it's the least-risky fallback)
            k_node = inst["nodes"]["hub_indices"][ki]
            
            # x_act[ki, si] = 1 iff (x[ki] == 1) AND (risk <= chi OR risk == min_risk_s)
            is_safe_or_best = (sc["risk"][k_node] <= chi or sc["risk"][k_node] <= min_risk_s + 1e-7)
            
            if not is_safe_or_best:
                solver.Add(x_act[ki, si] == 0)
            else:
                solver.Add(x_act[ki, si] <= x[ki])
                # Optimization: x_act can be 1 if x[ki] is 1 and it's safe/best. 
                # The solver will naturally want x_act=1 to use pre-positioned inventory.

    # -------------------------------------------------------------------------
    # 2. Constraints
    # -------------------------------------------------------------------------
    for si, sc in enumerate(inst["scenarios"]):
        for ki in range(num_H):
            k_node = inst["nodes"]["hub_indices"][ki]

            # (C1) Hub mutual exclusivity: a location is either planned OR reactive
            solver.Add(x[ki] + y[ki, si] <= 1)

            # (C3) Safety constraint for reactive hub: r_{ks} * y_{ks} <= chi
            #      Equivalently: y_{ks} = 0 whenever r_k > chi
            risk_k = sc["risk"][k_node]
            if risk_k > chi:
                solver.Add(y[ki, si] == 0)
            else:
                # Linearised safety: risk_k * y[ki,si] <= chi * y[ki,si] is trivially
                # true; the constraint is only binding when risk_k > chi (above).
                # Add an explicit bound for the BigM-free form:
                solver.Add(risk_k * y[ki, si] <= chi)

        # ---- Demand assignment constraints -----------------------------------
        for ii in range(num_I):
            i_node = inst["nodes"]["demand_indices"][ii]
            demand_i = float(sc["demand"][str(i_node)])

            if demand_i > 1e-6:
                # (C4) Single-allocation: sum_k z_iks + u_is = 1
                solver.Add(
                    sum(z_iks[ii, ki, si] for ki in range(num_H)) + u_is[ii, si] == 1
                )
                for ki in range(num_H):
                    k_node = inst["nodes"]["hub_indices"][ki]

                    # (C6) Assignment only to active hub (planned-active or reactive)
                    solver.Add(z_iks[ii, ki, si] <= x_act[ki, si] + y[ki, si])

                    # (C8) Assignment only if at least one mode is accessible
                    #      z_iks <= sum_m a_{ikms}
                    acc_sum = sum(
                        sc["accessibility"][m][k_node][i_node]
                        for m in range(num_M)
                    )
                    solver.Add(z_iks[ii, ki, si] <= acc_sum)
            else:
                # Zero demand: freeze all assignment variables
                solver.Add(u_is[ii, si] == 0)
                for ki in range(num_H):
                    solver.Add(z_iks[ii, ki, si] == 0)

        # ---- Origin assignment constraints -----------------------------------
        for ji in range(num_J):
            j_node = inst["nodes"]["origin_indices"][ji]
            supply_j = float(sc["supply"][str(j_node)])

            if supply_j > 1e-6:
                # (C5) Single-allocation: sum_k z_jks + v_js = 1
                solver.Add(
                    sum(z_jks[ji, ki, si] for ki in range(num_H)) + v_js[ji, si] == 1
                )
                for ki in range(num_H):
                    k_node = inst["nodes"]["hub_indices"][ki]

                    # (C7) Assignment only to active hub
                    solver.Add(z_jks[ji, ki, si] <= x_act[ki, si] + y[ki, si])

                    # (C9) Assignment only if at least one mode is accessible
                    acc_sum = sum(
                        sc["accessibility"][m][j_node][k_node]
                        for m in range(num_M)
                    )
                    solver.Add(z_jks[ji, ki, si] <= acc_sum)
            else:
                solver.Add(v_js[ji, si] == 0)
                for ki in range(num_H):
                    solver.Add(z_jks[ji, ki, si] == 0)

        # ---- Transshipment and flow constraints ------------------------------
        for ki in range(num_H):
            k_node = inst["nodes"]["hub_indices"][ki]
            for hi in range(num_H):
                for m in range(num_M):
                    h_node = inst["nodes"]["hub_indices"][hi]
                    # (C10) Transshipment only on intact arcs
                    solver.Add(
                        f_khms[ki, hi, m, si] <= tot_cap * sc["accessibility"][m][k_node][h_node]
                    )
                    # Arc-use indicator coupling
                    solver.Add(f_khms[ki, hi, m, si] <= tot_cap * w_trans[ki, hi, m, si])

            # (C11) Inventory + supply + transshipment_in >= demand + transshipment_out
            # inventory_available = q[ki] if x_act[ki,si] else (0.5 * kappa if y[ki,si])
            inventory_s = q[ki] + 0.5 * K_hub[ki] * y[ki, si]
            
            # Demand sum must be converted from people to relief items via gamma
            sum_demand_items = sum(z_iks[ii, ki, si] * float(sc["demand"][str(inst["nodes"]["demand_indices"][ii])]) * gamma for ii in range(num_I))
            sum_supply_items = sum(z_jks[ji, ki, si] * float(sc["supply"][str(inst["nodes"]["origin_indices"][ji])]) for ji in range(num_J))
            sum_trans_in     = sum(f_khms[hi, ki, m, si] for hi in range(num_H) for m in range(num_M))
            sum_trans_out    = sum(f_khms[ki, hi, m, si] for hi in range(num_H) for m in range(num_M))

            solver.Add(
                inventory_s + sum_supply_items + sum_trans_in >= sum_demand_items + sum_trans_out
            )
            # (C12) Assignment/Flow only if active (planned-active or reactive)
            solver.Add(y[ki, si] + x_act[ki, si] <= 1)

            # (C12) Throughput capacity: total inflow <= kappa * hub_active
            solver.Add(
                q[ki] + sum(z_jks[ji, ki, si] * float(sc["supply"][str(inst["nodes"]["origin_indices"][ji])]) for ji in range(num_J)) + sum(f_khms[hi, ki, m, si] for hi in range(num_H) for m in range(num_M)) <= K_hub[ki] * (x_act[ki, si] + y[ki, si])
            )

        # ---- Helicopter quota (Mode index 2 = air/helicopter) ---------------
        # At most 15% of active routing links may use mode 2.
        # Using w_trans and z_iks/z_jks (same as before, but now z has no mode dim).
        # Count of helicopter z-links: each z_iks with helicopter as the only
        # accessible mode counts once. Since z_iks is not mode-indexed, we track
        # whether that assignment *uses* helicopter via the accessibility pattern.
        # For the quota, we tie it to the arc-use indicators w_trans for
        # transshipment links (mode=2), and separately for z links we use the
        # accessibility flag per mode as a coefficient proxy.
        heli_assign_i = solver.Sum(
            z_iks[ii, ki, si]
            for ii in range(num_I)
            for ki in range(num_H)
            if (
                sc["accessibility"][2][inst["nodes"]["hub_indices"][ki]][inst["nodes"]["demand_indices"][ii]]
                and not any(
                    sc["accessibility"][m2][inst["nodes"]["hub_indices"][ki]][inst["nodes"]["demand_indices"][ii]]
                    for m2 in range(num_M) if m2 != 2
                )
            )
        )
        heli_assign_j = solver.Sum(
            z_jks[ji, ki, si]
            for ji in range(num_J)
            for ki in range(num_H)
            if (
                sc["accessibility"][2][inst["nodes"]["origin_indices"][ji]][inst["nodes"]["hub_indices"][ki]]
                and not any(
                    sc["accessibility"][m2][inst["nodes"]["origin_indices"][ji]][inst["nodes"]["hub_indices"][ki]]
                    for m2 in range(num_M) if m2 != 2
                )
            )
        )
        heli_trans = solver.Sum(
            w_trans[ki, hi, 2, si]
            for ki in range(num_H)
            for hi in range(num_H)
        )
        total_links_s = (
            solver.Sum(z_iks[ii, ki, si] for ii in range(num_I) for ki in range(num_H)) +
            solver.Sum(z_jks[ji, ki, si] for ji in range(num_J) for ki in range(num_H)) +
            solver.Sum(w_trans[ki, hi, m, si] for ki in range(num_H) for hi in range(num_H) for m in range(num_M))
        )
        solver.Add(heli_assign_i + heli_assign_j + heli_trans <= 0.15 * total_links_s + 0.999)

        # ---- Z2 linearization -----------------------------------------------
        # W_s >= C^dep_{i,k,s} * z_iks  for all i,k,s  (eq:deprivation_bound)
        # C^dep_{i,k,s} = D_is * ( exp(lambda_is * (tau_ks + 2 * min_m tau_kim)) - 1 )
        # Because z_iks is single-allocation per demand, this is Big-M-free:
        # exactly one z_iks can be 1 per demand i, so W_s >= max_k [C^dep * z_iks].
        for ii in range(num_I):
            i_node = inst["nodes"]["demand_indices"][ii]
            demand_i = float(sc["demand"][str(i_node)])
            if demand_i <= 1e-6:
                continue

            lam_is = inst["lambda"][f"{i_node}_{si}"]

            # Penalty for unassigned demand (no hub reached)
            penalty = demand_i * min(math.expm1(lam_is * 24.0), 1e6)  # 24h wait cap
            solver.Add(z2_max_s[si] >= u_is[ii, si] * penalty)

            for ki in range(num_H):
                k_node = inst["nodes"]["hub_indices"][ki]

                # Find best (minimum) travel time for (i, k) pair across accessible modes
                min_t = float('inf')
                any_acc = False
                for m in range(num_M):
                    if sc["accessibility"][m][k_node][i_node]:
                        t = inst["transport"]["time"][m][k_node][i_node]
                        if t < min_t:
                            min_t = t
                        any_acc = True

                if any_acc:
                    tau_ks = sc["hub_process_time"][str(k_node)]
                    omega_iks = tau_ks + 2.0 * min_t
                    c_dep = demand_i * math.expm1(min(lam_is * omega_iks, 20.0))

                    # W_s >= C^dep_{iks} * z_{iks}   (binding when z_{iks}=1)
                    solver.Add(z2_max_s[si] >= c_dep * z_iks[ii, ki, si])

    # -------------------------------------------------------------------------
    # 3. Objective Functions
    # -------------------------------------------------------------------------
    # Z1: expected logistics cost
    z1_expr = solver.Sum(F_hub[ki] * x[ki] + C_hub[ki] * q[ki] for ki in range(num_H))

    for si, sc in enumerate(inst["scenarios"]):
        pi = sc["probability"]

        # Reactive hub setup cost (charged if y[ki,si] = 1)
        z1_expr += pi * solver.Sum(
            sc["hub_reactive_cost"][str(inst["nodes"]["hub_indices"][ki])] * y[ki, si]
            for ki in range(num_H)
        )

        # Origin-to-hub supply flow cost
        # Cost uses cheapest accessible mode per (j, k) pair in scenario s.
        for ji in range(num_J):
            j_node = inst["nodes"]["origin_indices"][ji]
            supply_j = float(sc["supply"][str(j_node)])
            for ki in range(num_H):
                k_node = inst["nodes"]["hub_indices"][ki]
                # Find cheapest accessible mode cost for this pair
                min_c = float('inf')
                any_acc = False
                for m in range(num_M):
                    if sc["accessibility"][m][j_node][k_node]:
                        c = inst["transport"]["cost"][m][j_node][k_node]
                        if c < min_c:
                            min_c = c
                        any_acc = True
                if any_acc:
                    # c_{jks} = min_m C_{jkm} (paper eq:obj1 comment for c_{jks})
                    z1_expr += pi * (min_c * supply_j * z_jks[ji, ki, si])

        # Inter-hub lateral transshipment cost (discounted by alpha)
        for ki in range(num_H):
            k_node = inst["nodes"]["hub_indices"][ki]
            for hi in range(num_H):
                h_node = inst["nodes"]["hub_indices"][hi]
                for m in range(num_M):
                    if sc["accessibility"][m][k_node][h_node]:
                        c_thm = inst["transport"]["cost"][m][k_node][h_node]
                        z1_expr += pi * (alpha * c_thm * f_khms[ki, hi, m, si])

        # Last-mile cost via pre-computed Daganzo CA theta[ki][ii][si]
        for ii in range(num_I):
            for ki in range(num_H):
                theta_val = inst["theta"][ki][ii][si]
                z1_expr += pi * (theta_val * z_iks[ii, ki, si])

        # Penalty for slack (unassigned demand/supply)
        z1_expr += pi * (sum(u_is[ii, si] for ii in range(num_I)) * big_M)
        z1_expr += pi * (sum(v_js[ji, si] for ji in range(num_J)) * big_M)

    # Z2: expected maximum deprivation cost
    z2_expr = solver.Sum(
        inst["scenarios"][si]["probability"] * z2_max_s[si]
        for si in range(num_S)
    )

    # Weighted-sum objective (w1 + w2 = 1)
    solver.Minimize(max(w1, 1e-7) * z1_expr + w2 * z2_expr)

    # Epsilon-constraint override (for exact Pareto front tracing)
    if eps_z2 is not None:
        solver.Add(z2_expr <= eps_z2)
        solver.Minimize(z1_expr)
    elif eps_z1 is not None:
        solver.Add(z1_expr <= eps_z1)
        solver.Minimize(z2_expr)

    # -------------------------------------------------------------------------
    # 4. Solve and extract results
    # -------------------------------------------------------------------------
    t0 = time.time()
    cpu0 = time.process_time()
    status = solver.Solve()
    elapsed = time.time() - t0
    cpu_elapsed = time.process_time() - cpu0

    if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
        X_res = [int(x[ki].solution_value() > 0.5) for ki in range(num_H)]
        # Inventory fill ratios
        R_res = [
            q[ki].solution_value() / K_hub[ki] if K_hub[ki] > 0 else 0.0
            for ki in range(num_H)
        ]
        # Total unassigned demand+supply (constraint violation count)
        CV_val = (
            sum(u_is[ii, si].solution_value() for ii in range(num_I) for si in range(num_S)) +
            sum(v_js[ji, si].solution_value() for ji in range(num_J) for si in range(num_S))
        )

        return {
            "status":    "OPTIMAL" if status == pywraplp.Solver.OPTIMAL else "FEASIBLE",
            "Z1":        z1_expr.solution_value(),
            "Z2":        z2_expr.solution_value(),
            "X":         X_res,
            "R":         R_res,
            "CV":        CV_val,
            "elapsed_s": elapsed,
            "cpu_time_s": cpu_elapsed,
        }
    else:
        print(f"Solver status: {status}")
        return {"status": "INFEASIBLE", "elapsed_s": time.time() - t0, "cpu_time_s": time.process_time() - cpu0}


def run_weighted_sum(inst, steps=1000, time_limit=600):
    """Run weighted-sum MILP. Iterates through weight combinations and returns non-dominated front."""
    if steps < 2:
        steps = 2

    front = []

    for i in range(steps):
        w1 = (steps - 1 - i) / (steps - 1)
        w2 = 1.0 - w1

        print(f"Solving weighted-sum {i+1}/{steps}: w1={w1:.3f}, w2={w2:.3f}")
        sol = build_and_solve_milp(inst, w1=w1, w2=w2, time_limit_s=time_limit)

        if sol and sol["status"] != "INFEASIBLE":
            print(f"  Result: Z1={sol['Z1']:.4f}, Z2={sol['Z2']:.4f}, "
                  f"CV={sol['CV']:.2f}, time={sol['elapsed_s']:.2f}s")
            front.append(sol)
        else:
            elapsed = sol.get("elapsed_s", "?") if sol else "?"
            print(f"  Weighted-sum {i+1} failed or infeasible (time={elapsed}s).")

    # Filter dominated solutions
    filtered = []
    for s1 in front:
        dominated = any(
            s2["Z1"] <= s1["Z1"] and s2["Z2"] <= s1["Z2"]
            and (s2["Z1"] < s1["Z1"] or s2["Z2"] < s1["Z2"])
            for s2 in front
        )
        if not dominated:
            filtered.append(s1)

    return filtered


def main():
    parser = argparse.ArgumentParser(description="MILP Baseline: MO-IHLNDP weighted-sum solver.")
    parser.add_argument("--instance",   required=True, help="Path to the JSON instance file.")
    parser.add_argument("--out",        required=True, help="Path to save results JSON.")
    parser.add_argument("--steps",      type=int, default=1000, help="Number of weighted-sum points.")
    parser.add_argument("--time_limit", type=int, default=600, help="Per-solve SCIP time limit (s).")
    args = parser.parse_args()

    inst = load_instance(args.instance)

    t_start = time.time()
    cpu_start = time.process_time()
    pareto  = run_weighted_sum(inst, steps=args.steps, time_limit=args.time_limit)
    t_total = time.time() - t_start
    cpu_total = time.process_time() - cpu_start

    per_solve_times = [s.get("elapsed_s", 0.0) for s in pareto]
    per_solve_cpu   = [s.get("cpu_time_s", 0.0) for s in pareto]

    out_data = {
        "meta": {
            "solver":           "MILP_WeightedSum_SCIP",
            "instance":         args.instance,
            "steps":            args.steps,
            "time_limit_s":     args.time_limit,
            "total_elapsed_s":  t_total,
            "total_cpu_s":      cpu_total,
            "per_solve_time_s": per_solve_times,
            "per_solve_cpu_s":  per_solve_cpu,
        },
        "pareto_front": pareto
    }

    with open(args.out, "w") as f:
        json.dump(out_data, f, indent=2)

    print(f"\nMILP Baseline finished.")
    print(f"  Pareto solutions found : {len(pareto)}")
    print(f"  Total wall-clock time  : {t_total:.2f}s")
    print(f"  Results saved to       : {args.out}")


if __name__ == "__main__":
    main()



\section{Problem Description and Mathematical Model}

We model the network design problem as a capacitated, single-allocation MO-IHLNDP. The network comprises \textbf{origins} (supply sources), \textbf{demands} (victim groups), and \textbf{hubs} of two types: planned (pre-disaster) and reactive (post-disaster, dynamically opened).

From a practical standpoint, DRND involves two critical uncertainty factors. First, infrastructure disruption -- damaged roads and buildings -- can disable pre-programmed plans, urging the need for a dynamic solution~\cite{Yahyaei2019}. Second, the exact locations of demands, the total number of victims, and the availability of origins are all highly uncertain during rescue operations~\cite{tofighi2016humanitarian}. To account for these, we employ a two-stage stochastic programming approach across multiple scenarios, each assigning a specific risk factor per area, and assume that Search and Rescue operations rely heavily on dynamic external supply sources, as pre-positioned hubs may not fully satisfy uncertain demands under extreme scenarios.

The model integrates the deprivation cost~\cite{holguin2013appropriate} for social equity, and Daganzo's continuous approximation (CA)~\cite{daganzo2005logistics} to tractably estimate last-mile rescue times.

\subsection{Sets and Indices}
\noindent
\begin{tabular}{l p{0.85\textwidth}}
$\mathcal{H}, \mathcal{I}, \mathcal{J}$ & Set of candidate hubs ($k, h$), demand nodes ($i$), and  origins ($j$) \\
$\mathcal{S}, \mathcal{M}$ & Set of disaster scenarios ($s$) and transportation modes ($m$) \\
$\mathcal{V}$ & Set of all nodes ($u,v$) representing the area in question, $\mathcal{V} = \mathcal{H} \cup \mathcal{I} \cup \mathcal{J}$ \\
\end{tabular}

\subsection{Parameters}

\noindent \textbf{First-Phase Parameters (Strategic Planning)} \\
\begin{tabular}{l p{0.85\textwidth}}
$F_k$ & Fixed cost to establish hub $k$ of the first type (before the disaster) \\
$c_k, \kappa_k$ & Unit holding cost and capacity limit for inventory at hub $k$ \\
$\alpha, \chi, M$ & Discount factor for economies of scale, max acceptable risk threshold, and Big-M constant \\
$C_{uvm}, \tau_{uvm}$ & Unit transportation cost and estimated travel time from node $u$ to $v$ via mode $m$ \\
$C_m, Q_m$ & Unit local routing cost and transportation capacity for vehicle mode $m$ \\
$\gamma$ & Conversion factor (average amount of relief items required per evacuated person) \\
\end{tabular}

% \vspace{0.2cm}
\noindent \textbf{Second-Phase Parameters (Disaster Response, Scenario $s$)} \\
\begin{tabular}{l p{0.85\textwidth}}
$\pi_s$ & Probability of scenario $s$ \\
$F_{ks}^{a}$ & Fixed cost to establish hub $k$ of the second type (reactive) in scenario $s$ \\
$\tau_{ks}$ & Processing time for each rescue round trip at hub $k$ in scenario $s$ \\
$a_{uvms}$ & Accessibility of arc $(u,v)$ via mode $m$ in scenario $s$ (1 if traversable, 0 otherwise) \\
$r_{us}, \lambda_{is}$ & Risk index of node $u$, and deprivation sensitivity coefficient for demand $i$ in scenario $s$ \\
$D_{is}, O_{js}$ & Demand (number of people to evacuate) at $i$, and relief items provided at origin $j$ in scenario $s$ \\
$c_{jks}$             & Pre-computed cheapest transport cost from origin $j$ to hub $k$ in scenario $s$:
                        $c_{jks} = \min_{m \in \mathcal{M} \mid a_{jkms}=1} C_{jkm}$, ($+\infty$ if no available mode) \\
$\Theta_{kis}$ & Pre-computed CA routing cost to execute the evacuation from grid $i$ to hub $k$ in scenario $s$ \\
$\Phi, \eta, A_i$ & Daganzo's circuity factor, average group size per distress location, and area of grid cell $i$ \\
\end{tabular}

\subsection{Decision Variables}
\noindent
\begin{tabular}{l p{0.85\textwidth}}
$x_{k} \in \{0,1\}$ & 1 if hub $k$ is established as the first type (planned), 0 otherwise \\
$y_{ks} \in \{0,1\}$ & 1 if hub $k$ is established as the second type (reactive) in scenario $s$, 0 otherwise \\
$z_{iks} \in \{0,1\}$ & 1 if demand $i$ is assigned to be evacuated to hub $k$ in scenario $s$, 0 otherwise \\
$z_{jks} \in \{0,1\}$ & 1 if origin $j$ supplies hub $k$ in scenario $s$, 0 otherwise \\
$q_{k}$ & Amount of relief items inventoried at hub $k$ \\
$f_{khms}$ & Lateral trans-shipment flow volume from hub $k$ to hub $h$ via mode $m$ in scenario $s$ \\
\end{tabular}

\subsection{Objectives}
\textbf{Objective 1: Minimize Total Expected Logistics Cost ($Z_1$)}

\begin{equation} \label{eq:obj1}
\begin{aligned}
    \text{Min } Z_1 = & \underbrace{\sum_{k \in \mathcal{H}} F_k x_k + \sum_{k \in \mathcal{H}} c_k q_k}_{\text{Pre-disaster strategic costs}} \\
    & + \sum_{s \in \mathcal{S}} \pi_s \Bigg[ \underbrace{\sum_{k \in \mathcal{H}} F_{ks}^a y_{ks}}_{\text{Reactive setup}} 
    + \underbrace{\sum_{j \in \mathcal{J}} \sum_{k \in \mathcal{H}} c_{jks} \cdot O_{js} z_{jks}}_{\text{Origin to Hub supply flow}} \\
    % + \underbrace{\sum_{j \in \mathcal{J}} \sum_{k \in \mathcal{H}} \left( \min_{m \in \mathcal{M} \mid a_{jkms}=1} C_{jkm} \right) O_{js} z_{jks}}_{\text{Origin to Hub supply flow}} \\
    % + \underbrace{\sum_{j \in \mathcal{J}} \sum_{k \in \mathcal{H}} \sum_{m \in \mathcal{M}} C_{jkm} O_{js} z_{jks}}_{\text{Origin to Hub supply flow}} \\
    & + \underbrace{\sum_{k \in \mathcal{H}} \sum_{h \in \mathcal{H}} \sum_{m \in \mathcal{M}} \alpha C_{khm} f_{khms}}_{\text{Inter-hub lateral trans-shipment}} 
    + \underbrace{\sum_{k \in \mathcal{H}} \sum_{i \in \mathcal{I}} \Theta_{kis} z_{iks}}_{\text{Grid-based Last-Mile CA}} 
    \Bigg]
\end{aligned}
\end{equation}

Objective $Z_1$ minimizes total expected logistics cost. Using the previously mentioned CA \cite{daganzo2005logistics}, demands are aggregated on a grid basis to pre-compute the last-mile routing cost $\Theta_{kis}$. The first term is line-haul cost from hub $k$ to demand $i$, and the second term is local detour cost inside area $i$:
% Cheapest transportation mode is considered
\begin{equation*} \label{eq:daganzo_theta}
    \Theta_{kis} = \min_{m \in \mathcal{M}  \mid a_{ikms}=1} \left( 2 \cdot C_{kim} \cdot \lceil D_{is}/Q_m \rceil + C_{m} \cdot \Phi \sqrt{\lceil D_{is}/\eta \rceil \cdot A_i} \right)
\end{equation*}

\textbf{Objective 2: Minimize Expected Maximum Deprivation Cost ($Z_2$)}

% Formula: max (s over S) (sum i over I) IS CHANGED TO avg (s over S) (max i over I)
% \begin{equation} \label{eq:obj2}
% \text{Min } Z_2 = \max_{s \in \mathcal{S}} \left( \sum_{i \in \mathcal{I}} D_{is} \cdot \left( e^{\lambda_{is} \cdot \Omega_{is}} - 1 \right) \right)`
% \end{equation}

\begin{equation} \label{eq:obj2}
    \text{Min } Z_2 = \sum_{s \in \mathcal{S}} \pi_s \left( \max_{i \in \mathcal{I}} \left[ D_{is} \cdot \left( e^{\lambda_{is} \cdot \Omega_{is}} - 1 \right) \right] \right)
\end{equation}

\begin{equation*} \label{eq:waiting_time}
\Omega_{is} = \sum_{k \in \mathcal{H}} z_{iks} \left( \tau_{ks} + 2 \cdot \min_{m \in \mathcal{M}  \mid a_{ikms}=1} \tau_{kim} \right)
\end{equation*}

Objective $Z_2$ minimizes the expected value of maximum deprivation cost \cite{holguin2013appropriate}. The exponential function of waiting time $\Omega_{is}$ heavily penalizes the model if it lets a demand node wait slightly longer than the rest, forcing the model to distribute resources evenly. The penalty function is adjusted by $\lambda_{is} = \lambda_0 (1 + r_{is})$ so that highly vulnerable populations are prioritized. 

To linearize $Z_2$, we exploit the single-allocation property \eqref{eq:single_alloc_demand}. Any demand $i$ is allocated to a single hub $k$. Thus, the deprivation cost $C^{\text{dep}}_{is}$ is pre-computed:

\begin{equation} \label{eq:deprivation_cost}
    C^{\text{dep}}_{is} = D_{is} \cdot \left(e^{\lambda_{is} \cdot \left(\tau_{ks} + 2 \cdot \min_{m \in \mathcal{M} \mid a_{ikms}=1} \tau_{kim}\right)} - 1\right)
\end{equation}

By introducing a continuous auxiliary variable $W_s \ge 0$ and constraint \eqref{eq:deprivation_bound} to capture the worst-case deprivation cost among all demand nodes in a given scenario $s$, we obtain the linearized program:

\begin{align}
    \text{Minimize } \quad & Z_1, Z_2^{\text{linear}} = \sum_{s \in \mathcal{S}} \pi_s \cdot W_s   \nonumber \\
    \text{subject to} \quad & \text{Constraints } \eqref{eq:deprivation_bound} - \eqref{eq:nonneg_vars} \nonumber \\
    W_s & \ge C^{\text{dep}}_{is} \cdot z_{iks} \quad \forall i \in \mathcal{I}, s \in \mathcal{S} \label{eq:deprivation_bound}
\end{align}

\subsection{Constraints}

The original, complete MO-IHLNDP model is formally stated as follows:

\allowdisplaybreaks
\begin{align}
    \text{Minimize } \quad & Z_1, Z_2 \nonumber \\
    \text{subject to} \quad & \text{Constraints } \eqref{eq:hub_type} - \eqref{eq:nonneg_vars} \nonumber \\
    x_k + y_{ks} & \le 1 \quad \forall k \in \mathcal{H}, s \in \mathcal{S} \label{eq:hub_type} \\
    q_k & \le \kappa_k \cdot x_k \quad \forall k \in \mathcal{H} \label{eq:hub_inv_cap} \\
    r_{ks} \cdot (x_k + y_{ks}) & \le \chi \quad \forall k \in \mathcal{H}, s \in \mathcal{S} \label{eq:hub_safety} \\
    \sum_{k \in \mathcal{H}} z_{iks} & = 1 \quad \forall i \in \mathcal{I}, s \in \mathcal{S} \label{eq:single_alloc_demand} \\
    \sum_{k \in \mathcal{H}} z_{jks} & = 1 \quad \forall j \in \mathcal{J}, s \in \mathcal{S} \label{eq:single_alloc_origin} \\
    z_{iks} & \le x_k + y_{ks} \quad \forall i \in \mathcal{I}, k \in \mathcal{H}, s \in \mathcal{S} \label{eq:valid_assign_demand} \\
    z_{jks} & \le x_k + y_{ks} \quad \forall j \in \mathcal{J}, k \in \mathcal{H}, s \in \mathcal{S} \label{eq:valid_assign_origin} \\
    z_{iks} & \le \sum_{m \in \mathcal{M}} a_{ikms} \quad \forall i \in \mathcal{I}, k \in \mathcal{H}, s \in \mathcal{S} \label{eq:path_demand} \\
    z_{jks} & \le \sum_{m \in \mathcal{M}} a_{jkms} \quad \forall j \in \mathcal{J}, k \in \mathcal{H}, s \in \mathcal{S} \label{eq:path_origin} \\
    f_{khms} & \le M \cdot a_{khms} \quad \forall k, h \in \mathcal{H},\; m \in \mathcal{M},\; s \in \mathcal{S} \label{eq:trans_path} \\
    % \sum_{i \in \mathcal{I}} \gamma D_{is} z_{iks} + \sum_{h \in \mathcal{H}} \sum_{m \in \mathcal{M}} f_{khms} & \le q_k + \sum_{j \in \mathcal{J}} O_{js} z_{jks} + \sum_{h \in \mathcal{H}} \sum_{m \in \mathcal{M}} f_{hkms} \quad \forall k \in \mathcal{H}, s \in \mathcal{S} \label{eq:flow_balance} \\
    \begin{split}
        \sum_{i \in \mathcal{I}} \gamma D_{is} z_{iks} + \sum_{h \in \mathcal{H}} \sum_{m \in \mathcal{M}} f_{khms} & \le q_k + \sum_{j \in \mathcal{J}} O_{js} z_{jks} \\
        & \quad + \sum_{h \in \mathcal{H}} \sum_{m \in \mathcal{M}} f_{hkms} \quad \forall k \in \mathcal{H}, s \in \mathcal{S} 
    \end{split} \label{eq:flow_balance} \\
    q_k + \sum_{j \in \mathcal{J}} O_{js} z_{jks} + \sum_{h \in \mathcal{H}} \sum_{m \in \mathcal{M}} f_{hkms} & \le \kappa_k \cdot (x_k + y_{ks}) \quad \forall k \in \mathcal{H}, s \in \mathcal{S} \label{eq:throughput_cap} \\
    x_k, y_{ks}, z_{iks}, z_{jks} & \in \{0, 1\} \quad \forall i, j, k, s \label{eq:binary_vars} \\
    q_k, f_{khms}, W_s & \ge 0 \quad \forall k, h, m, s \label{eq:nonneg_vars}
\end{align}

Constraints \eqref{eq:hub_type} define the hub establishment. For planned hubs, inventory is bounded by physical capacity \eqref{eq:hub_inv_cap}, while reactive hubs are required to be placed within safe zones \eqref{eq:hub_safety}.
Constraints \eqref{eq:single_alloc_demand}-\eqref{eq:path_origin} enforce the single-allocation property to active hubs via available links. 
Constraint \eqref{eq:trans_path} restricts flow to be trans-shipped on intact paths. 
Constraints \eqref{eq:flow_balance} and \eqref{eq:throughput_cap} maintain flow conservation and capacity limits. Specifically, \eqref{eq:flow_balance} ensures that total supply, comprising inventory ($q_k$), external origins ($O_{js}$), and incoming flows -- satisfies both victim demand (converted by $\gamma$) and outgoing trans-shipments. Variable domains are defined in \eqref{eq:binary_vars}-\eqref{eq:nonneg_vars}.

% ============================================================