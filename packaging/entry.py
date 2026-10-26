"""Punct de intrare pentru PyInstaller (importuri absolute, fara pachet relativ)."""

import sys

from focusdesk.main import main

if __name__ == "__main__":
    sys.exit(main())
