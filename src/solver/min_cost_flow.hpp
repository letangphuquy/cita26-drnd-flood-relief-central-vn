// min_cost_flow.hpp — lightweight min-cost max-flow utilities for decoder
#pragma once

#include "template.hpp"

#include <limits>
#include <queue>

struct MCFEdge {
  int to;
  int rev;
  double cap;
  double init_cap;
  double cost;
  int kind; // 0=other, 1=origin->hub, 2=hub->hub
  int src_idx;
  int dst_idx;
  int mode;
};

static inline void mcf_add_edge(vector<vector<MCFEdge>> &g, int u, int v,
                                double cap, double cost, int kind = 0,
                                int src_idx = -1, int dst_idx = -1,
                                int mode = -1) {
  MCFEdge a{v, (int)g[v].size(), cap, cap, cost, kind, src_idx, dst_idx, mode};
  MCFEdge b{u, (int)g[u].size(), 0.0, 0.0, -cost, 0, -1, -1, -1};
  g[u].push_back(a);
  g[v].push_back(b);
}

static inline double min_cost_flow(vector<vector<MCFEdge>> &g, int s, int t,
                                   double max_flow) {
  const int N = (int)g.size();
  const double INF = std::numeric_limits<double>::infinity();
  vector<double> potential(N, 0.0), dist(N, INF);
  vector<int> pv(N, -1), pe(N, -1);
  double flow = 0.0, cost = 0.0;

  while (flow + EPS < max_flow) {
    std::fill(dist.begin(), dist.end(), INF);
    std::fill(pv.begin(), pv.end(), -1);
    std::fill(pe.begin(), pe.end(), -1);
    dist[s] = 0.0;

    using PQ = pair<double, int>;
    std::priority_queue<PQ, vector<PQ>, std::greater<PQ>> pq;
    pq.push({0.0, s});

    while (!pq.empty()) {
      auto [d, u] = pq.top();
      pq.pop();
      if (d > dist[u] + 1e-12)
        continue;
      for (int ei = 0; ei < (int)g[u].size(); ei++) {
        const auto &e = g[u][ei];
        if (e.cap <= EPS)
          continue;
        double rc = e.cost + potential[u] - potential[e.to];
        double nd = d + rc;
        if (nd + 1e-12 < dist[e.to]) {
          dist[e.to] = nd;
          pv[e.to] = u;
          pe[e.to] = ei;
          pq.push({nd, e.to});
        }
      }
    }

    if (pv[t] == -1)
      break;

    for (int v = 0; v < N; v++)
      if (dist[v] < INF / 2)
        potential[v] += dist[v];

    double addf = max_flow - flow;
    for (int v = t; v != s; v = pv[v]) {
      const auto &e = g[pv[v]][pe[v]];
      addf = std::min(addf, e.cap);
    }

    for (int v = t; v != s; v = pv[v]) {
      auto &e = g[pv[v]][pe[v]];
      auto &r = g[e.to][e.rev];
      e.cap -= addf;
      r.cap += addf;
      cost += addf * e.cost;
    }
    flow += addf;
  }

  return cost;
}
