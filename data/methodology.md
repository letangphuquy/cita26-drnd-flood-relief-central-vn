# Data Generation Methodology
## MO-IHLNDP: Central Vietnam Disaster Relief Network Design

### 1. Instance Sizes

| Parameter | Small | Large |
|-----------|-------|-------|
| Demand nodes \|I\| | 20 | 100 |
| Hub candidates \|H\| | 5 | 20 |
| Origins \|J\| | 2 | 12 |
| Scenarios \|S\| | 3 | 3 |
| Transport modes \|M\| | 3 | 3 |

**Rationale:** The small instance is suitable for rapid experimentation and illustration; the large instance captures realistic scale for Central Vietnam's administration district structure.

---

### 2. Node Coordinates
All coordinates are real geographic locations hand-curated from flood risk literature, OpenStreetMap, and Vietnamese government disaster management reports, covering the Vu Gia – Thu Bồn river basin (Đà Nẵng / Quảng Nam / Thừa Thiên Huế province cluster).

- **Demand nodes:** Flood-prone communes and urban wards (coastal to mountain)
- **Hub candidates:** Elevated, safe positions: airports, logistics facilities, military bases, elevated rescue stations
- **Origins:** External supply entry points: seaports, mountain passes (Hải Vân), military airports (Chu Lai), rail stations

---

### 3. Transportation Modes

| Mode | Vehicle | Speed (km/h) | Unit Cost ($/km) | Capacity | Disruption |
|------|---------|-------------|-----------------|----------|------------|
| 0: Road | Truck convoy | 40 | 5 × terrain_factor | 50 persons | Disrupted by flooding |
| 1: Water | Motorized boat | 15 | 12 × minor_tf | 30 persons | Resilient, always available |
| 2: Air | Helicopter | 180 | 80 × moderate_tf | 15 persons | Always available |

**Terrain factor:** `tf(lon) = 1.0 + 0.8 × (1 - (lon - 107.0)/1.8)` — coastal areas (lon≈108.2) have tf≈1.0, deep mountain interior (lon≈107.0) has tf≈1.8. Adjustment: road fully affected, water minimally, air moderately.

**Road distances:** OSRM table API (real routing), falling back to Haversine × 1.3 tortuosity.

---

### 4. Disaster Scenarios

| Scenario | Probability (π_s) | Epicenters | σ (km) | Road Disruption β | Severity Multiplier |
|----------|------------------|-----------|--------|-------------------|---------------------|
| S1: Mild | 0.60 | 1 | 50 | 0.20 | 1.0× |
| S2: Severe | 0.30 | 2 | 35 | 0.55 | 1.6× |
| S3: Extreme | 0.10 | 3 | 25 | 0.90 | 2.5× |

**Probability rationale:** Based on Vietnamese flood occurrence statistics (VNMHA 2020–2024): minor floods ≈60%, major floods ≈30%, catastrophic events ≈10%.

---

### 5. Risk Index Model
$$r_{is} = \text{clip}\left(\text{Base\_Risk} + \sum_{E \in \mathcal{E}_s} I_E \cdot \exp\!\left(-\frac{d(i,E)^2}{2\sigma^2}\right),\ 0,\ 1\right)$$

- **Base risk = 0.08:** Minimum background risk even in mild scenario
- **Epicenter positions:** Sampled randomly from node set per scenario
- **Hub safety constraint:** Hub k is eligible for activation iff `r_ks ≤ χ = 0.7`

---

### 6. Demand Model
$$D_{is} = \text{BasePop}_i \times (0.1 + 0.9 \cdot r_{is}) \times \text{SeverityMult}_s + \mathcal{N}(0, 0.05 D_{is})$$

- **Base population:** Proportional to coastal proximity and flow centrality (500–5000 persons)
- **Noise:** 5% Gaussian perturbation for realism

---

### 7. Forecasted Demand for Inventory (q_k)
The inventory ratio `R_k` in the chromosome encodes `q_k = R_k × κ_k`. The total forecasted demand is not known exactly pre-disaster; the chromosome implicitly samples from a right-skewed distribution ranging 0–1 of hub capacity. This captures the stochastic nature without requiring explicit demand forecasting.

---

### 8. Daganzo CA Routing Cost (Θ_{kis})
$$\Theta_{kis} = \min_{m \in \mathcal{M}: a_{ikms}=1} \left( 2 C_{kim} \left\lceil \frac{D_{is}}{Q_m} \right\rceil + C_m \cdot \Phi \sqrt{\left\lceil \frac{D_{is}}{\eta} \right\rceil \cdot A_i} \right)$$

| Parameter | Value | Justification |
|-----------|-------|---------------|
| Φ (circuity factor) | 0.57 | Daganzo (2005) standard for planar networks |
| η (group size) | 5 persons | Average rescue team load per stop |
| A_i (cell area) | 8–40 km² | Administrative division area |
| C_m (local routing cost) | 2.5 $/km | Standardized operational cost coefficient |

If all modes are blocked for a (k, i, s) triple: `Θ_kis = BIG-M = 10^9` (forces infeasible flag).

---

### 9. Benchmark Dataset Extension (AP / TR)
AP Euclidean instances and the Turkish 81-city network are extended with synthetically generated DRND parameters using the same methodology:
- Hub candidates: top nodes by total flow centrality
- Risk/accessibility: same epicenter model, but using Euclidean distance units
- Demand: proportional to incoming flow
- Daganzo Θ: computed from Euclidean distance matrix
