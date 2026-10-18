"""Where a trial's harness actually runs.

docker (default in compose): one fresh container per trial from the harness image,
  1 CPU / 2 GB, on an internal network that only reaches the model gateway.
local: a plain subprocess. No isolation beyond separate folders; for development
  (e.g. on Windows without Docker access from the worker) and for the baseline harness.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)
WORKERS_ROOT = Path(__file__).resolve().parent.parent

IMAGES = {
    "baseline": os.environ.get("IMAGE_BASELINE", "aep/harness-baseline:latest"),
    "hermes": os.environ.get("IMAGE_HERMES", "aep/harness-hermes:latest"),
}


@dataclass
class SandboxOutcome:
    ok: bool                 # False = infrastructure failure (couldn't start, killed by OOM, ...)
    timed_out: bool = False
    detail: str = ""


class LocalSandbox:
    def run(self, harness: str, ctx_path: Path, workspace: Path, timeout_s: int) -> SandboxOutcome:
        # HARNESS_PYTHONPATH lets a locally installed harness (e.g. a Hermes checkout) be found.
        extra = os.environ.get("HARNESS_PYTHONPATH", "")
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in [str(WORKERS_ROOT), extra] if p)}
        log_file = ctx_path.parent / "native" / "process.log"
        log_file.parent.mkdir(exist_ok=True)
        with log_file.open("w") as lf:
            try:
                p = subprocess.run([sys.executable, "-m", "evalworker.adapters.run", str(ctx_path), harness],
                                   cwd=workspace, env=env, stdout=lf, stderr=subprocess.STDOUT, timeout=timeout_s + 30)
            except subprocess.TimeoutExpired:
                return SandboxOutcome(ok=True, timed_out=True, detail="killed after timeout")
        return SandboxOutcome(ok=p.returncode == 0, detail=f"exit {p.returncode}")


class DockerSandbox:
    def __init__(self):
        import docker  # only needed in docker mode

        self.client = docker.from_env()
        self.network = os.environ.get("SANDBOX_NETWORK", "aep_sandbox")
        self.volume = os.environ.get("TRIALS_VOLUME")   # named volume shared with the worker
        self.data_root = os.environ.get("TRIALS_MOUNT", "/data")

    def run(self, harness: str, ctx_path: Path, workspace: Path, timeout_s: int) -> SandboxOutcome:
        import docker

        image = IMAGES[harness]
        volumes = {self.volume: {"bind": self.data_root, "mode": "rw"}} if self.volume \
            else {str(Path(self.data_root).resolve()): {"bind": self.data_root, "mode": "rw"}}
        container = None
        try:
            container = self.client.containers.run(
                image, command=["python", "-m", "evalworker.adapters.run", str(ctx_path), harness],
                working_dir=str(workspace), volumes=volumes, network=self.network,
                mem_limit="2g", nano_cpus=1_000_000_000, detach=True,
                environment={"PYTHONUNBUFFERED": "1"},
            )
            try:
                status = container.wait(timeout=timeout_s + 30)
                timed_out = False
            except Exception:  # noqa: BLE001 - requests ReadTimeout
                container.kill()
                status, timed_out = {"StatusCode": -1}, True
            (ctx_path.parent / "native").mkdir(exist_ok=True)
            (ctx_path.parent / "native" / "container.log").write_bytes(container.logs())
            code = status.get("StatusCode", -1)
            if code == 137 and not timed_out:
                return SandboxOutcome(ok=False, detail="container killed (out of memory?)")
            return SandboxOutcome(ok=code == 0 or timed_out, timed_out=timed_out, detail=f"exit {code}")
        except docker.errors.DockerException as e:
            return SandboxOutcome(ok=False, detail=f"docker error: {e}")
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:  # noqa: BLE001
                    pass


def make_sandbox():
    mode = os.environ.get("SANDBOX_MODE", "local")
    return DockerSandbox() if mode == "docker" else LocalSandbox()
