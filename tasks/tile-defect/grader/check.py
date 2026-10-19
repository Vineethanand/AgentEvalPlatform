import json
import re

EXPECTED = {"row": 21, "col": 13, "tile_row": 5, "tile_col": 3}


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
    d = data if isinstance(data, dict) else {}
    return [
        {"name": "answer contains a JSON object", "passed": True},
        {"name": "pixel row and col are right", "passed": (d.get("row"), d.get("col")) == (EXPECTED["row"], EXPECTED["col"]),
         "detail": f"got {d.get('row')},{d.get('col')}; expected {EXPECTED['row']},{EXPECTED['col']}"},
        {"name": "tile is right", "passed": (d.get("tile_row"), d.get("tile_col")) == (EXPECTED["tile_row"], EXPECTED["tile_col"]),
         "must": False},
    ]
