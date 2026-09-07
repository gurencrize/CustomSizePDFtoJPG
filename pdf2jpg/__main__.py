"""``python -m pdf2jpg`` で CLI を起動する。``--gui`` で GUI を開く."""

import sys

if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv and argv[0] == "--gui":
        from pdf2jpg.gui import main
        raise SystemExit(main(argv[1:]))
    from pdf2jpg.cli import main
    raise SystemExit(main(argv))
