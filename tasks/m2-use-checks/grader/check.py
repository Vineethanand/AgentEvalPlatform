def check(workspace, final_answer):
    f = workspace / "checks.txt"
    text = f.read_text().strip() if f.exists() else ""
    return [{"name": "checks.txt has the passing line", "passed": text.endswith("ALL CHECKS PASSED ci-7"), "detail": text[:200]}]
