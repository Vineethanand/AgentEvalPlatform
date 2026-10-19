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


EXPECTED = {"added": ["origin"], "removed": ["legacy"], "changed": ["dims", "price"]}


def check(workspace, final_answer):
    try:
        data = _json_in(final_answer)
    except ValueError as e:
        return [{"name": "answer contains a JSON object", "passed": False, "detail": str(e)}]
    return [{"name": "added, removed and changed are right", "passed": data == EXPECTED, "detail": f"got {data}"}]
