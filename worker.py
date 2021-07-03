#!/usr/bin/env python3
# worker
# pull all available entropy from /dev/random and store in text file as base64 for requestor retrieval
from pathlib import *
import base64

outputdir='/golem/output'
RESULT_PATH = Path(outputdir + '/result.bin')






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












if __name__=="__main__":
    try:
        randomBytes=read_available_random_bytes()
        encoded = base64.b64encode(randomBytes)
        print(encoded.decode("utf-8"), end="")
    except Exception as exception:
        print("uncaught exception", type(exception).__name__)
        print(exception)
        raise

