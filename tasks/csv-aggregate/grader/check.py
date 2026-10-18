import json

EXPECTED = {"East": 32.5, "North": 159.97, "South": 298.4, "West": 56.0}


def check(workspace, final_answer):
    f = workspace / "report.json"
    if not f.exists():
        return [{"name": "report.json exists", "passed": False}]
    try:
        data = json.loads(f.read_text())
    except json.JSONDecodeError as e:
        return [{"name": "report.json is valid JSON", "passed": False, "detail": str(e)}]
    totals_ok = isinstance(data, dict) and set(data) == set(EXPECTED) and all(
        abs(float(data[k]) - v) < 0.006 for k, v in EXPECTED.items())
    return [
        {"name": "report.json exists", "passed": True},
        {"name": "totals match", "passed": totals_ok, "detail": f"got {data}, expected {EXPECTED}"},
        {"name": "regions sorted", "passed": isinstance(data, dict) and list(data) == sorted(data), "must": False},
    ]
