import json

EXPECTED = {"version": 2, "database": {"host": "db.internal", "port": 5432}, "debug": True,
            "features": ["search", "export"]}


def check(workspace, final_answer):
    try:
        data = json.loads((workspace / "config.json").read_text())
    except Exception as e:  # noqa: BLE001
        return [{"name": "config.json readable", "passed": False, "detail": str(e)}]
    return [{"name": "matches v2", "passed": data == EXPECTED, "detail": f"got {data}"}]
