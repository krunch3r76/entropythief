#!/usr/bin/env python3
# debug diceroller.py

import sys
from die import Die

import os, sys
from pathlib import Path

PATH_TO_PIPE_READERS = Path(os.path.dirname(__file__)).resolve().parents[0]
sys.path.append(str(PATH_TO_PIPE_READERS))
from pipe_reader import PipeReader
from diceroller import DiceRoller

# import pprint
import locale


def _sum_freq_table(t):
    total = 0
    for val in t.values():
        total += val
    return total


def _print_freq_table(t, rowcount=6, with_freqs=True):
    print("\033[0;33;1m", end="")  # yellow
    first_tuple = next(iter(t))
    assert len(first_tuple) == 2, "only indexing when exactly two die are thrown!"

    sum_ = _sum_freq_table(t)

    def _print(as_counts=True):
        print("")
        for r in range(1, rowcount + 1):
            key = (1, r)
            if as_counts:
                val = str(t[key])
            else:
                val = "{:.4f}".format(t[key] / sum_)

            print(f"{key}->{val}", end="\t")
            # print(f"(1, {r})", end="\t")
            for r2 in range(1, r):
                key = (r2 + 1, r)
                if as_counts:
                    val = str(t[key])
                else:
                    val = "{:.4f}".format(t[key] / sum_)
                # print(f"({r2+1}, {r})", end="\t")
                print(f"{key}->{val}", end="\t")
            print("")

    _print()
    if with_freqs:
        _print(False)

    locale.setlocale(locale.LC_NUMERIC, "")
    print("\033[0m", end="")  # yellow

    print(f"\nfrom total rolls: " + locale.format_string("%d", sum_, grouping=True))


def _build_base_freq_table(high_num=6):
    freq_table = dict()
    for one in range(1, high_num + 1):
        for two in range(1, high_num + 1):
            freq_table[tuple(sorted([one, two]))] = 0
    return freq_table


if __name__ == "__main__":
    diceroller = DiceRoller(high_face=6, number_of_dice=2, as_sorted=True)
    error = False
    rollcount = 100000
    if len(sys.argv) == 2:
        try:
            rollcount = int(sys.argv[1])
        except:
            error = True
    elif len(sys.argv) > 2:
        error = True

    if error:
        print(f"usage {sys.argv[0]} <number of rolls>")
        sys.exit(1)

    print(f"rolling two 6-sided dice: {rollcount} times")
    print(
        f"\033[0;33mto change the number of rolls, rerun with the count after\ne.g. \033[0;3m./python3 roll_two_die.py 250000\033[0m"
    )
    freq_table = _build_base_freq_table()
    # roll the dice /rollcount/ times and print the frequency table

    for _ in range(rollcount):
        roll = diceroller()
        # print(roll)
        freq_table[roll] += 1

    _print_freq_table(freq_table)
