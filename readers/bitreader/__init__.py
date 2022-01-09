# provides a generator class that produces a bit on demand utilizing entropythief's pipe_reader

from pipe_reader import PipeReader
from . bitgenerator import BitGenerator

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

