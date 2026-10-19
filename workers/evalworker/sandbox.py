"""Where a trial's harness actually runs.

docker (default in compose): one fresh container per trial from the harness image,
  1 CPU / 2 GB, on an internal network that only reaches the model gateway. It mounts only that trial's own
  folder (plus the shared memory home in a "carry" memory chain), never the whole trials volume, so one trial
  cannot read or change another trial's files.
local: a plain subprocess. No isolation beyond separate folders; for development
  (e.g. on Windows without Docker access from the worker) and for the baseline harness.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

log = logging.getLogger(__name__)
WORKERS_ROOT = Path(__file__).resolve().parent.parent

IMAGES = {
    "baseline": os.environ.get("IMAGE_BASELINE", "aep/harness-baseline:latest"),
    "hermes": os.environ.get("IMAGE_HERMES", "aep/harness-hermes:latest"),
    "claude-code": os.environ.get("IMAGE_CLAUDE_CODE", "aep/harness-claude-code:latest"),
}

# Harnesses that call their provider directly (subscription auth) instead of the gateway:
# they get a network with real egress and the token passed through from the worker env.
DIRECT = {"claude-code"}
PASSTHROUGH_ENV = ("CLAUDE_CODE_OAUTH_TOKEN",)


@dataclass
class SandboxOutcome:
    ok: bool                 # False = infrastructure failure (couldn't start, killed by OOM, ...)
    timed_out: bool = False
    detail: str = ""


class LocalSandbox:
    def run(self, harness: str, ctx_path: Path, workspace: Path, timeout_s: int,
            extra_rw: tuple[Path, ...] = ()) -> SandboxOutcome:
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

    def mounts(self, trial_dir: Path, extra_rw: tuple[Path, ...] = ()) -> list:
        """Mounts for one trial: its own folder, plus any extra folder it must share (the memory home of a
        "carry" chain). Each is mounted at its own path, so the paths in ctx.json stay valid. Nothing else
        under the trials root is visible."""
        from docker.types import Mount

        mounts = []
        if self.volume:  # named volume shared with the worker: expose only this sub-folder of it
            root = PurePosixPath(Path(self.data_root).as_posix())
            for p in dict.fromkeys(PurePosixPath(Path(x).as_posix()) for x in (trial_dir, *extra_rw)):
                mounts.append(Mount(target=str(p), source=self.volume, type="volume",
                                    subpath=p.relative_to(root).as_posix()))
        else:
            for p in dict.fromkeys(Path(x).resolve() for x in (trial_dir, *extra_rw)):
                mounts.append(Mount(target=str(p), source=str(p), type="bind"))
        return mounts

    def run(self, harness: str, ctx_path: Path, workspace: Path, timeout_s: int,
            extra_rw: tuple[Path, ...] = ()) -> SandboxOutcome:
        import docker

        image = IMAGES[harness]
        mounts = self.mounts(ctx_path.parent, extra_rw)
        network = os.environ.get("SANDBOX_NETWORK_CLAUDE_CODE", "aep_egress") if harness in DIRECT else self.network
        env = {"PYTHONUNBUFFERED": "1"}
        if harness in DIRECT:
            env.update({k: os.environ[k] for k in PASSTHROUGH_ENV if os.environ.get(k)})
        container = None
        try:
            container = self.client.containers.run(
                image, command=["python", "-m", "evalworker.adapters.run", str(ctx_path), harness],
                working_dir=str(workspace), mounts=mounts, network=network,
                mem_limit="2g", nano_cpus=1_000_000_000, detach=True,
                environment=env,
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
            tail = container.logs(tail=15).decode(errors="replace").strip()[-1500:]
            if code == 137 and not timed_out:
                return SandboxOutcome(ok=False, detail="container killed (out of memory?)")
            return SandboxOutcome(ok=code == 0 or timed_out, timed_out=timed_out,
                                  detail=f"exit {code}" + ("\n" + tail if code != 0 and tail else ""))
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
