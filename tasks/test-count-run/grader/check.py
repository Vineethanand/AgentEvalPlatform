"""Grader for test-count-run: the last line of the reply must report the number of failing tests (2)."""
import re


def check(workspace, final_answer):  # pylint: disable=unused-argument
    """Take the reply's last non-empty line; it must contain exactly one number, and that number must be 2."""
    lines = [line for line in (final_answer or "").strip().splitlines() if line.strip()]
    last = lines[-1].strip() if lines else ""
    nums = re.findall(r"\d+", last)
    return [{"name": "reports 2 failing tests", "passed": nums == ["2"], "detail": last[:120]}]
