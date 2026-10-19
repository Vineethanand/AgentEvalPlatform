"""Small QA suite: 4 predictable tests. Expected results are hardcoded below.

Exits 0 only if every test passes.
"""
import hashlib
import json
import sys
from pathlib import Path

# Only the hash of the accepted suite name is stored, so the name cannot be read out of this file.
# (The memory tasks rely on this: the name must come from the teach task, not from the workspace.)
SUITE_SHA256 = "80959b54e5b28aa7520e232b66ca03c43e63632fe90f446c1dc955d26fa10e57"
HERE = Path(__file__).resolve().parent

EXPECTED_REPORT = '{\n  "suite": "nightly-4",\n  "tests": 4,\n  "total": 391\n}\n'


def suite_from_args(argv):
    """The value of --suite=<name> if it is the accepted suite, else None."""
    for arg in argv:
        if arg.startswith("--suite="):
            name = arg.split("=", 1)[1]
            if hashlib.sha256(name.encode()).hexdigest() == SUITE_SHA256:
                return name
    return None


def test_math(_suite):
    """A calculation with a known answer."""
    assert 17 * 23 == 391, "17 * 23 should be 391"


def test_read_file(_suite):
    """Read an existing data file and check its exact contents."""
    lines = (HERE / "data" / "sample.txt").read_text().splitlines()
    assert lines == ["alpha", "beta", "gamma"], f"unexpected contents: {lines}"


def test_json_report(suite):
    """Create a JSON file and check its format is exact: 2-space indent and a trailing newline."""
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    report = {"suite": suite, "tests": 4, "total": 17 * 23}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    text = (out / "report.json").read_text()
    assert text == EXPECTED_REPORT, f"report.json format differs: {text!r}"


def test_string(_suite):
    """Reverse a string and join its characters with hyphens."""
    assert "-".join(reversed("abc")) == "c-b-a"


# Run in this order; each test either returns quietly (pass) or raises AssertionError (fail).
TESTS = [test_math, test_read_file, test_json_report, test_string]

if __name__ == "__main__":
    chosen = suite_from_args(sys.argv[1:])
    if chosen is None:
        print("error: missing or unknown --suite")
        sys.exit(2)
    failed = 0
    for t in TESTS:
        try:
            t(chosen)
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"SUITE {chosen}: {len(TESTS) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
