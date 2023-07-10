# random_number.py
from enum import Enum, auto
from pathlib import Path

import os, sys

# PATH_TO_PIPE_READERS = Path(os.path.dirname(__file__)).resolve().parents[0]
# sys.path.append(str(PATH_TO_PIPE_READERS))

from collections import namedtuple

# Define the namedtuple type
ClosestValues = namedtuple(
    "ClosestValues", "exponent power_of_two closest_multiple multiplicand distance"
)

# def myclosest(num, power_limit: int = 100):
#    #


def closest_power_of_two(num: int, power_limit: int = 100) -> ClosestValues:
    """find the power of two and a multiple of num that is 0 or more than 1 off from the power of two

    pre: none
    in:
    - num: number that shall measure exactly or near (off by at least 2) from the power of two found
    - power_limit: power of 2 in which to stop searching
    out:
    - (exponent, power_of_two, closest_multipe, multiplicand, distance)
    post: none
    """
    closest_distance = float("inf")
    closest_values = ClosestValues(0, 0, 0, 0, 0)

    for i in range(num.bit_length(), power_limit):
        power_of_two = 2**i
        closest_multiple = (power_of_two // num) * num
        distance = power_of_two - closest_multiple

        # refactor
        if distance == 0:
            closest_distance = distance
            closest_values = ClosestValues(
                i,
                power_of_two,
                closest_multiple,
                closest_multiple // num,
                power_of_two - closest_multiple,
            )
            return closest_values

        if distance == 1:
            continue

        if 0 <= distance < closest_distance:
            closest_distance = distance
            closest_values = ClosestValues(
                i,
                power_of_two,
                closest_multiple,
                closest_multiple // num,
                power_of_two - closest_multiple,
            )

    return closest_values  # interested in the closest multiple and its distance from the power (which is always at least two)


def roll_modulo_bytes(
    _pipe_reader,
    _n,
    _N,
    _num_bytes_random_needed,
    _num_bits_in_random,
    _num_bits_needed,
    _highest_random_number,
    _distance_of_multiple_from_power_of_two,
) -> int:
    """obtain random number by discarding excess bits from byte length inputs
    pre: none
    in:
    - _pipe_reader: object that implements read(count) for random bytes source
    - _n, _N: [_n, _N] range that each roll has to be in
    - _num_bytes_random_needed: the number of bytes that are needed to ensure a high enough number
    - _num_bits_in_random: the precomputed number of bits that _num_bytes_random_needed occupies
    - _highest_random_number: the highest number that could have been read e.g. 2^x - 1
    - _distance_of_multiple_from_power_of_two: the number of values that would be rejected
    out:
        a random number in [_n, _N]
    post:
        _pipe_reader state changed (1 or more bytes read)
    discussion:
        this method is a result of personal exploration of numbers. it requires hypothesis testing.
    """
    while True:
        random_bytes = _pipe_reader.read(_num_bytes_random_needed)
        random_int = int.from_bytes(random_bytes, byteorder="little")
        # can test for 0 to optimize
        # shift lsb to the right to zero most significant bits
        random_shifted = random_int >> max(0, _num_bits_in_random - _num_bits_needed)
        if (
            random_shifted
            > _highest_random_number - _distance_of_multiple_from_power_of_two
        ):
            continue
        return _n + random_shifted % (_N - _n + 1)


def random_number_scaled(n: int, N: int, pipe_reader, num_bytes=8) -> int:
    """generate a random number using a scaling factor
    pre: pipe_reader implements .read(count)
    in:
    - n: low number
    - N: high number
    - pipe_reader: object implementing read(count)->bytes
    - [ num_bytes ]: how big of a number to use for scaling
    post: none
    out:
    - a random number in [n, N]

    discussion:
        this method was suggested by chat-gpt4. it is supposedly a well accepted means of generating a uniform random number distribution exhibiting independence.
    """

    while True:
        random_bytes = pipe_reader.read(num_bytes)  # bytes for scaling
        random_int = int.from_bytes(
            random_bytes, byteorder="big"
        )  # a random number for scaling

        if random_int == 0:
            return n

        # Scale random_int to be in the range [0, 1)
        random_scaled = random_int / (2 ** (num_bytes * 8) - 1)

        # Map the random number to the range [n, N]
        # very rarely will random_scaled be 1
        result = int(n + (N - n + 1) * random_scaled)

        # Ensure the result falls within the desired range
        if n <= result <= N:
            return result
