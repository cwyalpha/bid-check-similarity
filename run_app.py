import sys

from checksim.cli import main as cli_main
from checksim.ui import main as gui_main


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit(cli_main(sys.argv[1:]))
    gui_main()
