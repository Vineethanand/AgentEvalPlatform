import re
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).parent / "tests"


def check(workspace, final_answer):
    """Extract the returned daterange.py, put it next to the hidden tests and run them."""
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", final_answer or "", re.S)
    code = next((b for b in blocks if "def days_between" in b), None)
    if code is None:
        return [{"name": "answer contains daterange.py", "passed": False, "detail": "no python block with days_between"}]
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "daterange.py").write_text(code)
        (Path(tmp) / "_hidden_tests").mkdir()
        for f in TESTS.glob("*.py"):
            (Path(tmp) / "_hidden_tests" / f.name).write_text(f.read_text())
        try:
            p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "_hidden_tests", "-t", "."],
                               cwd=tmp, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return [{"name": "hidden tests pass", "passed": False, "detail": "timed out"}]
    return [{"name": "hidden tests pass", "passed": p.returncode == 0, "detail": (p.stderr + p.stdout)[-800:]}]
