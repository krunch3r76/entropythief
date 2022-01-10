#!/usr/bin/env python3
# provides a generator class that produces a bit on demand utilizing entropythief's pipe_reader

from pathlib import Path
import os,sys
PATH_TO_PIPE_READERS=Path(os.path.dirname(__file__)).resolve().parents[0]
sys.path.append(str(PATH_TO_PIPE_READERS))

from pipe_reader import PipeReader
# review, too complex to import
try:
    from bitgenerator import BitGenerator
except:
    from .bitgenerator import BitGenerator

class EntropyBitReader:
    """encapsulate a generic bitreader to utilize et's pipe reader"""

    def __init__(self, kCountBytesToBuffer=10000):
        self._kCountBytesToBuffer=kCountBytesToBuffer
        self._readerPipe = PipeReader()
        self._bitgenerator=BitGenerator(
                lambda: self._readerPipe.read(self._kCountBytesToBuffer)
                , self._kCountBytesToBuffer
                )

    
    def __iter__(self):
        pass


    def __next__(self):
        """get the next 1 or 0 from the internal bitgenerator"""
        return next(self._bitgenerator)

if __name__ == '__main__':
    print("reading bits from the entropy stream. first bit printed. press enter for next")
    ebr=EntropyBitReader(1)
    while True:
        try:
            print(next(ebr), end="")
            input()
        except (KeyboardInterrupt, EOFError):
            print("\n\033[1mall's well that end's well!\033[0m")
            break
