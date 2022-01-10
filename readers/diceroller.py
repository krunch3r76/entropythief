#!/usr/bin/env python3
# diceroller.py
# implements a DieRoller functor that represents a die of a specified number of sides and can be rolled repeatedly
# implements a DiceRoller functor that rolls as many die that have the same number of sies and returns the sorted result

from bitreader import EntropyBitReader

class _Ball:
    """called to return T or F based on next bit from the bit generator it was instantiated with"""
    def __init__(self, bit_generator):
        self._bit_generator=bit_generator
    def __call__(self):
        return True if next(self._bit_generator)==1 else False

class DieRoller:
    """roller for a die of a fixed number of sides"""
    def __init__(self, bit_generator, side_count=6):
        """
        in:
            bit_generator: an object that implements the generator protocol to return a 1 or 0
            side_count: the number of sides on the die (1 to side_count)
        """
        self._side_count=side_count
        self._ball = _Ball(bit_generator)
        self._universe = set( [ num for num in range(1, self._side_count+1)] )


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

        new_universe=set()
        while len(new_universe) == 0:
            new_universe = self._universe.copy()
            while len(new_universe) > 1:
                new_universe = self._choose_randomly_from(new_universe)

        return list(new_universe)[0]




class DiceRoller():
    """rolls n dice and return result as a sorted tuple so order is not important"""
    def __init__(self, bit_generator=EntropyBitReader(), side_count=6):
        self._side_count=side_count
        self._die_roller=DieRoller(bit_generator)

    def __call__(self, dice_count=2):
        throw=[]
        for _ in range(dice_count):
            throw.append(self._die_roller())
        return tuple(sorted(throw))
