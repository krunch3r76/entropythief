#!/usr/bin/env python3
# worker
# pull all available entropy from /dev/random and store in text file as base64 for requestor retrieval
from pathlib import *
import base64
import sys

import il
import ctypes

outputdir='/golem/output'
RESULT_PATH = Path(outputdir + '/result.bin')


# OUT: 64bit integer
def rdrand__ilasm():
    f = il.def_asm(
            name="r2",
            prototype=ctypes.CFUNCTYPE(ctypes.c_int64),
            code="""
            .intel_syntax noprefix
            0:
            mov rax, 0
            rdrand rax
            jnc 0b
            ret
            """)
    return f()


#-------------------------------------------------------#
#           rdrand__gen()                               #
#       yield 3 random int64s (24 bytes)                #
#                                                       #
#-------------------------------------------------------#
def rdrand__gen():
    while True:
        yielded = bytearray()
        for _ in range(3):
            val = rdrand__ilasm()
            asbytes = val.to_bytes(8, byteorder="little", signed=True)
            yielded.extend([ byte for byte in asbytes ])
        yield yielded



def rdrand__generate_random_numbers_bin(bytesrequired) -> bytes:
    int64_count = int(bytesrequired / 8)
    rem_bytes_count = bytesrequired % 8
    thebytes=bytearray()
    for _ in range(int64_count):
       bytes_int64 = rdrand__ilasm().to_bytes(8, byteorder="little", signed=True)
       thebytes.extend(bytes_int64)
    if rem_bytes_count > 0:
        bytes_int64 = rdrand__ilasm().to_bytes(8, byteorder="little", signed=True)
        thebytes.extend(bytes_int64[0:rem_bytes_count])
    return thebytes[:bytesrequired]  # in case the requested count is not measured by 8








#-------------------------------------------------------#
#           _devrand__read_entropy_available()                   #
#   query procfs for count of entropy bits in stream    #
# IN: NONE, PRE: NONE, POST: NONE, OUT: count bits      #
#-------------------------------------------------------#
# required by: read_available_random_bytes()
def _devrand__read_entropy_available() -> int:
    with open('/proc/sys/kernel/random/entropy_avail', 'r') as procentropy:
        return int(procentropy.read())




#---------------------------------------------------------------#
#           devrand__read_num_random_bytes()                            #
#   read bytes from system entropy stream                       #
# IN: NONE, PRE: NONE, POST: entropy taken, OUT: binary entropy #
#---------------------------------------------------------------#
# required by: read_available_random_bytes()
def devrand__read_num_random_bytes(num, devrandom=None) -> bytes:
    close_devrandom=False
    if devrandom==None:
        close_devrandom=True
        devrandom = open('/dev/random', 'rb')
    randomBytes=devrandom.read(num)
    if close_devrandom:
        devrandom.close()
    return randomBytes





###################################################################
#           devrand__read_all_available_random_bytes()                         #
# IN: NONE, PRE: NONE, POST: NONE, OUT: all available entropy     #
###################################################################
# comments: entropy available is at most 4096 bits or 512 bytes 
# not used
def devrand__read_all_available_random_bytes() -> bytes:
    entropy_available_in_num_bytes = int(_devrand__read_entropy_available() / 8)
    return devrand__read_num_random_bytes( entropy_available_in_num_bytes )



def devrand__generate_random_numbers_bin(count):
    countRemaining = count
    result = bytearray()
    with open('/dev/random', 'rb') as devrandom:
        while countRemaining > 0:
            countAvailable = int(_devrand__read_entropy_available() / 8)
            if countAvailable > 0:
                if countAvailable >= countRemaining:
                    ba_temp =devrand__read_num_random_bytes(countRemaining, devrandom)
                    countRemaining = 0
                else:
                    ba_temp = devrand__read_num_random_bytes(countAvailable, devrandom)
                    countRemaining -= countAvailable
                result.extend(ba_temp)    
    return result


def main(count, USE_RDRAND):
    if not USE_RDRAND:
        result = devrand__generate_random_numbers_bin(count)
    else:
        result = rdrand__generate_random_numbers_bin(count)
    return result


if __name__=="__main__":
    USE_RDRAND=False
    try:
        count = int(sys.argv[1])
        if len(sys.argv) == 3:
            if sys.argv[2] == 'rdrand':
                USE_RDRAND=True
        result = main(count, USE_RDRAND)

        with RESULT_PATH.open(mode="wb") as f:
            f.write(result)

    except Exception as exception:
        print("worker.py: UNHANDLED EXCEPTION", file=sys.stderr)
        print(type(exception).__name__, file=sys.stderr)
        print(exception, file=sys.stderr)

