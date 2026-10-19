"""Grader for m1-use-units (memory chain M1, use step): the total must be in the remembered unit, dodos.

The unit and its conversion formula (dodos = sqrt(x) + 56 * ln(x), x in miles, applied to the total) appear only
in the teach task, so an agent without memory has no way to produce this number.
"""
import math
import re

TOTAL_MILES = 12.5 + 30.0 + 7.25 + 18.0
TOTAL_DODOS = round(math.sqrt(TOTAL_MILES) + 56 * math.log(TOTAL_MILES), 1)  # 244.3


def check(workspace, final_answer):  # pylint: disable=unused-argument
    """Require the reply to say "dodos", not mention miles, and contain the total to one decimal place.

    The conversion is applied to the weekly total. Converting each trip and adding the results gives a
    different number (the formula is not linear), so that wrong method fails the number check.
    """
    text = (final_answer or "").lower()
    nums = [float(x) for x in re.findall(r"\d+\.\d", text)]
    return [
        {"name": "uses dodos", "passed": "dodo" in text},
        {"name": "not miles", "passed": "mile" not in text},
        {"name": f"total is {TOTAL_DODOS} with one decimal", "passed": TOTAL_DODOS in nums, "detail": text.strip()},
    ]
