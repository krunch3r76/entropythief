#!/usr/bin/env python3
# print_nonce

# interface with entropythief's ring of named pipes to draw a 64bit value
import os, sys


PATH_TO_PIPE_MODULE=os.path.dirname(__file__) + "/.."
sys.path.append(PATH_TO_PIPE_MODULE)
import pipe_reader

readerPipe = pipe_reader.PipeReader()

while True:
    count = int(input("How many nonces? "))
    for _ in range(count):
        result = readerPipe.read(8)
        int64 = int.from_bytes(result, byteorder="little")
        print(int64)

