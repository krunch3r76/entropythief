#!/usr/bin/env python3
# diceroller.py

from pathlib import Path
import os
import sys

PATH_TO_PIPE_READERS = Path(os.path.dirname(__file__)).resolve().parents[0]
sys.path.append(str(PATH_TO_PIPE_READERS))

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

        if pipe_reader is None:
            pipe_reader = PipeReader(read_buffer_size)
        else:
            pipe_reader = pipe_reader

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
# Simple Shared Reader Management for Multi-threading
# ============================================================================

# Module-level shared reader (thread-safe PipeReader)
_shared_reader = None

def create_shared_dice_roller(buffer_size=None, **kwargs):
    """Factory function to create DiceRollers that share a single thread-safe PipeReader.
    
    This is the recommended way to create DiceRollers for multi-threaded usage.
    All DiceRollers created via this function will share the same PipeReader instance,
    eliminating file descriptor contention and improving performance.
    
    Args:
        buffer_size: Size of shared PipeReader buffer (default: 100MB for multi-threading)
        **kwargs: All normal DiceRoller arguments (high_face, number_of_dice, etc.)
        
    Returns:
        DiceRoller: A new DiceRoller instance using the shared PipeReader
        
    Example:
        # Multi-threaded usage
        def worker():
            dice_roller = create_shared_dice_roller(high_face=6, number_of_dice=2)
            return dice_roller()
        
        threads = [threading.Thread(target=worker) for _ in range(10)]
    """
    global _shared_reader
    
    if _shared_reader is None:
        # Default to 100MB buffer for multi-threading performance
        if buffer_size is None:
            buffer_size = 100 * 1024 * 1024  # 100MB
        _shared_reader = PipeReader(buffer_size=buffer_size)
    
    # Ensure pipe_reader isn't overridden in kwargs
    kwargs['pipe_reader'] = _shared_reader
    
    return DiceRoller(**kwargs)


def get_shared_reader_stats():
    """Get efficiency statistics from the shared PipeReader.
    
    Returns:
        dict: Statistics about shared reader performance, or None if no shared reader exists
    """
    global _shared_reader
    if _shared_reader is None:
        return None
    return _shared_reader.get_efficiency_stats()


def reset_shared_reader(buffer_size=None):
    """Reset the shared PipeReader (useful for testing or changing buffer size).
    
    Args:
        buffer_size: New buffer size for the shared reader
    """
    global _shared_reader
    _shared_reader = None
    if buffer_size is not None:
        # Pre-create with specific buffer size
        _shared_reader = PipeReader(buffer_size=buffer_size)


# Class method alternative for those who prefer object-oriented style
def DiceRoller_with_shared_reader(cls, **kwargs):
    """Class method alternative to create_shared_dice_roller()"""
    return create_shared_dice_roller(**kwargs)

# Monkey patch the class method
DiceRoller.with_shared_reader = classmethod(DiceRoller_with_shared_reader)
