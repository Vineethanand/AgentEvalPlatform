"""A sandbox must see only its own trial folder, never the whole trials volume (no state leaks between trials)."""
import unittest
from pathlib import Path

from evalworker.sandbox import DockerSandbox


def sandbox(volume):
    sb = DockerSandbox.__new__(DockerSandbox)  # skip docker.from_env(): these tests need no Docker daemon
    sb.volume, sb.data_root = volume, "/data"
    return sb


class MountTests(unittest.TestCase):
    def test_volume_mode_mounts_only_this_trials_subfolder(self):
        mounts = sandbox("aep_trialdata").mounts(Path("/data/trials/t1/attempt-1"))
        self.assertEqual(len(mounts), 1)
        m = mounts[0]
        self.assertEqual(m["Target"], "/data/trials/t1/attempt-1")
        self.assertEqual(m["Source"], "aep_trialdata")
        self.assertEqual(m["VolumeOptions"]["Subpath"], "trials/t1/attempt-1")

    def test_carry_chain_adds_only_the_shared_memory_home(self):
        mounts = sandbox("aep_trialdata").mounts(
            Path("/data/trials/t2/attempt-1"), (Path("/data/trials/chains/t1-ab12/home"),))
        self.assertEqual(sorted(m["VolumeOptions"]["Subpath"] for m in mounts),
                         ["trials/chains/t1-ab12/home", "trials/t2/attempt-1"])

    def test_no_mount_covers_the_trials_root(self):
        for m in sandbox("aep_trialdata").mounts(Path("/data/trials/t1/attempt-1")):
            self.assertNotIn(m["Target"], ("/data", "/data/trials"))
            self.assertNotEqual(m["VolumeOptions"]["Subpath"], "")


if __name__ == "__main__":
    unittest.main()
