# randbit.py
# implements a random bit generator given a reader object
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)
from enum import Enum, auto


class StorageKind(Enum):
    BITFIELD = auto()
    BITSTRING = auto()


class BitGenerator:
    """Base class for BitGenerator"""

    def __init__(
        self, bytes_reader=None, length_random_bytes=None, kind=StorageKind.BITFIELD
    ):
        """
        pre: None
        in:
        - bytes_reader : callback that implements read(length_random_bytes)
        - length_random_bytes: the number of bytes that make up the random number returned by the callback

        post:
        - _k_bytelength : number of bytes that the cb is expected to return
        - _k_buffer_bit_length : number of 1's and 0's implied by _k_bytelength
        - _bytes_reader : callback that implements read(length_random_bytes)
        - _offset : to the next bit to return
        - _bitpool : the "buffer" of bits from a large integer of size length_random_bytes
        # - _bitpool_queued : a read ahead for the next pool
        """
        # self._implementation = implementation(bytes_reader, length_random_bytes)

        if length_random_bytes is None:
            raise Exception(
                "BitGenerator requires explictly setting the length of random bytes to read from the entropy source 𝘳𝘦𝘢𝘥𝘦𝘳 at a time. This can be arbitrarily high as PipeReader will yield for the entropy source to refill to offer as many as needed."
            )

        self._k_bytelength = length_random_bytes
        self._k_buffer_bit_length = self._k_bytelength * 8
        self._bytes_reader = bytes_reader
        self._bitpool = None
        self._offset = None
        self._kind = kind
        self._refill_bits()

    def __iter__(self):
        """
        This method makes BitGenerator iterable as with a for in loop.
        pre : None
        in  : None
        post: None
        out : Returns itself as an iterator
        """
        while True:
            yield self.__next__()

    def __call__(self):
        """iterate to get the next bit

        pre: None
        in: None
        post: _bitpool has one less bit
        out: integer that is 1 or 0
        """
        return self.__next__()

    def _refill_bits(self):
        """replace the internal "buffer" with a new bitpool of length _k_buffer_bit_length
        pre : None
        in  : None
        post: self._bitpool, self._offset=0
        out : None
        """
        random_bytes = self._bytes_reader.read(self._k_bytelength)
        if self._kind == StorageKind.BITSTRING:
            self._bitpool = bin(int.from_bytes(random_bytes, byteorder="little"))[2:]
            self._bitpool = self._bitpool.zfill(self._k_buffer_bit_length)
            # print(
            #     f"\n\n{self._k_bytelength} {self._k_buffer_bit_length} {len(self._bitpool)}\n\n"
            # )
        else:
            # self._bitpool = int.from_bytes(random_bytes, byteorder="little")
            self._bitpool = bytes(random_bytes)  # ensure bytes
        self._offset = 0

    def __next__(self) -> int:
        """Get the next bit.
        pre : None
        in: None
        post: _offset, [[ self._bitpool ]]
        out: 1 or 0
        """
        bit = None

        if self._offset >= self._k_buffer_bit_length:
            self._refill_bits()

        if self._kind == StorageKind.BITSTRING:
            bit = int(self._bitpool[self._offset])
        else:
            if self._offset >= self._k_buffer_bit_length:
                self._refill_bits()
            byte_index = self._offset // 8
            bit_index = self._offset % 8
            bit = (self._bitpool[byte_index] >> bit_index) & 1
            # bit = (self._bitpool >> self._offset) & 1

        self._offset += 1
        return bit
