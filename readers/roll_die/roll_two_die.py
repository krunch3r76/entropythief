#!/usr/bin/env python3
# debug diceroller.py

import sys
# sys.path.append("/home/krunch3r/golem/entropythief/readers")
# from bitreader import EntropyBitReader
from diceroller import DiceRoller
# import pprint
import locale

def _sum_freq_table(t):
    total=0
    for val in t.values():
        total+=val
    return total




def _print_freq_table(t, rowcount=6, with_freqs=True):
    first_tuple=next(iter(t))
    assert len(first_tuple) == 2, "only indexing when exactly two die are thrown!"

    sum_ = _sum_freq_table(t)

    def _print(as_counts=True):
        print("")
        for r in range(1, rowcount+1):
            key=(1, r)
            if as_counts:
                val=str(t[key])
            else:
                val="{:.4f}".format(t[key]/sum_)

            print(f"{key}->{val}", end="\t")
            # print(f"(1, {r})", end="\t")
            for r2 in range(1, r):
                key=(r2+1, r)
                if as_counts:
                    val=str(t[key])
                else:
                    val="{:.4f}".format(t[key]/sum_)
                # print(f"({r2+1}, {r})", end="\t")
                print(f"{key}->{val}", end="\t")
            print("")
    _print()
    if with_freqs:
        _print(False)

    locale.setlocale(locale.LC_NUMERIC, '')
    print(f"\nfrom total rolls: "
            + locale.format_string("%d", sum_, grouping=True))




def _build_base_freq_table(high_num=6):
    freq_table=dict()
    for one in range(1,high_num+1):
        for two in range(1, high_num+1):
            freq_table[ tuple( sorted( [one,two] ) ) ] = 0
    return freq_table




if __name__ == '__main__':
    diceroller = DiceRoller()
    error =False
    rollcount=100000
    if len(sys.argv) == 2:
        try:
            rollcount=int(sys.argv[1])
        except:
            error = True
    elif len(sys.argv) > 2:
        error=True

    if error:
        print(f"usage {sys.argv[0]} <number of rolls>")
        sys.exit(1)

    print(f"rolling two 6-sided dice: {rollcount} times")
    print(f"to change the number of rolls, rerun with the count after\ne.g. ./python3 roll_two_die.py 250000")
    freq_table = _build_base_freq_table()
    # roll the dice /rollcount/ times and print the frequency table

    for _ in range(rollcount):
        freq_table[diceroller()]+=1

    _print_freq_table(freq_table)


