import json
import re

ORDER = ["J02", "J09", "J03", "J19", "J13", "J16", "J05", "J12", "J07", "J14", "J04", "J20", "J01", "J18", "J08", "J06", "J10", "J15", "J11", "J17"]
PEAK = 7


def _json_in(text):
    text = re.sub(r"```(?:json)?", "", text or "")
    start = text.find("{")
    while start != -1:
        try:
            return json.JSONDecoder().raw_decode(text[start:])[0]
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
    raise ValueError("no JSON object in the answer")


def check(workspace, final_answer):
    try:
        data = _json_in(final_answer)
    except ValueError as e:
        return [{"name": "answer contains a JSON object", "passed": False, "detail": str(e)}]
    got = data.get("order") if isinstance(data, dict) else None
    wrong = sum(1 for a, b in zip(got or [], ORDER) if a != b) if isinstance(got, list) else len(ORDER)
    return [
        {"name": "answer contains a JSON object", "passed": True},
        {"name": "order is exactly right", "passed": got == ORDER, "detail": f"{wrong} positions differ"},
        {"name": f"peak concurrency is {PEAK}", "passed": isinstance(data, dict) and data.get("peak_concurrency") == PEAK,
         "detail": f"got {data.get('peak_concurrency') if isinstance(data, dict) else None}"},
    ]
