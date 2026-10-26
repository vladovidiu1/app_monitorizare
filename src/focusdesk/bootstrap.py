"""Bootstrap standard-library-only pentru multiprocessing/fereastră fără consolă."""

import multiprocessing
import os
import sys


def prepare_multiprocessing() -> None:
    # Native wrappers may need fileno() even in a PyInstaller --windowed child.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    multiprocessing.freeze_support()
