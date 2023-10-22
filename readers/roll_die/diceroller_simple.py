#!/usr/bin/env python3
# diceroller.py
# implements a DieRoller functor that represents a die of a specified number of sides and can be rolled repeatedly
# implements a DiceRoller functor that rolls as many die that have the same number of sies and returns the sorted result
"""extended description
DieRoller leverages entropythief's bit reader by creating a universe of possible face values for a roll
then randomly chooses to keep or discard each of the values in the universe (e.g. 1, 2, 3, 4, 5, 6)
then repeats this logic over the next set until only one is left or if all have decided to have been discarded
repeats with a new universe (e.g. 1, 2, 3, 4, 5, 6)
"""
from pathlib import Path
import os
import sys

PATH_TO_PIPE_READERS = Path(os.path.dirname(__file__)).resolve().parents[0]
sys.path.append(str(PATH_TO_PIPE_READERS))

from bitreader import EntropyBitReader

DISCARDBITCOUNT = 5  # arbitrarily chosen bit discard value


class _Ball:
    """called to return T or F based on next bit from the bit generator it was instantiated with"""

    def __init__(self, bit_generator):
        self._bit_generator = bit_generator

    def __call__(self):
        for _ in range(DISCARDBITCOUNT):
            next(self._bit_generator)

        return True if next(self._bit_generator) == 1 else False


class DieRoller:
    """roller for a die of a fixed number of sides"""

    def __init__(self, bit_generator, face_count=6):
        """
        in:
            bit_generator: an object that implements the generator protocol to return a 1 or 0
            face_count: the number of sides on the die (1 to face_count)
        """
        self._face_count = face_count
        self._ball = _Ball(bit_generator)
        self._universe = set([num for num in range(1, self._face_count + 1)])

    def _choose_randomly_from(self, uni):
        """traverse each universe element consulting ball as to whether to keep by adding to a new set. repeat on new set until one or zero kept. returns empty or single element set

        in: full universe
        out: sub universe of 0 or more picks
        """
        new_uni = set()

        for pick in uni:
            if self._ball() == True:
                new_uni.add(pick)

        uni.clear()

        return new_uni

    def __call__(self):
        """
        inputs
        ------
        universe_of_numbers (_universe)

        process
        -------
        new_universe {empty}
        *----------
            [ len(new_universe) == 0 ]
                new_universe <-copy- _universe
                **---len(new_universe)>1--------------
                    new_universe <- krunch universe

        output
        ------
        final chosen number from universe
        """

        new_universe = set()
        while len(new_universe) == 0:
            new_universe = self._universe.copy()
            while len(new_universe) > 1:
                new_universe = self._choose_randomly_from(new_universe)

        return list(new_universe)[0]


class DiceRollerSimple:
    """rolls n dice and return result as a sorted tuple so order is not important"""

    def __init__(self, bit_generator=None, face_count=6, subtraction=0, repeats=False):
        if bit_generator == None:
            bit_generator = EntropyBitReader()
        self._face_count = face_count
        self._die_roller = DieRoller(bit_generator=bit_generator, face_count=face_count)
        self._subtraction = subtraction
        self._repeats = repeats

    def __call__(self, dice_count=1):
        throw = []
        while len(throw) < dice_count:
            result = self._die_roller() - self._subtraction
            if self._repeats:
                throw.append(result)
            else:
                if result not in throw:
                    throw.append(result)
        return tuple(sorted(throw))


if __name__ == "__main__":
    start_error = False
    dice_count = 2
    face_count = 6
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

    roller = DiceRoller(bit_generator=bit_generator, face_count=face_count)
    print(roller(dice_count))
