#!/usr/bin/env python3
# worker
# pull all available entropy from /dev/random and store in text file as base64 for requestor retrieval
from pathlib import *
import base64
import il
import ctypes

NUMBYTES=2**19
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
#           _rdrand()                                   #
#   get a random (64bit) integer repeatedly             #
#                                                       #
#-------------------------------------------------------#
def gen_rdrand():
    while True:
        # val = _ilasm_rdrand()
        # asbytes = val.to_bytes(8, byteorder="little", signed=True)
        # rv.extend([ byte for byte in asbytes ] )
        # rv.extend([ byte for byte in _ilasm_rdrand().to_bytes(8, byteorder="little", signed=True) ])
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




def generate_random_numbers() -> bytes:
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

            # print newbytearray as base64 encoded
        # print(len(result))
    # thebytes = _rdrand(NUMBYTES)
    # return thebytes






if __name__=="__main__":
    try:
        # randomBytes=read_available_random_bytes()
        # randomBytes = _rdrand()
        # encoded = base64.b64encode(randomBytes)
        # print(encoded.decode("utf-8"), end="")
        pass
    except Exception as exception:
        print("uncaught exception", type(exception).__name__)
        print(exception)
        raise

