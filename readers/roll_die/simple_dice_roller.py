#!/usr/bin/env python3
# diceroller.py
# implements a DieRoller callable that represents a die of a specified number of sides and can be rolled repeatedly
# implements a DiceRoller callable that rolls as many die:DieRoller that have the same number of sides
#  and returns the sorted result

"""
This module provides classes for simulating fair dice rolls using a source of random bits.

The main classes are:

DieRoller - Simulates a single die with a configurable number of sides. Uses an unbiased 
bit source to generate random rolls through rejection sampling.

_Coin - Internal helper class that provides binary random decisions by consuming entropy bits.
Each flip consumes a configurable number of bits to ensure fairness.

The random bit source must implement the generator protocol, yielding 1s and 0s. The module
is designed to work with hardware random number generators or other entropy sources through
the EntropyBitReader interface.

Example usage:
    bit_reader = EntropyBitReader()
    d6 = DieRoller(bit_reader, face_count=6)
    roll = d6()  # Returns random number 1-6

The implementation ensures uniform distribution across face values through rejection sampling
of binary decisions, avoiding modulo bias that can occur with simpler approaches.
"""

from pathlib import Path
import os
import sys

PATH_TO_PIPE_READERS = Path(os.path.dirname(__file__)).resolve().parents[0]
sys.path.append(str(PATH_TO_PIPE_READERS))

from bitreader import EntropyBitReader

BITS_PER_FLIP = 1  # number of entropy bits consumed for each binary decision


class _Coin:
    """A binary random decision maker that consumes entropy bits to return True/False outcomes.
    Acts like a coin flip, consuming BITS_PER_FLIP bits of entropy for each decision."""

    def __init__(self, bit_generator):
        self._bit_generator = bit_generator

    def __call__(self):
        for _ in range(BITS_PER_FLIP):
            bit = next(self._bit_generator)

        return True if bit else False


class DieRoller:
    """roller for a die of a fixed number of sides"""

    def __init__(self, bit_generator, face_count=6):
        """
        in:
            bit_generator: an object that implements the generator protocol to return a 1 or 0
            face_count: the number of sides on the die (1 to face_count)
        """
        self._face_count = face_count
        self._coin = _Coin(bit_generator)
        self._possible_faces = set([num for num in range(1, self._face_count + 1)])

    def _choose_randomly_from(self, candidates):
        """Filter a set of candidate face values by randomly keeping or removing each value.
        If all values would be removed, tries again until at least one value remains.
        
        Args:
            candidates: Set of possible face values to filter
            
        Returns:
            Set of remaining candidate values after random filtering, never empty
        """
        while True:
            removed = set()
            for face in candidates:
                if self._coin():
                    removed.add(face)
            
            remaining = candidates - removed
            if remaining:  # if we have at least one face left
                return remaining
            # if all faces were removed, try again with the same candidates

    def __call__(self):
        """
        Roll the die by repeatedly filtering the set of possible face values
        until only one value remains.
        
        Returns:
            The randomly selected face value
        """
        remaining_faces = set()
        while len(remaining_faces) != 1:
            remaining_faces = self._choose_randomly_from(self._possible_faces)
            while len(remaining_faces) > 1:
                remaining_faces = self._choose_randomly_from(remaining_faces)

        return list(remaining_faces)[0]


class DiceRollerSimple:
    """rolls n dice and return result as a sorted tuple so order is not important"""

    def __init__(
        self,
        bit_generator=None,
        face_count=6,
        subtraction=0,
        repeats=False,
        entropy_buffer_bytecount=None,
    ):
        if entropy_buffer_bytecount is None:
            entropy_buffer_bytecount = 2**12
        if bit_generator is None:
            bit_generator = EntropyBitReader(
                countBytesToBuffer=entropy_buffer_bytecount
            )
        self._face_count = face_count
        self._die_roller = DieRoller(bit_generator=bit_generator, face_count=face_count)
        self._subtraction = subtraction
        self._repeats = repeats

    def __call__(self, dice_count=1, as_sorted=False):
        throw = []
        while len(throw) < dice_count:
            result = self._die_roller() - self._subtraction
            if self._repeats:
                throw.append(result)
            else:
                if result not in throw:
                    throw.append(result)
        if as_sorted:
            return tuple(sorted(throw))
        else:
            return tuple(throw)


if __name__ == "__main__":
    start_error = False
    dice_count = 10
    face_count = 80
    if len(sys.argv) != 1:
        if len(sys.argv) > 3:
            start_error = True
        else:
            try:
                if len(sys.argv) > 1:
                    dice_count = int(sys.argv[1])
                if len(sys.argv) == 3:
                    face_count = int(sys.argv[2])
            except:
                start_error = True
    if start_error:
        print(f"Usage: {sys.argv[0]} [<number of dice>=2] [<faces_per_die=6>]")
        sys.exit(1)

    bit_generator = EntropyBitReader(10)  # just reserve 10 bytes for the buffer

    roller = DiceRollerSimple(bit_generator=bit_generator, face_count=face_count)
    print(roller(dice_count)) 