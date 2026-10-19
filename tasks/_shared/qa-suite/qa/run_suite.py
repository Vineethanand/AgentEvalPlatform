"""Small QA suite: 4 predictable tests. Expected results are hardcoded below.

Run:  python qa/run_suite.py --suite=nightly-4
Exits 0 only if every test passes.
"""
import json
import sys
from pathlib import Path

SUITE = "nightly-4"
HERE = Path(__file__).resolve().parent

EXPECTED_REPORT = '{\n  "suite": "nightly-4",\n  "tests": 4,\n  "total": 391\n}\n'


def test_math():
    assert 17 * 23 == 391, "17 * 23 should be 391"


def test_read_file():
    lines = (HERE / "data" / "sample.txt").read_text().splitlines()
    assert lines == ["alpha", "beta", "gamma"], f"unexpected contents: {lines}"


def test_json_report():
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    report = {"suite": SUITE, "tests": 4, "total": 17 * 23}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    text = (out / "report.json").read_text()
    assert text == EXPECTED_REPORT, f"report.json format differs: {text!r}"


def test_string():
    assert "-".join(reversed("abc")) == "c-b-a"


TESTS = [test_math, test_read_file, test_json_report, test_string]

if __name__ == "__main__":
    if f"--suite={SUITE}" not in sys.argv[1:]:
        print("error: missing or unknown --suite")
        sys.exit(2)
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"SUITE {SUITE}: {len(TESTS) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
