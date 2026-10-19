import re


def check(workspace, final_answer):
    lines = [l for l in (final_answer or "").strip().splitlines() if l.strip()]
    last = lines[-1].strip() if lines else ""
    nums = re.findall(r"\d+", last)
    return [{"name": "reports 2 failing tests", "passed": nums == ["2"], "detail": last[:120]}]
