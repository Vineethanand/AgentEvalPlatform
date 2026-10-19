"""Worker process: pulls trial jobs from the BullMQ queue and runs them.

python -m evalworker.main
Run several copies (or `docker compose up --scale worker=4`) to go faster.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal

from bullmq import Worker

from .runner import Runner

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("evalworker")


async def main() -> None:
    """Start the queue worker and run until SIGINT/SIGTERM."""
    runner = Runner()

    async def process(job, _job_token):
        """Handle one queue job: its ``trialIds`` are one trial, or a memory chain to run in order."""
        trial_ids = job.data["trialIds"]
        log.info("job %s: %d trial(s)", job.id, len(trial_ids))
        # The runner is blocking (docker, subprocess, HTTP); keep the event loop free for BullMQ's lock renewal.
        await asyncio.to_thread(runner.run_job, trial_ids)
        return {"trials": len(trial_ids)}

    worker = Worker("trials", process, {
        "connection": os.environ.get("REDIS_URL", "redis://localhost:6379"),
        "concurrency": int(os.environ.get("WORKER_CONCURRENCY", "1")),
        "lockDuration": 120_000,   # ms; the job lock is renewed while the thread runs, so long trials stay locked
    })
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows event loops do not support signal handlers
            pass
    log.info("worker started, waiting for jobs")
    await stop.wait()
    await worker.close()


if __name__ == "__main__":
    asyncio.run(main())
