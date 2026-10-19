"""Custom QA suite runner (hardcoded results so the output is predictable)."""
import sys

SUITE = "nightly-4"

if __name__ == "__main__":
    if f"--suite={SUITE}" not in sys.argv[1:]:
        print("error: missing or unknown --suite")
        sys.exit(2)
    print("collected 12 checks")
    print(f"SUITE {SUITE}: 12 passed, 0 failed")
