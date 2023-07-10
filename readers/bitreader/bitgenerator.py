# randbit.py
# implements a random bit generator given a reader object
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)


class BitGenerator:
    """generate a bit (int of 1 or 0) upon every call given a readable source of an arbitrary number of bytes

    stores bits in a single large integer of fixed length which is replaced when all bits have
    been iterated upon
    """

    def __init__(self, bytes_reader=None, length_random_bytes=None):
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
        if length_random_bytes is None:
            raise Exception(
                "BitGenerator requires explictly setting the length of random bytes to read from the entropy source 𝘳𝘦𝘢𝘥𝘦𝘳 at a time. This can be arbitrarily high as PipeReader will yield for the entropy source to refill to offer as many as needed."
            )

        self._k_bytelength = length_random_bytes
        self._k_buffer_bit_length = self._k_bytelength * 8
        self._bytes_reader = bytes_reader
        self._bitpool = None
        # self._bitpool_queued = None
        self.refill_bits()

    def __call__(self):
        """iterate to get the next bit

        pre: None
        in: None
        post: _bitpool has one less bit
        out: integer that is 1 or 0
        """
        return self.__next__()

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

    def refill_bits(self):
        """replace the internal "buffer" with a new bitpool of length _k_buffer_bit_length
        pre : None
        in  : None
        post: self._bitpool, self._offset=0
        out : None
        """
        random_bytes = self._bytes_reader.read(self._k_bytelength)
        self._bitpool = int.from_bytes(random_bytes, byteorder="little")
        self._offset = 0

    def __next__(self) -> int:
        """Get the next bit.
        pre : None
        in: None
        post: _offset, [[ self._bitpool ]]
        out: 1 or 0
        """
        if self._offset == self._k_buffer_bit_length:
            self.refill_bits()
        bit = (self._bitpool >> self._offset) & 1
        self._offset += 1
        return bit


# class BitsGenerator
# TODO implement an iterator that returns an Int object with n random bits
