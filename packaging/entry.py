"""Punct de intrare pentru PyInstaller (importuri absolute, fara pachet relativ)."""

from focusdesk.bootstrap import prepare_multiprocessing

if __name__ == "__main__":
    # Must run before importing Tk/application code: frozen --multiprocessing-fork
    # invocations are redirected to the worker instead of opening another window.
    prepare_multiprocessing()
    from focusdesk.main import main

    raise SystemExit(main())
