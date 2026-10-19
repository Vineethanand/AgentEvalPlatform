"""Grader for fs-rename-batch: the photos must be renamed from IMG_* to date-based names, none deleted."""
EXPECTED = {"2024-05-01_1.jpg", "2024-05-03_2.jpg", "2023-12-24_7.jpg", "2025-01-09_12.jpg"}


def check(workspace, final_answer):  # pylint: disable=unused-argument
    """Look at the file names in photos/: all new names present, no old IMG_ names left, nothing removed."""
    d = workspace / "photos"
    names = {p.name for p in d.iterdir()} if d.exists() else set()
    return [
        {"name": "all photos renamed", "passed": EXPECTED <= names, "detail": f"have {sorted(names)}"},
        {"name": "no old names left", "passed": not any(n.startswith("IMG_") for n in names)},
        {"name": "nothing deleted", "passed": len(names) >= 4},
    ]
