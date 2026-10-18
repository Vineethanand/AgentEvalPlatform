import re

EXPECTED = {
    "IMG_1.jpg": "2024-05-01_1.jpg",
    "IMG_2.jpg": "2024-05-03_2.jpg",
    "IMG_7.jpg": "2023-12-24_7.jpg",
    "IMG_12.jpg": "2025-01-09_12.jpg",
}


def check(workspace, final_answer):
    pairs = dict(re.findall(r"([\w.-]+\.jpg)\W*(?:->|=>|→|to)\W*([\w.-]+\.jpg)", final_answer or "", re.I))
    wrong = {k: pairs.get(k) for k, v in EXPECTED.items() if pairs.get(k) != v}
    return [
        {"name": "every photo has the expected new name", "passed": not wrong,
         "detail": f"wrong or missing: {wrong}" if wrong else ""},
        {"name": "no extra mappings", "passed": set(pairs) <= set(EXPECTED), "must": False,
         "detail": f"unexpected: {sorted(set(pairs) - set(EXPECTED))}"},
    ]
