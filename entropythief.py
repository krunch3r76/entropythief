#!/usr/bin/env python3
import sys

try:
    import yapapi

    version_list = yapapi.__version__.split(".")
    if int(version_list[1]) < 9:
        print(
            f"Sorry, the version of a required python module, yapapi, is outdated. Currently it is {yapapi.__version__}. It needs to be updated to at least version 0.9.1 to run."
        )
        sys.exit(1)
except ModuleNotFoundError:
    print(
        "Uh oh, did you forget to install the requirements? I could not find a required module: yapapi! Please see the readme for direction."
    )
    sys.exit(1)

from entropythief.application import main
import entropythief.utils
from entropythief.utils import (
    build_parser,
    print_env_info,
    TEXT_COLOR_YELLOW,
    TEXT_COLOR_DEFAULT,
)

parser = build_parser("pilfer entropy stashes from providers")
args = parser.parse_args()
print_env_info(args)
try:
    input(
        "to change any of the settings, ctrl-c and pass the arguments desired on the command line.\n"
        f"for example, \033[4m./entropythief.py --payment-network {TEXT_COLOR_YELLOW}polygon{TEXT_COLOR_DEFAULT}\033[4m --subnet-tag {TEXT_COLOR_YELLOW}public-beta{TEXT_COLOR_DEFAULT}.\n"
        "press enter to accept the above arguments and proceed"
    )
    print("")
except KeyboardInterrupt:
    print("\n\033[1msure thing boss, see you in a few\033[0m")
    sys.exit(0)
main(args)
