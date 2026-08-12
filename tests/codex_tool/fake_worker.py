"""Small subprocess target used by job lifecycle tests."""

import time


def main() -> None:
    time.sleep(60)


if __name__ == "__main__":
    main()
