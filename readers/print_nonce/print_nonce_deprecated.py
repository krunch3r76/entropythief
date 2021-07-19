#!/usr/bin/python3
# print_nonce.py
# grabs an 8 byte (64bit) value from the entropy loot and prints it
# author: krunch3r (biz@u26a4.com)

"""
    an example script that uses the _pipe API that comes along with entropythief
    to read the random bits from the named pipe into which the entropy has been placed
    it utilizes the public coroutine function _pipe.harness_entropy, which has
    the signature (<payload length in bytes>, <payload handler>)
"""

import os
import sys

PATH_TO_PIPE_MODULE=os.path.dirname(__file__) + "/.."
sys.path.append(PATH_TO_PIPE_MODULE)
import _pipe # _pipe.harness_entropy

#########################################
#       _print_64bit_integer             #
#########################################
def _print_64bit_integer(payload, endianness="little"):
    int64 = int.from_bytes(payload, endianness)
    print(int64)



#########################################
#               main                    #
#########################################
if __name__ == "__main__":
    try:
        coro_harness_entropy = _pipe.harness_entropy(8, _print_64bit_integer)
        next(coro_harness_entropy)
        for _ in range(1):
            coro_harness_entropy.send(None)
    except KeyboardInterrupt:
        print("Goodbye")
    finally:
        coro_harness_entropy.close()

