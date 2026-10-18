def check(workspace, final_answer):
    lines = [x.strip() for x in (final_answer or "").strip().splitlines() if x.strip()]
    last = lines[-1] if lines else ""
    return [{"name": "answer is the passing line", "passed": "ALL CHECKS PASSED ci-7" in last, "detail": last[:200]}]
