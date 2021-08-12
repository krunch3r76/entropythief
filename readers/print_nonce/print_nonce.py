#!/usr/bin/env python3
# print_nonce

# interface with entropythief's ring of named pipes to draw a 64bit value
import os, sys


PATH_TO_PIPE_MODULE=os.path.dirname(__file__) + "/.."
sys.path.append(PATH_TO_PIPE_MODULE)
import pipe_reader


readerPipe = pipe_reader.PipeReader()
if len(sys.argv) == 1:
    while True:
        count = int(input("How many nonces? "))
        for _ in range(count):
            result = readerPipe.read(8)
            int64 = int.from_bytes(result, byteorder="little")
            print(int64)
elif len(sys.argv) == 3:
        if sys.argv[1] == 'burn':
            count = int(sys.argv[2])
            print(f"burning {8*count} bytes")
            readerPipe.read(8*count)
        else:
            print(f"usage: {sys.argv[0]} burn <nonce count [counts of 8 bytes]>")
            sys.exit(127)

