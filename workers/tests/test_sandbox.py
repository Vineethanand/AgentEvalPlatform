"""A sandbox must see only its own trial folder, never the whole trials volume (no state leaks between trials)."""
import unittest
from pathlib import Path

from evalworker.sandbox import DockerSandbox


def sandbox(volume):
    """A DockerSandbox for ``volume`` without a Docker connection, to test only how it builds mounts."""
    sb = DockerSandbox.__new__(DockerSandbox)  # skip docker.from_env(): these tests need no Docker daemon
    sb.volume, sb.data_root = volume, "/data"
    return sb


class MountTests(unittest.TestCase):
    """A trial may only ever see its own folders."""

    def test_volume_mode_mounts_only_this_trials_subfolder(self):
        """In named-volume mode exactly one mount, of this attempt's sub-folder, at its own path."""
        mounts = sandbox("aep_trialdata").mounts(Path("/data/trials/t1/attempt-1"))
        self.assertEqual(len(mounts), 1)
        m = mounts[0]
        self.assertEqual(m["Target"], "/data/trials/t1/attempt-1")
        self.assertEqual(m["Source"], "aep_trialdata")
        self.assertEqual(m["VolumeOptions"]["Subpath"], "trials/t1/attempt-1")

    def test_carry_chain_adds_only_the_shared_memory_home(self):
        """A memory chain adds the shared home folder as a second mount, and nothing else."""
        mounts = sandbox("aep_trialdata").mounts(
            Path("/data/trials/t2/attempt-1"), (Path("/data/trials/chains/t1-ab12/home"),))
        self.assertEqual(sorted(m["VolumeOptions"]["Subpath"] for m in mounts),
                         ["trials/chains/t1-ab12/home", "trials/t2/attempt-1"])

    def test_no_mount_covers_the_trials_root(self):
        """No mount exposes /data or /data/trials, which would reveal other trials' folders."""
        for m in sandbox("aep_trialdata").mounts(Path("/data/trials/t1/attempt-1")):
            self.assertNotIn(m["Target"], ("/data", "/data/trials"))
            self.assertNotEqual(m["VolumeOptions"]["Subpath"], "")


if __name__ == "__main__":
    unittest.main()
