import {
  Body, Controller, Get, Injectable, NotFoundException, Param, Post, Query, UseGuards,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { In, LessThan, MoreThan, Not, Repository } from 'typeorm';
import * as path from 'path';
import { ConfigVersion, Experiment, Grade, TaskVersion, TraceEvent, Trial } from './entities';
import { InternalTokenGuard } from './common';
import { tasksDir } from './tasks';

export interface EventIn {
  seq: number;
  parent_seq?: number | null;
  type: string;
  ts?: string;
  payload?: Record<string, unknown>;
}

export interface CompleteBody {
  attempt: number;
  status: 'done' | 'harness_error' | 'infra_error';
  stopReason?: string;
  finalAnswer?: string;
  passed?: boolean | null;
  score?: number | null;
  tokensIn?: number;
  tokensOut?: number;
  costUsd?: number;
  latencyMs?: number;
  steps?: number;
  error?: string | null;
  failureCategory?: string | null;
  grades?: Array<{ grader: string; primary?: boolean; score: number; passed: boolean; reasoning?: string; raw?: Record<string, unknown>; judgeCostUsd?: number }>;
}

@Injectable()
export class TrialsService {
  constructor(
    @InjectRepository(Trial) private trials: Repository<Trial>,
    @InjectRepository(TraceEvent) private events: Repository<TraceEvent>,
    @InjectRepository(Grade) private grades: Repository<Grade>,
    @InjectRepository(TaskVersion) private taskVersions: Repository<TaskVersion>,
    @InjectRepository(ConfigVersion) private configVersions: Repository<ConfigVersion>,
    @InjectRepository(Experiment) private experiments: Repository<Experiment>,
  ) {}

  private async trial(id: string) {
    const t = await this.trials.findOne({ where: { id } });
    if (!t) throw new NotFoundException(`trial ${id}`);
    return t;
  }

  // ---------------- public (UI) ----------------

  async view(id: string) {
    const trial = await this.trial(id);
    const [grades, events, taskVersion, configVersion] = await Promise.all([
      this.grades.find({ where: { trialId: id } }),
      this.events.find({ where: { trialId: id, attempt: trial.attempt }, order: { seq: 'ASC' } }),
      this.taskVersions.findOne({ where: { id: trial.taskVersionId } }),
      this.configVersions.findOne({ where: { id: trial.configVersionId } }),
    ]);
    return { trial, grades, events, taskVersion, configVersion };
  }

  /** Same task and trial index under the other config(s): for side-by-side comparison. */
  async pair(id: string) {
    const t = await this.trial(id);
    return this.trials.find({
      where: { experimentId: t.experimentId, taskId: t.taskId, trialIndex: t.trialIndex, id: Not(t.id) },
    });
  }

  async eventsAfter(id: string, after: number) {
    const t = await this.trial(id);
    return this.events.find({ where: { trialId: id, attempt: t.attempt, seq: MoreThan(after) }, order: { seq: 'ASC' } });
  }

  // ---------------- internal (workers) ----------------

  /** Everything a worker needs to run a trial, frozen at experiment creation. */
  async spec(id: string) {
    const trial = await this.trial(id);
    const tv = await this.taskVersions.findOne({ where: { id: trial.taskVersionId } });
    const cv = await this.configVersions.findOne({ where: { id: trial.configVersionId } });
    return {
      trial, task: tv!.spec, taskHash: tv!.hash,
      taskDir: path.join(tasksDir(), tv!.taskId),
      config: cv,
    };
  }

  /** Marks a trial running and bumps its attempt. Events from older attempts are dropped. */
  async start(id: string) {
    const t = await this.trial(id);
    if (t.status === 'cancelled') return { skip: true, attempt: t.attempt };
    const attempt = t.attempt + 1;
    await this.trials.update(id, { status: 'running', attempt, startedAt: new Date(), finishedAt: null, error: null });
    await this.events.delete({ trialId: id, attempt: LessThan(attempt) });
    await this.grades.delete({ trialId: id });
    await this.experiments.update({ id: t.experimentId, status: 'queued' }, { status: 'running' });
    return { skip: false, attempt };
  }

  async addEvents(id: string, attempt: number, events: EventIn[]) {
    const t = await this.trial(id);
    if (attempt !== t.attempt) return { accepted: 0, stale: true };
    await this.events.save(events.map((e) => this.events.create({
      trialId: id, attempt, seq: e.seq, parentSeq: e.parent_seq ?? null, type: e.type,
      ts: e.ts ? new Date(e.ts) : new Date(), payload: e.payload ?? {},
    })), { chunk: 200 });
    return { accepted: events.length };
  }

  /** Idempotent: a duplicate or stale completion (older attempt) is ignored. */
  async complete(id: string, body: CompleteBody) {
    const t = await this.trial(id);
    // Stale attempt, or this attempt was already recorded: ignore (safe to retry the POST).
    if (body.attempt !== t.attempt || t.status !== 'running') return { ignored: true };
    await this.trials.update(id, {
      status: body.status, stopReason: body.stopReason ?? null, finalAnswer: body.finalAnswer ?? null,
      passed: body.status === 'done' ? (body.passed ?? false) : null,
      score: body.status === 'done' ? (body.score ?? (body.passed ? 1 : 0)) : null,
      tokensIn: body.tokensIn ?? 0, tokensOut: body.tokensOut ?? 0, costUsd: body.costUsd ?? 0,
      latencyMs: body.latencyMs ?? 0, steps: body.steps ?? 0, error: body.error ?? null,
      failureCategory: body.failureCategory ?? null, finishedAt: new Date(),
    });
    await this.grades.delete({ trialId: id });
    if (body.grades?.length) {
      await this.grades.save(body.grades.map((g) => this.grades.create({
        trialId: id, grader: g.grader, primary: !!g.primary, score: g.score, passed: g.passed,
        reasoning: g.reasoning ?? '', raw: g.raw ?? {}, judgeCostUsd: g.judgeCostUsd ?? 0,
      })));
    }
    await this.refreshExperimentStatus(t.experimentId);
    return { ok: true };
  }

  private async refreshExperimentStatus(experimentId: string) {
    const open = await this.trials.count({ where: { experimentId, status: In(['queued', 'running']) } });
    if (open > 0) return;
    const failed = await this.trials.count({ where: { experimentId, status: In(['infra_error', 'harness_error']) } });
    await this.experiments.update({ id: experimentId, status: Not('cancelled') }, { status: failed ? 'incomplete' : 'done' });
  }
}

@Controller('trials')
export class TrialsController {
  constructor(private svc: TrialsService) {}
  @Get(':id') view(@Param('id') id: string) { return this.svc.view(id); }
  @Get(':id/pair') pair(@Param('id') id: string) { return this.svc.pair(id); }
  @Get(':id/events') events(@Param('id') id: string, @Query('after') after = '-1') { return this.svc.eventsAfter(id, Number(after)); }
}

@Controller('internal/trials')
@UseGuards(InternalTokenGuard)
export class InternalController {
  constructor(private svc: TrialsService) {}
  @Get(':id/spec') spec(@Param('id') id: string) { return this.svc.spec(id); }
  @Post(':id/start') start(@Param('id') id: string) { return this.svc.start(id); }
  @Post(':id/events') events(@Param('id') id: string, @Body() body: { attempt: number; events: EventIn[] }) {
    return this.svc.addEvents(id, body.attempt, body.events ?? []);
  }
  @Post(':id/complete') complete(@Param('id') id: string, @Body() body: CompleteBody) { return this.svc.complete(id, body); }
}
