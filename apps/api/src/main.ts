import 'reflect-metadata';
import { Module } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { TypeOrmModule } from '@nestjs/typeorm';
import { json } from 'express';
import { ALL_ENTITIES } from './entities';
import { TasksController, TasksService } from './tasks';
import { ConfigsController, ConfigsService } from './configs';
import { ExperimentsController, ExperimentsService, QueueService } from './experiments';
import { InternalController, TrialsController, TrialsService } from './trials';

@Module({
  imports: [
    TypeOrmModule.forRoot({
      type: 'postgres',
      url: process.env.DATABASE_URL ?? 'postgresql://evals:evals@localhost:5432/evals',
      entities: ALL_ENTITIES,
      // Fine for a local single-user tool. A production setup would use migrations.
      synchronize: true,
    }),
    TypeOrmModule.forFeature(ALL_ENTITIES),
  ],
  controllers: [TasksController, ConfigsController, ExperimentsController, TrialsController, InternalController],
  providers: [TasksService, ConfigsService, ExperimentsService, QueueService, TrialsService],
})
class AppModule {}

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.use(json({ limit: '20mb' }));
  app.enableCors();
  await app.listen(Number(process.env.PORT ?? 3000));
  // eslint-disable-next-line no-console
  console.log(`API listening on :${process.env.PORT ?? 3000}`);
}
bootstrap();
