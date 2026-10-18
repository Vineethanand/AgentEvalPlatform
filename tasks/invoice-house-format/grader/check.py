import json
import re


def _json_in(text):
    """First JSON object in the answer (tolerates ```json fences and surrounding prose)."""
    text = re.sub(r"```(?:json)?", "", text or "")
    start = text.find("{")
    while start != -1:
        try:
            return json.JSONDecoder().raw_decode(text[start:])[0]
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
    raise ValueError("no JSON object in the answer")


EXPECTED = {'1042': {'inv_no': '1042', 'vendor': 'BLUE RIVER SUPPLIES', 'date': '2025-03-03', 'total_cents': 123450, 'currency': 'USD'}, '1043': {'inv_no': '1043', 'vendor': 'KITE & CO', 'date': '2025-04-17', 'total_cents': 8900, 'currency': 'EUR'}}


def check(workspace, final_answer):
    try:
        data = _json_in(final_answer)
    except ValueError as e:
        return [{"name": "answer contains a JSON object", "passed": False, "detail": str(e)}]
    return [
        {"name": f"{no} matches house format", "passed": isinstance(data, dict) and data.get(no) == exp,
         "detail": f"got {data.get(no) if isinstance(data, dict) else data}"}
        for no, exp in EXPECTED.items()
    ]
