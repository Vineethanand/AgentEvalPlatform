import {
  binomTwoSided, fisherExact, mcnemarByTask, mulberry32, pairedBootstrap, PairedCell, verdictFromCI,
} from './stats';

// The worked example from the design discussion: 8 tasks x 5 trials.
const example: PairedCell[] = [
  { taskId: 'csv-aggregate', a: [1, 1, 1, 1, 1], b: [1, 1, 1, 1, 1] },
  { taskId: 'py-fix-bug', a: [1, 1, 0, 1, 1], b: [1, 1, 1, 0, 1] },
  { taskId: 'log-triage', a: [1, 0, 1, 0, 1], b: [1, 1, 1, 0, 1] },
  { taskId: 'unanswerable', a: [0, 1, 0, 1, 0], b: [0, 0, 1, 0, 0] },
  { taskId: 'invoice', a: [0, 0, 1, 0, 0], b: [0, 1, 0, 0, 0] },
  { taskId: 'm1', a: [0, 0, 0, 0, 0], b: [1, 1, 0, 1, 1] },
  { taskId: 'm2', a: [0, 0, 1, 0, 0], b: [1, 1, 1, 1, 1] },
  { taskId: 'postmortem', a: [1, 0, 1, 1, 0], b: [0, 1, 1, 1, 0] },
];

describe('stats', () => {
  it('binomial test matches scipy', () => {
    expect(binomTwoSided(9, 10)).toBeCloseTo(0.021484, 5);
    expect(binomTwoSided(2, 2)).toBeCloseTo(0.5, 6);
    expect(binomTwoSided(0, 0)).toBe(1);
  });

  it('fisher exact matches scipy', () => {
    expect(fisherExact(1, 9, 7, 3)).toBeCloseTo(0.019767, 5);
    expect(fisherExact(4, 1, 0, 5)).toBeCloseTo(0.047619, 5);
  });

  it('McNemar on the worked example: 2 vs 0 discordant tasks, p = 0.5', () => {
    const m = mcnemarByTask(example);
    expect([m.bothPass, m.onlyA, m.onlyB, m.neither]).toEqual([4, 0, 2, 2]);
    expect(m.p).toBeCloseTo(0.5, 6);
  });

  it('bootstrap on the worked example: +20 points, CI crosses zero', () => {
    const r = pairedBootstrap(example, 5000, 1);
    expect(r.delta).toBeCloseTo(0.2, 6);
    expect(r.lo).toBeLessThan(0);
    expect(r.hi).toBeGreaterThan(0.3);
    expect(verdictFromCI(r.lo, r.hi)).toBe('no clear difference');
  });

  it('a large consistent effect is detected', () => {
    const cells: PairedCell[] = Array.from({ length: 20 }, (_, i) => ({
      taskId: `t${i}`, a: [0, 0, 0, 1, 0, 0, 0, 0, 1, 0], b: [1, 1, 1, 0, 1, 1, 1, 1, 1, 1],
    }));
    const r = pairedBootstrap(cells, 2000, 2);
    expect(verdictFromCI(r.lo, r.hi)).toBe('B better');
  });

  it('A/A calibration: false "better" rate stays near 5%', () => {
    const rnd = mulberry32(99);
    let falsePositives = 0;
    const runs = 200;
    for (let k = 0; k < runs; k++) {
      const cells: PairedCell[] = Array.from({ length: 24 }, (_, i) => {
        const p = (i + 1) / 26; // tasks of varying difficulty, identical for A and B
        const draw = () => Array.from({ length: 10 }, () => (rnd() < p ? 1 : 0));
        return { taskId: `t${i}`, a: draw(), b: draw() };
      });
      const r = pairedBootstrap(cells, 400, k + 1);
      if (verdictFromCI(r.lo, r.hi) !== 'no clear difference') falsePositives++;
    }
    expect(falsePositives / runs).toBeLessThan(0.12);
  });
});
