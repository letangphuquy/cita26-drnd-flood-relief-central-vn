// template.hpp — Utility library for PB-NSGA-II solver
// Copied from intern/project-hlp-rail/template.hpp with minor adjustments
// (removed Boost dependency: binstr/dynamic_bitset not needed here)
#pragma once

#include <algorithm>
#include <chrono>
#include <cmath>
#include <functional>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <string>
#include <utility>
#include <vector>


using std::vector, std::cin, std::cout, std::cerr, std::string, std::pair;

#define all(v) (v).begin(), (v).end()
#define cst(T) const T &

typedef long long Int;
typedef double Real;
const Real EPS = 1e-9;

template <class A, class B> bool umin(A &var, cst(B) val) {
  return (val < var) ? (var = val, true) : false;
}
template <class A, class B> bool umax(A &var, cst(B) val) {
  return (var < val) ? (var = val, true) : false;
}

// ── RNG ─────────────────────────────────────────────────────────────────────
std::mt19937 rng(std::chrono::steady_clock::now().time_since_epoch().count());
const Int SEED_BASE = 0xAC152004;

void set_rolling_seed(int iter = 0) {
  Int seed = SEED_BASE;
  for (int i = 0; i < iter; i++)
    seed = (seed * 48271LL) % 0x7fffffff;
  rng.seed((unsigned int)seed);
}

template <class X, class Y> Int rand_int(const X &l, const Y &r) {
  return std::uniform_int_distribution<Int>((Int)l, (Int)r)(rng);
}
Real rand01() { return std::uniform_real_distribution<Real>(0.0, 1.0)(rng); }
Real rand_real(Real l, Real r) {
  return std::uniform_real_distribution<Real>(l, r)(rng);
}
// Gaussian noise N(0, sigma)
Real rand_gauss(Real sigma = 1.0) {
  return std::normal_distribution<Real>(0.0, sigma)(rng);
}

template <typename T> T &sample_ref(vector<T> &v) {
  return v[rand_int(0, (int)v.size() - 1)];
}
template <typename T> const T &sample(const vector<T> &v) {
  return v[rand_int(0, (int)v.size() - 1)];
}
template <typename T> T sample_pop(vector<T> &v) {
  int idx = (int)rand_int(0, (int)v.size() - 1);
  T item = v[idx];
  std::swap(v[idx], v.back());
  v.pop_back();
  return item;
}
template <typename T> void shuffle_vec(vector<T> &v) {
  std::shuffle(v.begin(), v.end(), rng);
}

// ── Timing / Benchmarking ───────────────────────────────────────────────────
typedef std::chrono::high_resolution_clock::time_point TimeVar;
#define time_now() std::chrono::high_resolution_clock::now()
#define duration_ms(a)                                                         \
  (std::chrono::duration_cast<std::chrono::microseconds>(a).count() / 1000.0)

void log_time(const string &label, TimeVar t_start) {
  double ms = duration_ms(time_now() - t_start);
  cerr << std::fixed << std::setprecision(2) << "[" << label << "] " << ms
       << " ms\n";
}

// ── Misc ─────────────────────────────────────────────────────────────────────
const Real PI_CONST = acos(-1.0);
const Real INF_VAL = 1e18;
