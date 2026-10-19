// Data model. Everything a result depends on is versioned and immutable:
// a trial points at an exact task version and config version, never "latest".
import {
  Column, CreateDateColumn, Entity, Index, PrimaryColumn, PrimaryGeneratedColumn, Unique,
} from 'typeorm';

@Entity('task')
export class Task {
  @PrimaryColumn() id: string; // slug, e.g. "csv-aggregate"
  @Column() title: string;
  @Column('jsonb', { default: () => "'[]'" }) tags: string[];
  @Column({ type: 'varchar', nullable: true }) latestVersionId: string | null;
}

@Entity('task_version')
@Unique(['taskId', 'hash'])
export class TaskVersion {
  @PrimaryGeneratedColumn('uuid') id: string;
  @Column() taskId: string;
  @Column() hash: string; // covers task.yaml + fixtures + grader + skills
  @Column('jsonb') spec: TaskSpec;
  @CreateDateColumn() createdAt: Date;
}

export interface TaskSpec {
  id: string;
  title?: string;
  prompt: string;
  tags?: string[];
  timeout_s?: number;
  fixtures_from?: string;    // shared folder under tasks/ copied into the workspace before the task's own fixtures/
  scored?: boolean;          // false for "teach" tasks in a memory chain
  chain?: string;            // memory chain id, e.g. "m1"
  chain_order?: number;      // position in the chain
  required_tools?: string[];
  graders: Array<Record<string, unknown> & { type: string; primary?: boolean }>;
}

@Entity('config')
export class Config {
  @PrimaryGeneratedColumn('uuid') id: string;
  @Column({ unique: true }) name: string;
  @Column({ default: '' }) description: string;
}

@Entity('config_version')
@Unique(['configId', 'version'])
export class ConfigVersion {
  @PrimaryGeneratedColumn('uuid') id: string;
  @Column() configId: string;
  @Column('int') version: number;
  @Column() hash: string;
  @Column() harness: string;        // "baseline" | "hermes" | ...
  @Column() modelAlias: string;     // alias in gateway/litellm_config.yaml
  @Column('jsonb') modelSnapshot: Record<string, unknown>; // provider model id + prices at creation time
  @Column('jsonb') settings: ConfigSettings;
  @CreateDateColumn() createdAt: Date;
}

export interface ConfigSettings {
  temperature?: number;
  max_steps?: number;
  max_tokens_total?: number;
  timeout_s?: number;
  tools?: string[];
  skills?: string[];
  memory?: { mode: 'off' | 'fresh' | 'carry' };
  system_prompt_override?: string | null;
}

@Entity('experiment')
export class Experiment {
  @PrimaryGeneratedColumn('uuid') id: string;
  @Column() name: string;
  @Column({ default: '' }) hypothesis: string;
  @Column('jsonb') taskVersionIds: string[];
  @Column('jsonb') configVersionIds: string[];
  @Column('int') nTrials: number;
  @Column('jsonb', { default: () => "'{}'" }) nOverrides: Record<string, number>; // taskId -> N
  @Column('int', { default: 1234 }) seed: number;
  @Column({ default: 'queued' }) status: string; // queued | running | done | incomplete | cancelled
  @CreateDateColumn() createdAt: Date;
}

@Entity('trial')
@Unique(['experimentId', 'taskVersionId', 'configVersionId', 'trialIndex'])
@Index(['experimentId', 'status'])
export class Trial {
  @PrimaryGeneratedColumn('uuid') id: string;
  @Column() experimentId: string;
  @Column() taskVersionId: string;
  @Column() taskId: string;
  @Column() configVersionId: string;
  @Column('int') trialIndex: number;
  @Column('int') seed: number;
  @Column({ default: true }) scored: boolean;
  @Column({ default: 'queued' }) status: string; // queued | running | done | harness_error | infra_error
  @Column('int', { default: 0 }) attempt: number;
  @Column({ type: 'varchar', nullable: true }) stopReason: string | null;
  @Column({ type: 'text', nullable: true }) finalAnswer: string | null;
  @Column({ type: 'boolean', nullable: true }) passed: boolean | null;
  @Column({ type: 'float', nullable: true }) score: number | null;
  @Column('int', { default: 0 }) tokensIn: number;
  @Column('int', { default: 0 }) tokensOut: number;
  @Column('float', { default: 0 }) costUsd: number;
  @Column('int', { default: 0 }) latencyMs: number;
  @Column('int', { default: 0 }) steps: number;
  @Column({ type: 'text', nullable: true }) error: string | null;
  @Column({ type: 'varchar', nullable: true }) failureCategory: string | null;
  @Column({ type: 'timestamptz', nullable: true }) startedAt: Date | null;
  @Column({ type: 'timestamptz', nullable: true }) finishedAt: Date | null;
}

@Entity('trace_event')
@Index(['trialId', 'attempt', 'seq'])
export class TraceEvent {
  @PrimaryGeneratedColumn('increment') id: number;
  @Column() trialId: string;
  @Column('int') attempt: number;
  @Column('int') seq: number;
  @Column({ type: 'int', nullable: true }) parentSeq: number | null;
  @Column() type: string; // llm_call | tool_call | tool_result | memory_read | memory_write | skill_invoked | agent_message | harness_note
  @Column({ type: 'timestamptz' }) ts: Date;
  @Column('jsonb') payload: Record<string, unknown>;
}

@Entity('grade')
export class Grade {
  @PrimaryGeneratedColumn('uuid') id: string;
  @Column() trialId: string;
  @Column() grader: string;
  @Column({ default: false }) primary: boolean;
  @Column('float') score: number;
  @Column() passed: boolean;
  @Column({ type: 'text', default: '' }) reasoning: string;
  @Column('jsonb', { default: () => "'{}'" }) raw: Record<string, unknown>;
  @Column('float', { default: 0 }) judgeCostUsd: number;
}

export const ALL_ENTITIES = [Task, TaskVersion, Config, ConfigVersion, Experiment, Trial, TraceEvent, Grade];
