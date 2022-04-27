# randbit.py
# implements a random bit generator

import random
import sys


class BitGenerator:
    """generate a bit (value of 1 or 0) upon every call"""

    """
    _bitstring
    _cb_returnRandomNumber
    _k_bytelength
    _k_bitstringlen
    _cb_returnRandomNumber
    _offset

    """

    def __init__(self, cb_returnRandomNumber, returned_byte_length):
        """
        in:
        cb_returnRandomNumber : callback with zero arguments returning _k_bytelength count bytes
        returned_byte_length: the number of bytes that make up the random number returned by the callback

        initializes:
        _k_bytelength : number of bytes that the cb is expected to return
        _k_bitstringlen : number of 1's and 0's implied by _k_bytelength
        _cb_returnRandomNumber : callback with zero arguments returning _k_bytelength count bytes
        _offset : to the next bit to return

        post:
        bitstring : the "buffer" of bits
        """
        self._k_bytelength = returned_byte_length
        self._k_bitstringlen = self._k_bytelength * 8
        self._cb_returnRandomNumber = cb_returnRandomNumber

        self.refill_bitstring()

    def __iter__(self):
        pass

    def refill_bitstring(self):
        """replace the intenral "buffer" with a new bitstring of length _k_bitstringlen
        post: self._bitstring, self._offset=0
        """
        bits64 = self._cb_returnRandomNumber()
        int64 = int.from_bytes(bits64, byteorder="little")
        self._bitstring = format(int64, "0{l}b".format(l=self._k_bytelength * 8))
        self._offset = 0

    def __next__(self):
        if self._offset == self._k_bitstringlen:
            self.refill_bitstring()
        try:
            rv = int(self._bitstring[self._offset])
        except IndexError:
            raise
        self._offset += 1
        return rv
