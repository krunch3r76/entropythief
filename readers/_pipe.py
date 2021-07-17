# _pipe
# author: krunch3r (biz@u26a4.com)
# license: poetic

"""
python api to named pipe containg the random/entropy bytes
provided by entropythief

usage:
  " assuming the reader is being written in a child directory to this module
  PATH_TO_PIPE_MODULE=os.path.dirname(__file__) + "/.."
  sys.path.append(PATH_TO_PIPE_MODULE)

  from _pipe import harness_entropy

  " in this example, the coroutine object is given the name harness_entropy
  harness_entropy_coro = harness_entropy(<payload len in bytes>, <callback inputting the payload bytes object>)
  next(harness_entropy_coro)

   for _ in range(<number of iteration>) # alt, infinite while loop with try block
       harness_entropy_coro.send(None)

   harness_entropy_coro.close()
"""

import fcntl
import os
import sys #debug
import termios
import time
import select

kIPC_FIFO_FP="/tmp/pilferedbits"



#-------------------------------------------#
#           _count_bytes_in_pipe            #
#-------------------------------------------#
def _count_bytes_in_pipe(fifo_read):
    s = select.select([fifo_read],[],[],0)
    if len(s[0]) > 0:
        buf=bytearray(4)
        fcntl.ioctl(fifo_read, termios.FIONREAD, buf, 1)
        return int.from_bytes(buf, "little")
    else:
        return 0





#-------------------------------------------#
#           _open_pipe_for_reading          #
#-------------------------------------------#
def _open_pipe_for_reading(IPC_FIFO_FP):
    while True:
        if os.path.exists(IPC_FIFO_FP):
            fifo = os.open(IPC_FIFO_FP, os.O_RDONLY | os.O_NONBLOCK)
            break
        else:
            print("...", file=sys.stderr, end="\r")
            time.sleep(0.1)
            continue
    return fifo




##################################################
#           harness_entropy()                    #
##################################################
def harness_entropy(loot_size, cb, endianness="little", IPC_FIFO_FP=kIPC_FIFO_FP):

    """
    loot_size:  count in bytes desired to be pulled from the entropy pool each time
    endianness: to ensure the bits are received the same way generated, this option is available to help
    IPC_FIFO_FP: to override the named pipe file. the default is same as that used by entropythief
    """

    fifo_read = _open_pipe_for_reading(IPC_FIFO_FP)
    try:
        while True:
                yield
                if not os.path.exists(IPC_FIFO_FP):
                    try:
                        os.close(fifo_read)
                    except OSError:
                        pass
                    fifo_read = _open_pipe_for_reading(IPC_FIFO_FP)
                #/if  [!fifo available]
                # count = _count_bytes_in_pipe(fifo_read)
                while _count_bytes_in_pipe(fifo_read) < loot_size:
                    time.sleep(0.1) # rest between ioctl calls or risk crash
                    continue
                #/while  [!payload readable]
                loot = os.read(fifo_read, loot_size)
                cb(loot)
    except GeneratorExit:
        try:
            os.close(fifo_read)
        except OSError:
            pass

