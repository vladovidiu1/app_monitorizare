from focusdesk.bootstrap import prepare_multiprocessing

if __name__ == "__main__":
    prepare_multiprocessing()
    from focusdesk.main import main

    raise SystemExit(main())
