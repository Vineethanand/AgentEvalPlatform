import { BadRequestException, Body, Controller, Delete, Get, Injectable, NotFoundException, Param, Post } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Config, ConfigSettings, ConfigVersion, Experiment } from './entities';
import { HARNESSES, loadModels, sha256, stableStringify } from './common';

export interface ConfigVersionInput {
  harness: string;
  modelAlias: string;
  settings: ConfigSettings;
}

const DEFAULT_SETTINGS: ConfigSettings = {
  temperature: 0.7,
  max_steps: 25,
  max_tokens_total: 200000,
  timeout_s: 600,
  tools: ['bash', 'read_file', 'write_file', 'list_dir'],
  skills: [],
  memory: { mode: 'off' },
  system_prompt_override: null,
};

@Injectable()
export class ConfigsService {
  constructor(
    @InjectRepository(Config) private configs: Repository<Config>,
    @InjectRepository(ConfigVersion) private versions: Repository<ConfigVersion>,
    @InjectRepository(Experiment) private experiments: Repository<Experiment>,
  ) {}

  /** Reject settings the chosen harness can't honour, and unknown models. */
  validate(input: ConfigVersionInput): ConfigSettings {
    const harness = HARNESSES[input.harness];
    if (!harness) throw new BadRequestException(`unknown harness "${input.harness}". Known: ${Object.keys(HARNESSES).join(', ')}`);
    const settings = { ...DEFAULT_SETTINGS, ...input.settings };
    const caps = new Set(harness.capabilities);
    if (settings.memory && settings.memory.mode !== 'off' && !caps.has('memory'))
      throw new BadRequestException(`harness "${input.harness}" has no memory capability`);
    if (settings.skills?.length && !caps.has('skills'))
      throw new BadRequestException(`harness "${input.harness}" has no skills capability`);
    if (!['off', 'fresh', 'carry'].includes(settings.memory?.mode ?? 'off'))
      throw new BadRequestException('memory.mode must be off | fresh | carry');
    if (!loadModels().some((m) => m.alias === input.modelAlias))
      throw new BadRequestException(`unknown model alias "${input.modelAlias}" (see gateway/litellm_config.yaml)`);
    return settings;
  }

  async create(body: { name: string; description?: string } & ConfigVersionInput) {
    if (await this.configs.findOne({ where: { name: body.name } })) throw new BadRequestException('config name already exists');
    this.validate(body);
    const cfg = await this.configs.save(this.configs.create({ name: body.name, description: body.description ?? '' }));
    const version = await this.addVersion(cfg.id, body);
    return { config: cfg, version };
  }

  /** Versions are immutable: editing a config always creates version n+1. */
  async addVersion(configId: string, input: ConfigVersionInput) {
    const settings = this.validate(input);
    const model = loadModels().find((m) => m.alias === input.modelAlias)!;
    const last = await this.versions.findOne({ where: { configId }, order: { version: 'DESC' } });
    const modelSnapshot = { ...model };
    const hash = sha256(stableStringify({ harness: input.harness, model: modelSnapshot, settings }));
    if (last && last.hash === hash) return last;
    return this.versions.save(this.versions.create({
      configId, version: (last?.version ?? 0) + 1, hash, harness: input.harness,
      modelAlias: input.modelAlias, modelSnapshot, settings,
    }));
  }

  async list() {
    const cfgs = await this.configs.find({ order: { name: 'ASC' } });
    const versions = await this.versions.find({ order: { version: 'DESC' } });
    return cfgs.map((c) => ({ ...c, versions: versions.filter((v) => v.configId === c.id) }));
  }

  /** Experiments pin exact config versions, so a config that any experiment used cannot be deleted. */
  async remove(id: string) {
    const cfg = await this.configs.findOne({ where: { id } });
    if (!cfg) throw new NotFoundException();
    const versions = await this.versions.find({ where: { configId: id } });
    const ids = new Set(versions.map((v) => v.id));
    const users = (await this.experiments.find()).filter((e) => e.configVersionIds.some((v) => ids.has(v)));
    if (users.length)
      throw new BadRequestException(`config is used by ${users.length} experiment(s): ${users.map((e) => e.name).join(', ')}. Delete those experiments first.`);
    await this.versions.delete({ configId: id });
    await this.configs.delete(id);
    return { ok: true, versionsDeleted: versions.length };
  }

  async version(id: string) {
    const v = await this.versions.findOne({ where: { id } });
    if (!v) throw new NotFoundException();
    return v;
  }
}

@Controller()
export class ConfigsController {
  constructor(private svc: ConfigsService) {}

  @Get('harnesses') harnesses() { return HARNESSES; }
  @Get('models') models() { return loadModels(); }
  @Get('configs') list() { return this.svc.list(); }
  @Post('configs') create(@Body() body: { name: string; description?: string } & ConfigVersionInput) { return this.svc.create(body); }
  @Post('configs/:id/versions') addVersion(@Param('id') id: string, @Body() body: ConfigVersionInput) { return this.svc.addVersion(id, body); }
  @Delete('configs/:id') remove(@Param('id') id: string) { return this.svc.remove(id); }
  @Get('config-versions/:id') version(@Param('id') id: string) { return this.svc.version(id); }
}
