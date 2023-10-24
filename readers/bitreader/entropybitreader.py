#!/usr/bin/env python3
# provides a generator class that produces a bit on demand utilizing entropythief's pipe_reader
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)

from pathlib import Path
import os, sys

PATH_TO_PIPE_READERS = Path(os.path.dirname(__file__)).resolve().parents[0]
sys.path.append(str(PATH_TO_PIPE_READERS))

from pipe_reader import PipeReader

# review, too complex to import
try:
    from bitgenerator import BitGenerator
except:
    from .bitgenerator import BitGenerator


class EntropyBitReader:
    """encapsulate a generic bitreader to utilize et's pipe reader"""

    def __init__(self, countBytesToBuffer=(2**16), pipe_reader=None):
        """
        pre: with defaults, entropy source should be able to eventually have half a megabyte of
         bits read from it
        in:
            countBytesToBuffer: how many bytes to read into memory from entropy source at a time
            pipe_reader: optionally use a pipe reader already instantiated, must implement .read()

        post:
            _kCountBytesToBuffer: arbitrarily sets read size to help mitigate overhead from too many lowlevel reads
            _readerPipe: an new instance of PipeReader
            _bitgenerator: a new instance of BitGenerator initialized with the count and pipereader
        """
        self._kCountBytesToBuffer = countBytesToBuffer
        self._readerPipe = PipeReader() if pipe_reader is None else pipe_reader
        self._bitgenerator = BitGenerator(
            self._readerPipe,
            self._kCountBytesToBuffer,
        )

    def __call__(self):
        """provide an alternative to next() to directly get the next random bit

        pre: none
        in: none
        post: one less bit in self._bitgenerator's bitpool
        """
        return self.__next__()

    def __iter__(self):
        """This method makes EntropyBitReader iterable

        pre: none
        in: none
        post: _bitgenerator less 1 bit
        out: 1 or 0
        """
        while True:
            yield self.__next__()

    def __next__(self):
        """get the next 1 or 0 from the internal bitgenerator

        pre: none
        in: none
        post: _bitgenerator less 1 bit
        out: 1 or 0
        """
        return next(self._bitgenerator)


if __name__ == "__main__":
    print(
        "buffering bits from the entropy stream. first bit will print momentarily. press enter for next"
    )
    ebr = EntropyBitReader()
    while True:
        try:
            print(next(ebr), end="")
            input()
        except (KeyboardInterrupt, EOFError):
            print("\n\033[1mall's well that end's well!\033[0m")
            break
