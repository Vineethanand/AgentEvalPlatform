import { createHash } from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { parse } from 'yaml';
import { Controller, Get, Injectable, Param, Post } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Task, TaskSpec, TaskVersion } from './entities';
import { hashDir } from './common';

export const tasksDir = () => process.env.TASKS_DIR ?? path.resolve(__dirname, '../../../tasks');

@Injectable()
export class TasksService {
  constructor(
    @InjectRepository(Task) private tasks: Repository<Task>,
    @InjectRepository(TaskVersion) private versions: Repository<TaskVersion>,
  ) {}

  /** Scan tasks/ and create a new TaskVersion for every task whose content hash changed. */
  async sync(): Promise<{ created: string[]; unchanged: string[] }> {
    const root = tasksDir();
    const created: string[] = [];
    const unchanged: string[] = [];
    for (const name of fs.readdirSync(root).sort()) {
      const dir = path.join(root, name);
      const file = path.join(dir, 'task.yaml');
      if (!fs.statSync(dir).isDirectory() || !fs.existsSync(file)) continue;
      const spec = parse(fs.readFileSync(file, 'utf8')) as TaskSpec;
      if (spec.id !== name) throw new Error(`tasks/${name}/task.yaml has id "${spec.id}"; it must match the folder name`);
      // reference/ and negatives/ are only for validating graders; they don't change what a trial sees.
      let hash = hashDir(dir, ['reference', 'negatives']);
      if (spec.fixtures_from) {  // shared fixtures are part of what a trial sees, so a change there is a new version
        const shared = path.join(root, spec.fixtures_from);
        if (!fs.existsSync(shared)) throw new Error(`tasks/${name}: fixtures_from "${spec.fixtures_from}" not found`);
        hash = createHash('sha256').update(hash).update(hashDir(shared)).digest('hex');
      }
      let version = await this.versions.findOne({ where: { taskId: spec.id, hash } });
      if (!version) {
        version = await this.versions.save(this.versions.create({ taskId: spec.id, hash, spec }));
        created.push(spec.id);
      } else unchanged.push(spec.id);
      await this.tasks.save({ id: spec.id, title: spec.title ?? spec.id, tags: spec.tags ?? [], latestVersionId: version.id });
    }
    return { created, unchanged };
  }

  list() {
    return this.tasks.find({ order: { id: 'ASC' } });
  }

  versionsOf(taskId: string) {
    return this.versions.find({ where: { taskId }, order: { createdAt: 'DESC' } });
  }
}

@Controller('tasks')
export class TasksController {
  constructor(private svc: TasksService) {}
  @Get() list() { return this.svc.list(); }
  @Post('sync') sync() { return this.svc.sync(); }
  @Get(':id/versions') versions(@Param('id') id: string) { return this.svc.versionsOf(id); }
}
