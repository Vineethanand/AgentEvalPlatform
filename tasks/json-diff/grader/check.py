"""Grader for json-diff: the reply must list the keys added, removed and changed between two JSON files."""
import json
import re


def _json_in(text):
    """First JSON object in the answer (tolerates ```json fences and surrounding prose).

    Agents often wrap JSON in a code fence or add a sentence around it. Fence markers are removed, then every
    "{" is tried in turn as the start of a JSON value, so a stray brace in the prose does not hide the object.
    """
    text = re.sub(r"```(?:json)?", "", text or "")
    start = text.find("{")
    while start != -1:
        try:
            return json.JSONDecoder().raw_decode(text[start:])[0]
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
    raise ValueError("no JSON object in the answer")


EXPECTED = {"added": ["origin"], "removed": ["legacy"], "changed": ["dims", "price"]}


def check(workspace, final_answer):  # pylint: disable=unused-argument
    """Require the reply's JSON object to equal the expected added / removed / changed lists exactly."""
    try:
        data = _json_in(final_answer)
    except ValueError as e:
        return [{"name": "answer contains a JSON object", "passed": False, "detail": str(e)}]
    return [{"name": "added, removed and changed are right", "passed": data == EXPECTED, "detail": f"got {data}"}]
