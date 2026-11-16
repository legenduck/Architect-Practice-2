import sys

from practice import main

if __name__ == "__main__":
    # Keep redirected Korean diagnostics readable on Windows as well.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
