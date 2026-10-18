import re

TOTAL_KM = round((12.5 + 30.0 + 7.25 + 18.0) * 1.609344, 1)  # 109.0


def check(workspace, final_answer):
    f = workspace / "summary.txt"
    if not f.exists():
        return [{"name": "summary.txt exists", "passed": False}]
    text = f.read_text().lower()
    nums = [float(x) for x in re.findall(r"\d+\.\d", text)]
    return [
        {"name": "uses kilometres", "passed": "km" in text or "kilomet" in text},
        {"name": "not miles", "passed": "mile" not in text},
        {"name": f"total is {TOTAL_KM} with one decimal", "passed": TOTAL_KM in nums, "detail": text.strip()},
    ]
