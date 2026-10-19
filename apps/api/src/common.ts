import { createHash } from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { parse } from 'yaml';
import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';

export const sha256 = (s: string | Buffer): string => createHash('sha256').update(s).digest('hex');

/** Stable JSON stringify (sorted keys) so equal objects hash equally. */
export function stableStringify(v: unknown): string {
  if (v === null || typeof v !== 'object') return JSON.stringify(v);
  if (Array.isArray(v)) return `[${v.map(stableStringify).join(',')}]`;
  const o = v as Record<string, unknown>;
  return `{${Object.keys(o).sort().map((k) => `${JSON.stringify(k)}:${stableStringify(o[k])}`).join(',')}}`;
}

/** Hash every file under dir (relative path + content), skipping folders that don't affect a trial. */
export function hashDir(dir: string, skip: string[] = []): string {
  const h = createHash('sha256');
  const walk = (d: string) => {
    for (const name of fs.readdirSync(d).sort()) {
      const full = path.join(d, name);
      const rel = path.relative(dir, full).split(path.sep).join('/');
      if (skip.some((s) => rel === s || rel.startsWith(`${s}/`))) continue;
      if (fs.statSync(full).isDirectory()) walk(full);
      else h.update(rel).update('\0').update(fs.readFileSync(full)).update('\0');
    }
  };
  walk(dir);
  return h.digest('hex');
}

// ---------------------------------------------------------------------------
// Harness registry. A harness declares its capabilities; a config that asks for
// a setting the harness can't honour is rejected up front, so a setting never
// silently does nothing.
// ---------------------------------------------------------------------------
export const HARNESSES: Record<string, { image: string; capabilities: string[] }> = {
  baseline: { image: 'aep/harness-baseline:latest', capabilities: ['tools', 'temperature', 'max_steps', 'memory', 'skills'] },
  hermes: { image: 'aep/harness-hermes:latest', capabilities: ['tools', 'temperature', 'max_steps', 'memory', 'skills'] },
  'claude-code': { image: 'aep/harness-claude-code:latest', capabilities: ['tools', 'max_steps', 'memory', 'skills'] },
};

export interface ModelEntry {
  alias: string;
  litellmModel: string;
  priceInputPerMtok: number;
  priceOutputPerMtok: number;
  provider?: string;
  openWeight?: boolean;
}

/** Models come from the gateway's own config, so there is one model registry. */
export function loadModels(): ModelEntry[] {
  const file = process.env.MODELS_FILE ?? path.resolve(__dirname, '../../../gateway/litellm_config.yaml');
  const doc = parse(fs.readFileSync(file, 'utf8')) as {
    model_list: Array<{ model_name: string; litellm_params: { model: string }; model_info?: Record<string, unknown> }>;
  };
  return doc.model_list.map((m) => ({
    alias: m.model_name,
    litellmModel: m.litellm_params.model,
    priceInputPerMtok: Number(m.model_info?.price_input_per_mtok ?? 0),
    priceOutputPerMtok: Number(m.model_info?.price_output_per_mtok ?? 0),
    provider: m.model_info?.provider as string | undefined,
    openWeight: Boolean(m.model_info?.open_weight),
  }));
}

@Injectable()
export class InternalTokenGuard implements CanActivate {
  canActivate(ctx: ExecutionContext): boolean {
    const expected = process.env.INTERNAL_TOKEN;
    const got = ctx.switchToHttp().getRequest().headers['x-internal-token'];
    if (!expected || got !== expected) throw new UnauthorizedException('bad internal token');
    return true;
  }
}
