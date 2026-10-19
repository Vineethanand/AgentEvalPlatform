"""Grader for env-file-update: settings.env must contain exactly the expected settings, in order."""
EXPECTED = [
    "# app settings",
    "APP_NAME=shop",
    "DEBUG=false",
    "PORT=9090",
    "DB_URL=postgres://localhost/shop",
    "LOG_LEVEL=warn",
]


def check(workspace, final_answer):  # pylint: disable=unused-argument
    """Compare the file's non-empty lines (trailing spaces ignored) with the expected lines."""
    path = workspace / "settings.env"
    if not path.exists():
        return [{"name": "settings.env exists", "passed": False}]
    lines = [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [{"name": "file has exactly the expected lines", "passed": lines == EXPECTED, "detail": f"got {lines}"}]
