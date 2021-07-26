#!/usr/bin/env python3
# worker
# pull all available entropy from /dev/random and store in text file as base64 for requestor retrieval
from pathlib import *
import base64
import sys

# import ctypes
from rdrand import rdrand # C extension

outputdir='/golem/output'
RESULT_PATH = Path(outputdir + '/result.bin')






#####################################################
# rdrand__generate_random_numbers_bin               #
#####################################################
# read the count bytes from the cpu entropy source as 8 byte frames sliced as needed
# IN: count of bytes required
# PRE: rdrand cpu instruction available
# POST: cpu emptied of the ceiling in measures of 8 bytes of the count requested
# OUT: random bits in measures of bytes requested
def rdrand__generate_random_numbers_bin(bytesrequired) -> bytes:
    int64_count = int(bytesrequired / 8)
    rem_bytes_count = bytesrequired % 8
    thebytes=bytearray()
    for _ in range(int64_count):
       bytes_int64 = rdrand().to_bytes(8, byteorder="little", signed=False)
       thebytes.extend(bytes_int64)
    if rem_bytes_count > 0:
        bytes_int64 = rdrand().to_bytes(8, byteorder="little", signed=False)
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


#################################################
#   devrand__generate_random_numbers_bin        #
#################################################
# read count random bytes from the system's kernel entropy source
# IN: count
# PRE: n/a
# POST: entropy source emptied of count bytes bits
# OUT: count random bytes
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


#############################
#   steal                   #
#############################
# draw randomness from a specified entropy source
# IN: count of bytes in which to store random bits, flag to indicate cpu rdrand as randomness source
# PRE: rdrand cpu instruction available on a 64 bit processor (as per shared library requirement)
# POST: random sources emptied of corresponding bits
# OUT: count bytes of random bits
def steal(count, USE_RDRAND):
    if not USE_RDRAND:
        result = devrand__generate_random_numbers_bin(count)
    else:
        result = rdrand__generate_random_numbers_bin(count)
    return result






#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
#                        __main__                         #
#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# notes:
#   argument 1: count of bytes <REQUIRED>
#   argument 2: 'rdrand' <OPTIONAL> use rdrand as entropy source
# POST: count random bytes written to RESULT_PATH
if __name__=="__main__":
    USE_RDRAND=False
    try:
        count = int(sys.argv[1])
        if len(sys.argv) == 3:
            if sys.argv[2] == 'rdrand':
                USE_RDRAND=True
        result = steal(count, USE_RDRAND)

        with RESULT_PATH.open(mode="wb") as f:
            f.write(result)

    except Exception as exception:
        print("worker.py: UNHANDLED EXCEPTION", file=sys.stderr)
        print(type(exception).__name__, file=sys.stderr)
        print(exception, file=sys.stderr)

