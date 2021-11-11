# utils
# this code has been taken from https://github.com/golemfactory/yapapi/tree/master/examples

"""Utilities for yapapi example scripts."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import tempfile


import colorama  # type: ignore


TEXT_COLOR_RED = "\033[31;1m"
TEXT_COLOR_GREEN = "\033[32;1m"
TEXT_COLOR_YELLOW = "\033[33;1m"
TEXT_COLOR_BLUE = "\033[34;1m"
TEXT_COLOR_MAGENTA = "\033[35;1m"
TEXT_COLOR_CYAN = "\033[36;1m"
TEXT_COLOR_WHITE = "\033[37;1m"

TEXT_COLOR_DEFAULT = "\033[0m"

colorama.init()


def build_parser(description: str):
    current_time_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S%z")
    default_log_path = "entropythief-yapapi.log"
    # default_log_path = Path(tempfile.gettempdir()) / f"yapapi_{current_time_str}.log"

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--driver", help="Payment driver name, for example `zksync`")
    parser.add_argument("--network", help="Network name, for example `rinkeby`")
    parser.add_argument(
        "--subnet-tag", default="devnet-beta", help="Subnet name; default: %(default)s"
    )
    parser.add_argument(
        "--log-file",
        default=str(default_log_path),
        help="Log file for YAPAPI; default: %(default)s",
    )
    parser.add_argument("--enable-logging", help="whether to log to the above log-file {0, 1} DEFAULT: 1", default=1
                        , type=int)
    parser.add_argument("--rdrand", default=1, help="whether to use rdrand cpu instruction (limits providers) {0, 1} DEFAULT: 1", type=int)
    parser.add_argument("--start-paused", default=0, help="whether to pause instead of beginning execution immediately")
    return parser
