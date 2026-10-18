import {
  BadRequestException, Body, Controller, Get, Injectable, NotFoundException, OnModuleDestroy, Param, Post, Query, Res,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Queue } from 'bullmq';
import IORedis from 'ioredis';
import { In, Repository } from 'typeorm';
import type { Response } from 'express';
import { ConfigVersion, Experiment, Grade, Task, TaskVersion, TraceEvent, Trial } from './entities';
import {
  mcnemarByTask, mean, pairedBootstrap, PairedCell, perTask, verdictFromCI,
} from './stats';

export const TRIAL_QUEUE = 'trials';

/** One queue job = one or more trials run in order (a memory chain runs as one job). */
export interface TrialJob {
  experimentId: string;
  trialIds: string[];
}

@Injectable()
export class QueueService implements OnModuleDestroy {
  private conn = new IORedis(process.env.REDIS_URL ?? 'redis://localhost:6379', { maxRetriesPerRequest: null });
  readonly queue = new Queue<TrialJob>(TRIAL_QUEUE, { connection: this.conn });

  async enqueue(jobs: TrialJob[]) {
    await this.queue.addBulk(jobs.map((data) => ({
      name: 'run',
      data,
      opts: {
        attempts: 2,                                   // one retry if a worker dies or the harness crashes
        backoff: { type: 'exponential', delay: 5000 },
        removeOnComplete: 1000,
        removeOnFail: 1000,
      },
    })));
  }

  async onModuleDestroy() {
    await this.queue.close();
    this.conn.disconnect();
  }
}

export interface CreateExperimentBody {
  name: string;
  hypothesis?: string;
  taskIds?: string[];            // latest version of each; default = all synced tasks
  configVersionIds: string[];    // 2 or more
  nTrials: number;
  nOverrides?: Record<string, number>;
  seed?: number;
}

@Injectable()
export class ExperimentsService {
  constructor(
    @InjectRepository(Experiment) private experiments: Repository<Experiment>,
    @InjectRepository(Trial) private trials: Repository<Trial>,
    @InjectRepository(Task) private tasks: Repository<Task>,
    @InjectRepository(TaskVersion) private taskVersions: Repository<TaskVersion>,
    @InjectRepository(ConfigVersion) private configVersions: Repository<ConfigVersion>,
    @InjectRepository(Grade) private grades: Repository<Grade>,
    @InjectRepository(TraceEvent) private events: Repository<TraceEvent>,
    private queue: QueueService,
  ) {}

  async create(body: CreateExperimentBody) {
    if (!body.configVersionIds || body.configVersionIds.length < 2) throw new BadRequestException('need at least 2 config versions');
    if (!(body.nTrials >= 1)) throw new BadRequestException('nTrials must be >= 1');
    const cvs = await this.configVersions.find({ where: { id: In(body.configVersionIds) } });
    if (cvs.length !== body.configVersionIds.length) throw new BadRequestException('unknown config version id');

    const taskRows = body.taskIds?.length
      ? await this.tasks.find({ where: { id: In(body.taskIds) } })
      : await this.tasks.find();
    if (!taskRows.length) throw new BadRequestException('no tasks: call POST /tasks/sync first');
    const tvs = await this.taskVersions.find({ where: { id: In(taskRows.map((t) => t.latestVersionId!)) } });

    // Frozen snapshot: the experiment pins exact task versions and config versions.
    const exp = await this.experiments.save(this.experiments.create({
      name: body.name, hypothesis: body.hypothesis ?? '',
      taskVersionIds: tvs.map((t) => t.id), configVersionIds: body.configVersionIds,
      nTrials: body.nTrials, nOverrides: body.nOverrides ?? {}, seed: body.seed ?? 1234, status: 'queued',
    }));

    // Expand: tasks x configs x N. Trial i of A and B share a seed, so they are paired.
    const rows: Partial<Trial>[] = [];
    for (const tv of tvs) {
      const n = exp.nOverrides[tv.taskId] ?? (tv.spec.chain ? this.chainN(tvs, tv.spec.chain, exp) : exp.nTrials);
      for (let i = 0; i < n; i++) {
        for (const cvId of exp.configVersionIds) {
          rows.push({
            experimentId: exp.id, taskVersionId: tv.id, taskId: tv.taskId, configVersionId: cvId,
            trialIndex: i, seed: exp.seed * 1000 + i, scored: tv.spec.scored !== false, status: 'queued',
          });
        }
      }
    }
    const saved = await this.trials.save(rows.map((r) => this.trials.create(r)), { chunk: 500 });
    await this.queue.enqueue(this.buildJobs(exp, saved, tvs));
    return { experiment: exp, trials: saved.length };
  }

  /** Every task in a memory chain must run the same number of times. */
  private chainN(tvs: TaskVersion[], chain: string, exp: Experiment) {
    return Math.max(...tvs.filter((t) => t.spec.chain === chain).map((t) => exp.nOverrides[t.taskId] ?? exp.nTrials));
  }

  /**
   * Group trials into jobs. Normal task = one job per trial. Memory chain = one job per
   * (chain, config, trial index) with the chain's tasks in order. Jobs are interleaved
   * (trial index outer, configs inner) so provider slowdowns hit both configs equally.
   */
  buildJobs(exp: Experiment, trials: Trial[], tvs: TaskVersion[]): TrialJob[] {
    const specOf = new Map(tvs.map((t) => [t.id, t.spec]));
    const groups = new Map<string, Trial[]>();
    for (const t of trials) {
      const spec = specOf.get(t.taskVersionId)!;
      const key = spec.chain ? `chain:${spec.chain}:${t.configVersionId}:${t.trialIndex}` : `single:${t.id}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(t);
    }
    const jobs = [...groups.values()].map((g) => {
      g.sort((x, y) => (specOf.get(x.taskVersionId)!.chain_order ?? 0) - (specOf.get(y.taskVersionId)!.chain_order ?? 0));
      return { trialIndex: g[0].trialIndex, cfg: exp.configVersionIds.indexOf(g[0].configVersionId), job: { experimentId: exp.id, trialIds: g.map((t) => t.id) } };
    });
    jobs.sort((x, y) => x.trialIndex - y.trialIndex || x.cfg - y.cfg);
    return jobs.map((j) => j.job);
  }

  /** Re-queue only failed or stuck cells (a failed trial in a chain re-runs its whole chain). */
  async resume(id: string) {
    const exp = await this.get(id);
    const all = await this.trials.find({ where: { experimentId: id } });
    const tvs = await this.taskVersions.find({ where: { id: In(exp.taskVersionIds) } });
    const specOf = new Map(tvs.map((t) => [t.id, t.spec]));
    const bad = all.filter((t) => ['infra_error', 'harness_error', 'running', 'queued'].includes(t.status));
    const toRun = all.filter((t) => {
      const chain = specOf.get(t.taskVersionId)?.chain;
      if (!chain) return bad.includes(t);
      return bad.some((b) => specOf.get(b.taskVersionId)?.chain === chain && b.configVersionId === t.configVersionId && b.trialIndex === t.trialIndex);
    });
    if (!toRun.length) return { requeued: 0 };
    await this.trials.update({ id: In(toRun.map((t) => t.id)) }, { status: 'queued' });
    await this.experiments.update(id, { status: 'running' });
    await this.queue.enqueue(this.buildJobs(exp, toRun, tvs));
    return { requeued: toRun.length };
  }

  async cancel(id: string) {
    await this.trials.update({ experimentId: id, status: 'queued' }, { status: 'cancelled' });
    await this.experiments.update(id, { status: 'cancelled' });
    return { ok: true };
  }

  async get(id: string) {
    const exp = await this.experiments.findOne({ where: { id } });
    if (!exp) throw new NotFoundException();
    return exp;
  }

  async list() {
    const exps = await this.experiments.find({ order: { createdAt: 'DESC' } });
    const counts = await this.trials.createQueryBuilder('t')
      .select('t.experimentId', 'experimentId').addSelect('t.status', 'status').addSelect('COUNT(*)', 'n')
      .groupBy('t.experimentId').addGroupBy('t.status').getRawMany();
    return exps.map((e) => ({
      ...e,
      progress: Object.fromEntries(counts.filter((c) => c.experimentId === e.id).map((c) => [c.status, Number(c.n)])),
    }));
  }

  async detail(id: string) {
    const exp = await this.get(id);
    const trials = await this.trials.find({
      where: { experimentId: id }, order: { taskId: 'ASC', trialIndex: 'ASC' },
      select: ['id', 'taskId', 'configVersionId', 'trialIndex', 'status', 'passed', 'costUsd', 'failureCategory', 'scored'],
    });
    const cvs = await this.configVersions.find({ where: { id: In(exp.configVersionIds) } });
    return { experiment: exp, configVersions: cvs, trials };
  }

  /**
   * The comparison page. A = first config, B = second (or pass ?a=&b=).
   * Only scored trials count; infra failures are excluded from BOTH sides of a pair.
   * ?tag=memory limits to tasks with that tag, ?excludeTag=memory to the rest.
   */
  async comparison(id: string, a?: string, b?: string, tag?: string, excludeTag?: string) {
    const exp = await this.get(id);
    const A = a ?? exp.configVersionIds[0];
    const B = b ?? exp.configVersionIds[1];
    const tvs = await this.taskVersions.find({ where: { id: In(exp.taskVersionIds) } });
    const tagOf = new Map(tvs.map((t) => [t.taskId, t.spec.tags ?? []]));
    const trials = (await this.trials.find({ where: { experimentId: id, configVersionId: In([A, B]), scored: true } }))
      .filter((t) => (!tag || tagOf.get(t.taskId)?.includes(tag)) && (!excludeTag || !tagOf.get(t.taskId)?.includes(excludeTag)));

    const infra = (cv: string) => trials.filter((t) => t.configVersionId === cv && t.status !== 'done' && t.status !== 'queued' && t.status !== 'running' && t.status !== 'cancelled').length;
    const total = (cv: string) => trials.filter((t) => t.configVersionId === cv).length;

    // Pair trial i of A with trial i of B on the same task; drop pairs where either side didn't finish.
    const byKey = new Map<string, { a?: Trial; b?: Trial }>();
    for (const t of trials) {
      const k = `${t.taskId}#${t.trialIndex}`;
      const cell = byKey.get(k) ?? {};
      if (t.configVersionId === A) cell.a = t; else cell.b = t;
      byKey.set(k, cell);
    }
    const pairs = [...byKey.values()].filter((p) => p.a?.status === 'done' && p.b?.status === 'done') as { a: Trial; b: Trial }[];
    const cellsFor = (value: (t: Trial) => number): PairedCell[] => {
      const m = new Map<string, PairedCell>();
      for (const p of pairs) {
        const c = m.get(p.a.taskId) ?? { taskId: p.a.taskId, a: [], b: [] };
        c.a.push(value(p.a)); c.b.push(value(p.b));
        m.set(p.a.taskId, c);
      }
      return [...m.values()];
    };

    const passCells = cellsFor((t) => (t.passed ? 1 : 0));
    const boot = pairedBootstrap(passCells, 10000, exp.seed);
    const costBoot = pairedBootstrap(cellsFor((t) => t.costUsd), 4000, exp.seed);
    const tokBoot = pairedBootstrap(cellsFor((t) => t.tokensIn + t.tokensOut), 4000, exp.seed);
    const median = (xs: number[]) => { const s = [...xs].sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : NaN; };

    const failures = (side: 'a' | 'b') => {
      const out: Record<string, number> = {};
      for (const p of pairs) { const t = p[side]; if (!t.passed) out[t.failureCategory ?? 'wrong_answer'] = (out[t.failureCategory ?? 'wrong_answer'] ?? 0) + 1; }
      return out;
    };

    const infraShare = Math.max(infra(A) / Math.max(1, total(A)), infra(B) / Math.max(1, total(B)));
    const cvs = await this.configVersions.find({ where: { id: In([A, B]) } });
    return {
      a: cvs.find((c) => c.id === A), b: cvs.find((c) => c.id === B),
      filter: { tag: tag ?? null, excludeTag: excludeTag ?? null },
      tasks: passCells.length, pairs: pairs.length,
      passRate: { a: mean(pairs.map((p) => (p.a.passed ? 1 : 0))), b: mean(pairs.map((p) => (p.b.passed ? 1 : 0))) },
      delta: boot.delta, ci95: [boot.lo, boot.hi], bootstrapP: boot.p,
      verdict: infraShare > 0.05 ? 'withheld: too many infrastructure failures, resume the experiment' : verdictFromCI(boot.lo, boot.hi),
      mcnemar: mcnemarByTask(passCells),
      perTask: perTask(passCells),
      cost: { meanA: mean(pairs.map((p) => p.a.costUsd)), meanB: mean(pairs.map((p) => p.b.costUsd)), delta: costBoot.delta, ci95: [costBoot.lo, costBoot.hi] },
      tokens: { meanA: mean(pairs.map((p) => p.a.tokensIn + p.a.tokensOut)), meanB: mean(pairs.map((p) => p.b.tokensIn + p.b.tokensOut)), delta: tokBoot.delta, ci95: [tokBoot.lo, tokBoot.hi] },
      latencyMs: { medianA: median(pairs.map((p) => p.a.latencyMs)), medianB: median(pairs.map((p) => p.b.latencyMs)) },
      failureCategories: { a: failures('a'), b: failures('b') },
      infraFailures: { a: infra(A), b: infra(B) },
      totalSpendUsd: trials.reduce((s, t) => s + t.costUsd, 0),
    };
  }

  async exportTrials(id: string) {
    return this.trials.find({ where: { experimentId: id }, order: { taskId: 'ASC', trialIndex: 'ASC' } });
  }

  async exportBundle(id: string) {
    const exp = await this.get(id);
    const trials = await this.exportTrials(id);
    return {
      experiment: exp,
      configVersions: await this.configVersions.find({ where: { id: In(exp.configVersionIds) } }),
      taskVersions: await this.taskVersions.find({ where: { id: In(exp.taskVersionIds) } }),
      trials,
      grades: trials.length ? await this.grades.find({ where: { trialId: In(trials.map((t) => t.id)) } }) : [],
      comparison: await this.comparison(id),
    };
  }
}

const CSV_COLUMNS: (keyof Trial)[] = [
  'id', 'taskId', 'configVersionId', 'trialIndex', 'seed', 'scored', 'status', 'passed', 'score', 'stopReason',
  'failureCategory', 'tokensIn', 'tokensOut', 'costUsd', 'latencyMs', 'steps', 'attempt', 'error',
];
const csvCell = (v: unknown) => {
  const s = v === null || v === undefined ? '' : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

@Controller('experiments')
export class ExperimentsController {
  constructor(private svc: ExperimentsService) {}

  @Post() create(@Body() body: CreateExperimentBody) { return this.svc.create(body); }
  @Get() list() { return this.svc.list(); }
  @Get(':id') detail(@Param('id') id: string) { return this.svc.detail(id); }
  @Post(':id/resume') resume(@Param('id') id: string) { return this.svc.resume(id); }
  @Post(':id/cancel') cancel(@Param('id') id: string) { return this.svc.cancel(id); }

  @Get(':id/comparison')
  comparison(@Param('id') id: string, @Query('a') a?: string, @Query('b') b?: string,
    @Query('tag') tag?: string, @Query('excludeTag') excludeTag?: string) {
    return this.svc.comparison(id, a, b, tag, excludeTag);
  }

  @Get(':id/export')
  async export(@Param('id') id: string, @Query('format') format = 'json', @Res() res: Response) {
    if (format === 'csv') {
      const rows = await this.svc.exportTrials(id);
      const body = [CSV_COLUMNS.join(','), ...rows.map((r) => CSV_COLUMNS.map((c) => csvCell(r[c])).join(','))].join('\n');
      res.setHeader('Content-Type', 'text/csv');
      res.setHeader('Content-Disposition', `attachment; filename="experiment-${id}-trials.csv"`);
      return res.send(body);
    }
    res.setHeader('Content-Disposition', `attachment; filename="experiment-${id}.json"`);
    return res.json(await this.svc.exportBundle(id));
  }
}
