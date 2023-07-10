from pathlib import Path
import os, sys
from enum import Enum, auto

PATH_TO_PIPE_READERS = Path(os.path.dirname(__file__)).resolve().parents[0]
sys.path.append(str(PATH_TO_PIPE_READERS))
from roll_die.random_number import (
    closest_power_of_two,
    random_number_scaled,
    roll_modulo_bytes,
)
from pipe_reader import PipeReader


class Die:
    """simulate a die with predefined faces of consecutive integers of 0 and above"""

    class Algorithm(Enum):
        """define flags to indicate which random number generating algorithm to use"""

        MODULOBYTES = auto()
        # MODULOBITS = auto()  # todo
        SCALING = auto()

    def __init__(
        self, N: int, n: int = 1, pipe_reader=None, algorithm=Algorithm.MODULOBYTES
    ):
        if pipe_reader is None:
            self._pipe_reader = PipeReader()
        else:
            self._pipe_reader = pipe_reader

        self.algorithm = algorithm

        # find optimal parameters for rejection sampling via modulo
        self._N = N
        self._n = n

        if self.algorithm is Die.Algorithm.MODULOBYTES:
            result = closest_power_of_two(N - n + 1, 100)
            self._multiple_closest_to_a_power_of_two = result.closest_multiple
            self._distance_of_multiple_from_power_of_two = result.distance
            self._num_bits_needed = (
                self._multiple_closest_to_a_power_of_two
            ).bit_length()
            self._num_bytes_random_needed = (self._num_bits_needed + 7) // 8
            self._num_bits_in_random = self._num_bytes_random_needed * 8
            self._max_number_on_zero_scale = self._N - self._n
            self._highest_random_number = 2**self._num_bits_needed - 1

    def _roll_modulo_bytes(self):
        return roll_modulo_bytes(
            self._pipe_reader,
            self._n,
            self._N,
            self._num_bytes_random_needed,
            self._num_bits_in_random,
            self._num_bits_needed,
            self._highest_random_number,
            self._distance_of_multiple_from_power_of_two,
        )

    def __call__(self):
        if self.algorithm == Die.Algorithm.MODULOBYTES:
            return self._roll_modulo_bytes()
        elif self.algorithm == Die.Algorithm.SCALING:
            return random_number_scaled(self._n, self._N, self._pipe_reader)
