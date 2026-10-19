import json

EXPECTED = {
    "1042": {"inv_no": "1042", "vendor": "BLUE RIVER SUPPLIES", "date": "2025-03-03", "total_cents": 123450, "currency": "USD"},
    "1043": {"inv_no": "1043", "vendor": "KITE & CO", "date": "2025-04-17", "total_cents": 8900, "currency": "EUR"},
}


def check(workspace, final_answer):
    checks = []
    for no, exp in EXPECTED.items():
        f = workspace / "out" / f"{no}.json"
        try:
            got = json.loads(f.read_text())
        except Exception as e:  # noqa: BLE001
            checks.append({"name": f"out/{no}.json", "passed": False, "detail": str(e)})
            continue
        checks.append({"name": f"out/{no}.json matches house format", "passed": got == exp, "detail": f"got {got}"})
    return checks
