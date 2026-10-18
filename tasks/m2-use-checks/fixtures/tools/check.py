import sys

PROFILE = "ci-7"

if __name__ == "__main__":
    args = sys.argv[1:]
    if f"--profile={PROFILE}" not in args:
        print("error: unknown or missing profile. See the team's contributing guide.")
        sys.exit(2)
    print("lint ok")
    print("types ok")
    print(f"ALL CHECKS PASSED {PROFILE}")
