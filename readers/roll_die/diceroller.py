#!/usr/bin/env python3
# diceroller.py

from pathlib import Path
import os
import sys

PATH_TO_PIPE_READERS = Path(os.path.dirname(__file__)).resolve().parents[0]
sys.path.append(str(PATH_TO_PIPE_READERS))

from bitreader import EntropyBitReader
from pipe_reader import PipeReader
from roll_die.die import Die


class DiceRoller:
    """roll 2 or more Die to return a tuple of random rolls"""

    def __init__(
        self,
        high_face=6,
        low_face=1,
        number_of_dice=2,
        as_sorted=False,
        allow_repeats=True,
        read_buffer_size=None,
        algorithm=Die.Algorithm.MODULOBYTES
    ):
        """
        initialize DiceRoller

        pre: none
        in:
        - high_face: the highest face of the dice [6]
        - low_face: the lowest face of the dice [1]
        - number_of_dice: how many dice to roll [2]
        - as_sorted: whether to sort the dice faces [TRUE]
        - allow_repeats: whether to allow the same number to come up [TRUE]
        - [read_buffer_size]: override the default pipe reader's buffer value
        post:
        - _number_of_dice
        - _as_sorted
        - _allow_repeats
        """
        self._number_of_dice = number_of_dice
        self._as_sorted = as_sorted
        self._allow_repeats = allow_repeats

        pipe_reader = PipeReader(read_buffer_size)
        self._die = Die(
            high_face,
            low_face,
            pipe_reader=pipe_reader,
            algorithm=Die.Algorithm.MODULOBYTES,
        )

    def __call__(self):
        """
        pre: none
        in: none
        out:
        - a tuple of random rolls that may be sorted and may have repeats excluded as specified
        post: entropypool depleted of bytes/bits
        """
        rolls = []
        if self._allow_repeats:
            for _ in range(self._number_of_dice):
                rolls.append(self._die())
        else:
            while len(rolls) < self._number_of_dice:
                roll = self._die()
                if roll not in rolls:
                    rolls.append(roll)

        if self._as_sorted:
            rolls.sort()

        return tuple(rolls)


if __name__ == "__main__":
    start_error = False
    dice_count = 2
    face_count = 6
    algorithm = None
    if len(sys.argv) != 1:
        if len(sys.argv) > 4:
            start_error = True
        else:
            try:
                if len(sys.argv) > 1:
                    dice_count = int(sys.argv[1])
                if len(sys.argv) >= 3:
                    face_count = int(sys.argv[2])
                if len(sys.argv) == 4:
                    if sys.argv[3] == "scaling":
                        algorithm = Die.Algorithm.SCALING
                    else:
                        algorithm = Die.Algorithm.MODULOBYTES

            except:
                start_error = True
    if start_error:
        print(f"Usage: {sys.argv[0]} [<number of dice>=2] [<faces_per_die=6>]")
        sys.exit(1)

    diceroller = DiceRoller(high_face=face_count, number_of_dice=dice_count, algorithm=algorithm)
    print(diceroller())
