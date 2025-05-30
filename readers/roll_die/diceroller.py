#!/usr/bin/env python3
# diceroller.py

from pathlib import Path
import os
import sys

PATH_TO_PIPE_READERS = Path(os.path.dirname(__file__)).resolve().parents[0]
sys.path.append(str(PATH_TO_PIPE_READERS))

from pipe_reader import PipeReader
from roll_die.die import Die


# ============================================================================
# High Performance Shared Reader (DEFAULT)
# ============================================================================

# Single shared reader using optimized defaults for maximum performance
# Uses PipeReader() with optimal defaults: 100MB buffer, 256KB reads
shared_reader = PipeReader()

class DiceRoller:
    """roll 2 or more Die to return a tuple of random rolls
    
    By default uses optimized shared PipeReader for maximum performance.
    """

    def __init__(
        self,
        high_face=6,
        low_face=1,
        number_of_dice=2,
        as_sorted=False,
        allow_repeats=True,
        algorithm=Die.Algorithm.MODULOBYTES,
        pipe_reader=None
    ):
        """
        initialize DiceRoller

        pre: none
        in:
        - high_face: the highest face of the dice [6]
        - low_face: the lowest face of the dice [1]
        - number_of_dice: how many dice to roll [2]
        - as_sorted: whether to sort the dice faces [FALSE]
        - allow_repeats: whether to allow the same number to come up [TRUE]
        - algorithm: which algorithm to use for rolling [MODULOBYTES]
        - pipe_reader: custom pipe reader (default: uses optimized shared reader)
        post:
        - _number_of_dice
        - _as_sorted
        - _allow_repeats
        """
        self._number_of_dice = number_of_dice
        self._as_sorted = as_sorted
        self._allow_repeats = allow_repeats

        # Use optimized shared reader by default for maximum performance
        if pipe_reader is None:
            pipe_reader = shared_reader

        self._die = Die(
            high_face,
            low_face,
            pipe_reader=pipe_reader,
            algorithm=algorithm
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
            rolls_set = set()
            while len(rolls_set) < self._number_of_dice:
                roll = self._die()
                rolls_set.add(roll)
            rolls = list(rolls_set)

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


# ============================================================================
# Convenience Functions
# ============================================================================

def get_shared_stats():
    """Get efficiency statistics from the shared reader."""
    return shared_reader.get_efficiency_stats()

# Legacy compatibility - these now just create normal DiceRollers (which use shared reader by default)
def DiceRoller_fast(**kwargs):
    """Legacy alias - DiceRoller now uses shared reader by default."""
    return DiceRoller(**kwargs)

def create_shared_dice_roller(**kwargs):
    """Legacy alias - DiceRoller now uses shared reader by default.""" 
    return DiceRoller(**kwargs)

# Short aliases for convenience
fast = DiceRoller
max_performance = DiceRoller
get_performance_stats = get_shared_stats
get_shared_reader_stats = get_shared_stats
