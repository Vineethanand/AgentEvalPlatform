EXPECTED = [
    "# app settings",
    "APP_NAME=shop",
    "DEBUG=false",
    "PORT=9090",
    "DB_URL=postgres://localhost/shop",
    "LOG_LEVEL=warn",
]


def check(workspace, final_answer):
    path = workspace / "settings.env"
    if not path.exists():
        return [{"name": "settings.env exists", "passed": False}]
    lines = [l.rstrip() for l in path.read_text().splitlines() if l.strip()]
    return [{"name": "file has exactly the expected lines", "passed": lines == EXPECTED, "detail": f"got {lines}"}]
