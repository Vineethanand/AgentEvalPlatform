// Statistics for comparing two configs. Pure functions, no I/O, unit-tested in stats.spec.ts.
//
// Method (see docs/design.md, "Statistical method"):
//  - Headline: difference in pass rate (B - A), every task weighted equally.
//  - 95% confidence interval: paired bootstrap. Resample TASKS (keeping A and B together),
//    then resample trials inside each task. Tasks are resampled first because the N trials of
//    one task are related; treating them as independent would make us overconfident.
//  - Cross-check: exact McNemar test on one majority outcome per task.

export interface PairedCell {
  taskId: string;
  a: number[]; // per-trial values for config A (0/1 for pass, or a cost etc.)
  b: number[]; // per-trial values for config B
}

export type Verdict = 'B better' | 'A better' | 'no clear difference';

/** Small deterministic PRNG so results are reproducible for a given seed. */
export function mulberry32(seed: number): () => number {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

export const mean = (xs: number[]): number => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : NaN);

function percentile(sorted: number[], p: number): number {
  if (!sorted.length) return NaN;
  const idx = (sorted.length - 1) * p;
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

/** Difference of task-averaged means: mean over tasks of (mean(b) - mean(a)). */
export function pairedDelta(cells: PairedCell[]): number {
  return mean(cells.map((c) => mean(c.b) - mean(c.a)));
}

export interface BootstrapResult {
  delta: number;
  lo: number;
  hi: number;
  p: number; // two-sided bootstrap p-value (share of resamples on the other side of 0, doubled)
  resamples: number;
}

/** Two-level paired bootstrap: tasks first, then trials within each task. */
export function pairedBootstrap(cells: PairedCell[], resamples = 10000, seed = 1234): BootstrapResult {
  const usable = cells.filter((c) => c.a.length > 0 && c.b.length > 0);
  const delta = pairedDelta(usable);
  if (usable.length === 0) return { delta: NaN, lo: NaN, hi: NaN, p: NaN, resamples: 0 };
  const rnd = mulberry32(seed);
  const pick = <T>(xs: T[]): T => xs[Math.floor(rnd() * xs.length)];
  const draws: number[] = new Array(resamples);
  for (let r = 0; r < resamples; r++) {
    let sum = 0;
    for (let t = 0; t < usable.length; t++) {
      const cell = pick(usable); // level 1: a task, with its A and B results together
      let sa = 0;
      let sb = 0;
      for (let i = 0; i < cell.a.length; i++) sa += pick(cell.a); // level 2: trials
      for (let i = 0; i < cell.b.length; i++) sb += pick(cell.b);
      sum += sb / cell.b.length - sa / cell.a.length;
    }
    draws[r] = sum / usable.length;
  }
  draws.sort((x, y) => x - y);
  const below = draws.filter((d) => d <= 0).length / resamples;
  const above = draws.filter((d) => d >= 0).length / resamples;
  return {
    delta,
    lo: percentile(draws, 0.025),
    hi: percentile(draws, 0.975),
    p: Math.min(1, 2 * Math.min(below, above)),
    resamples,
  };
}

/** log of n choose k */
function logChoose(n: number, k: number): number {
  let s = 0;
  for (let i = 1; i <= k; i++) s += Math.log(n - k + i) - Math.log(i);
  return s;
}

/** Exact two-sided binomial test with p = 0.5. */
export function binomTwoSided(k: number, n: number): number {
  if (n === 0) return 1;
  const probs = Array.from({ length: n + 1 }, (_, i) => Math.exp(logChoose(n, i) - n * Math.LN2));
  const pk = probs[k];
  const p = probs.filter((q) => q <= pk * (1 + 1e-7)).reduce((s, q) => s + q, 0);
  return Math.min(1, p);
}

export interface McNemarResult {
  bothPass: number;
  onlyA: number;
  onlyB: number;
  neither: number;
  p: number;
}

/** Exact McNemar on one outcome per task: a config "passes" a task if it passed most of its trials. */
export function mcnemarByTask(cells: PairedCell[]): McNemarResult {
  let bothPass = 0, onlyA = 0, onlyB = 0, neither = 0;
  for (const c of cells) {
    if (!c.a.length || !c.b.length) continue;
    const pa = mean(c.a) > 0.5;
    const pb = mean(c.b) > 0.5;
    if (pa && pb) bothPass++;
    else if (pa) onlyA++;
    else if (pb) onlyB++;
    else neither++;
  }
  return { bothPass, onlyA, onlyB, neither, p: binomTwoSided(onlyB, onlyA + onlyB) };
}

/** Fisher exact test (two-sided) for a 2x2 table [[a, b], [c, d]]. Used per task. */
export function fisherExact(a: number, b: number, c: number, d: number): number {
  const r1 = a + b, r2 = c + d, c1 = a + c, n = r1 + r2;
  const logP = (x: number) => logChoose(r1, x) + logChoose(r2, c1 - x) - logChoose(n, c1);
  const lo = Math.max(0, c1 - r2), hi = Math.min(r1, c1);
  const pObs = Math.exp(logP(a));
  let p = 0;
  for (let x = lo; x <= hi; x++) {
    const px = Math.exp(logP(x));
    if (px <= pObs * (1 + 1e-7)) p += px;
  }
  return Math.min(1, p);
}

export function verdictFromCI(lo: number, hi: number): Verdict {
  if (lo > 0) return 'B better';
  if (hi < 0) return 'A better';
  return 'no clear difference';
}

export interface PerTaskRow {
  taskId: string;
  passA: number;
  nA: number;
  passB: number;
  nB: number;
  delta: number;
  p: number;
  label: 'significant' | 'noise';
}

export function perTask(cells: PairedCell[]): PerTaskRow[] {
  return cells.map((c): PerTaskRow => {
    const passA = c.a.reduce((s, x) => s + x, 0);
    const passB = c.b.reduce((s, x) => s + x, 0);
    const p = fisherExact(passB, c.b.length - passB, passA, c.a.length - passA);
    return {
      taskId: c.taskId,
      passA, nA: c.a.length, passB, nB: c.b.length,
      delta: mean(c.b) - mean(c.a),
      p,
      label: p < 0.05 ? 'significant' : 'noise',
    };
  }).sort((x, y) => y.delta - x.delta);
}
