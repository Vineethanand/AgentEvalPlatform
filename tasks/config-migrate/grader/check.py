"""Grader for config-migrate: config.json must have been migrated to the version 2 layout."""
import json

EXPECTED = {"version": 2, "database": {"host": "db.internal", "port": 5432}, "debug": True,
            "features": ["search", "export"]}


def check(workspace, final_answer):  # pylint: disable=unused-argument
    """Load the workspace's config.json and require it to equal the expected version 2 document."""
    try:
        data = json.loads((workspace / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [{"name": "config.json readable", "passed": False, "detail": str(e)}]
    return [{"name": "matches v2", "passed": data == EXPECTED, "detail": f"got {data}"}]
