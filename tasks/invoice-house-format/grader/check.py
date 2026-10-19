"""Grader for invoice-house-format: each invoice must be converted to a JSON file in the house format.

The format (upper-case vendor, amounts in cents, ISO dates) is only described in the invoice-format skill.
"""
import json

EXPECTED = {
    "1042": {"inv_no": "1042", "vendor": "BLUE RIVER SUPPLIES", "date": "2025-03-03", "total_cents": 123450,
             "currency": "USD"},
    "1043": {"inv_no": "1043", "vendor": "KITE & CO", "date": "2025-04-17", "total_cents": 8900,
             "currency": "EUR"},
}


def check(workspace, final_answer):  # pylint: disable=unused-argument
    """Read out/<invoice number>.json for each invoice and require it to equal the expected document."""
    checks = []
    for no, exp in EXPECTED.items():
        f = workspace / "out" / f"{no}.json"
        try:
            got = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            checks.append({"name": f"out/{no}.json", "passed": False, "detail": str(e)})
            continue
        checks.append({"name": f"out/{no}.json matches house format", "passed": got == exp, "detail": f"got {got}"})
    return checks
