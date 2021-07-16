#!/usr/bin/env python3
# worker
# pull all available entropy from /dev/random and store in text file as base64 for requestor retrieval
from pathlib import *
import base64
import il
import ctypes
import sys
import json

NUMBYTES=2**19
#outputdir='/tmp'
outputdir='/golem/output'
RESULT_PATH = Path(outputdir + '/result.bin')

# OUT: 64bit integer
def _ilasm_rdrand():
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
#           _gen_rdrand()                               #
#       yield 3 random int64s (24 bytes)                #
#                                                       #
#-------------------------------------------------------#
def gen_rdrand():
    while True:
        yielded = bytearray()
        for _ in range(3):
            val = _ilasm_rdrand()
            asbytes = val.to_bytes(8, byteorder="little", signed=True)
            yielded.extend([ byte for byte in asbytes ])
        yield yielded

#-------------------------------------------------------#
#           _read_entropy_available()                   #
#   query procfs for count of entropy bits in stream    #
# IN: NONE, PRE: NONE, POST: NONE, OUT: count bits      #
#-------------------------------------------------------#
# required by: read_available_random_bytes()
def _read_entropy_available() -> int:
    with open('/proc/sys/kernel/random/entropy_avail', 'r') as procentropy:
        return int(procentropy.read())

#---------------------------------------------------------------#
#           _read_num_random_bytes()                            #
#   read bytes from system entropy stream                       #
# IN: NONE, PRE: NONE, POST: entropy taken, OUT: binary entropy #
#---------------------------------------------------------------#
# required by: read_available_random_bytes()
def _read_num_random_bytes(num, devrandom=None) -> bytes:
    close_devrandom=False
    if devrandom==None:
        close_devrandom=True
        devrandom = open('/dev/random', 'rb')
    randomBytes=devrandom.read(num)
    if close_devrandom:
        devrandom.close()
    return randomBytes





###################################################################
#           read_available_random_bytes()                         #
# IN: NONE, PRE: NONE, POST: NONE, OUT: all available entropy     #
###################################################################
# comments: entropy available is at most 4096 bits or 512 bytes 
def read_available_random_bytes() -> bytes:
    entropy_available_in_num_bytes = int(_read_entropy_available() / 8)
    return _read_num_random_bytes( entropy_available_in_num_bytes )



# print the base64 encoding of at least bytesrequired, adding
# bytes needed 
def generate_random_numbers_test(bytesrequired=NUMBYTES) -> bytes:
    missing = bytesrequired % 3 # missing count of bytes
    bytesrequired += missing
    coro = gen_rdrand()
    next(coro)
    while True:
        result = coro.send(None)
        bytesacquired += 24
        if bytesacquired < bytesrequired:
            encoded = base64.b64encode(result)
        else:
            break

def generate_random_numbers_1() -> bytes:
    bytesrequired=NUMBYTES
    bytesacquired=0
    coro = gen_rdrand()
    next(coro)
    while True:
        result = coro.send(None)
        bytesacquired += 24
        if bytesacquired + 24 < bytesrequired:
            encoded = base64.b64encode(result)
            print(encoded.decode("utf-8"), end="")
            # print all bytesacquired as base64 to stdout
        else:
            bytestogo = bytesrequired - bytesacquired
            curtailed_result = result[0:bytestogo]
            encoded = base64.b64encode(curtailed_result)
            print(encoded.decode("utf-8"))
            break


def generate_random_numbers(d=dict(), bytesrequired=NUMBYTES) -> bytes:
    d['requested']=int(bytesrequired)
    output=str()
    bytesacquired=0
    coro = gen_rdrand()
    num_div = int(bytesrequired / 24)
    num_rem = int(bytesrequired % 24)

    next(coro)
    while True:
        next_random_twentyfour_bytes = coro.send(None)

        if bytesacquired < num_div*24:
            encoded = base64.b64encode(next_random_twentyfour_bytes)
            output+=encoded.decode("utf-8")
            # print(encoded.decode("utf-8"), end="")
        else:
            if num_rem > 0:
                # at this time we only want num_rem bytes
                # from next_random_twentyfour_bytes
                part = next_random_twentyfour_bytes[:num_rem]
                partEncoded = base64.b64encode(part)
                output+=partEncoded.decode("utf-8")
                # print(partEncoded.decode("utf-8"), end="")
            break
        bytesacquired += 24

    d['b64']=output





def generate_random_numbers_bin(bytesrequired=NUMBYTES) -> bytes:
    int64_count = int(bytesrequired / 8)
    rem_bytes_count = bytesrequired % 8
    thebytes=bytearray()
    for _ in range(int64_count):
       bytes_int64 = _ilasm_rdrand().to_bytes(8, byteorder="little", signed=True)
       thebytes.extend(bytes_int64)
    if rem_bytes_count > 0:
        bytes_int64 = _ilasm_rdrand().to_bytes(8, byteorder="little", signed=True)
        thebytes.extend(bytes_int64[0:rem_bytes_count])
    return thebytes




if __name__=="__main__":
    try:
        if len(sys.argv) > 1:
            NUMBYTES = int(sys.argv[1])

        thebytes=generate_random_numbers_bin(NUMBYTES)
        with RESULT_PATH.open(mode="wb") as f:
            f.write(thebytes)
    except Exception as exception:
        print("worker.py: UNHANDLED EXCEPTION", file=sys.stderr)
        print(type(exception).__name__, file=sys.stderr)
        print(exception, file=sys.stderr)

