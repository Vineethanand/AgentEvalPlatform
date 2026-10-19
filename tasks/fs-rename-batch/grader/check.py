EXPECTED = {"2024-05-01_1.jpg", "2024-05-03_2.jpg", "2023-12-24_7.jpg", "2025-01-09_12.jpg"}


def check(workspace, final_answer):
    d = workspace / "photos"
    names = {p.name for p in d.iterdir()} if d.exists() else set()
    return [
        {"name": "all photos renamed", "passed": EXPECTED <= names, "detail": f"have {sorted(names)}"},
        {"name": "no old names left", "passed": not any(n.startswith("IMG_") for n in names)},
        {"name": "nothing deleted", "passed": len(names) >= 4},
    ]
