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
    parser.add_argument(
        "--payment-driver",
        default="erc20",
        help="Payment driver name, `erc20`, `zksync`; default: \033[1m%(default)s\033[0m",
    )
    parser.add_argument(
        "--payment-network",
        default="holesky",
        help="Network name, e.g. `mainnet`, `rinkeby`, `goerli`, `holesky`, `polygon`, `mumbai`; default: \033[1m%(default)s\033[0m",
    )
    parser.add_argument(
        "--subnet-tag",
        default="public",
        help="Subnet name e.g. `public`; default: \033[1m%(default)s\033[0m",
    )
    parser.add_argument(
        "--log-file",
        default=str(default_log_path),
        help="Log file for YAPAPI; default: \033[2m%(default)s\033[0m",
    )
    parser.add_argument(
        "--disable-logging",
        action="store_true",
        help="log to the stderr and the above log-file",
    )
    parser.add_argument(
        "--start-paused",
        action="store_true",
        help="start paused instead of beginning execution immediately",
    )
    parser.add_argument(
        "--conceal-view",
        action="store_true",
        help="do not stream bytes to console - prevents backlog in memory",
    )
    return parser


def print_env_info(args):
    from yapapi import __version__ as yapapi_version

    print(
        f"yapapi version:\t{TEXT_COLOR_BLUE}{yapapi_version}{TEXT_COLOR_DEFAULT}\n"
        f"Using subnet:\t{TEXT_COLOR_YELLOW}{args.subnet_tag}{TEXT_COLOR_DEFAULT}\n"
        f"payment driver:\t{TEXT_COLOR_YELLOW}{args.payment_driver}{TEXT_COLOR_DEFAULT}\n, "
        f"and network:\t{TEXT_COLOR_YELLOW}{args.payment_network}{TEXT_COLOR_DEFAULT}"
    )
    print(f"logging:\t{TEXT_COLOR_YELLOW}", end="")
    if not args.disable_logging:
        print(
            f"{args.log_file} {TEXT_COLOR_DEFAULT}and {TEXT_COLOR_YELLOW}./stderr",
            end="",
        )
    else:
        print(f"disabled", end="")
    print(f"{TEXT_COLOR_DEFAULT}")

    print(f"entropy source:\t{TEXT_COLOR_YELLOW}", end="")
    print(f"RDSEED", end="")

    print(f"{TEXT_COLOR_DEFAULT}")
