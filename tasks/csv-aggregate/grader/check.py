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


EXPECTED = {"East": 32.5, "North": 159.97, "South": 298.4, "West": 56.0}


def check(workspace, final_answer):
    try:
        data = _json_in(final_answer)
    except ValueError as e:
        return [{"name": "answer contains a JSON object", "passed": False, "detail": str(e)}]
    totals_ok = isinstance(data, dict) and set(data) == set(EXPECTED) and all(
        isinstance(data[k], (int, float)) and abs(float(data[k]) - v) < 0.006 for k, v in EXPECTED.items())
    return [
        {"name": "answer contains a JSON object", "passed": True},
        {"name": "totals match", "passed": totals_ok, "detail": f"got {data}, expected {EXPECTED}"},
        {"name": "regions sorted", "passed": isinstance(data, dict) and list(data) == sorted(data), "must": False},
    ]
