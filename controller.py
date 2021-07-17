#!/usr/bin/env python3
# controller.py
# author: krunch3r (KJM)
# license: poetic/GPL 3

"""
    coordinate activites between the view and the model
    where the model is where Golem task execution occurs
    for more information, see README.md
"""

import model
import os
import sys
import multiprocessing
import time
import utils
import argparse
import view

import fcntl

IMAGE_HASH = "eb9d18bf1262a3f070baae7a7ff5f150233ca00f329ee46f8d089e95"
MAXWORKERS = 3
_MEGABYTE = 1048576
_MAXPOOLSIZE = _MEGABYTE # this is the theoretical max
MINPOOLSIZE = _MAXPOOLSIZE - 4096 # leave one page room to prevent blocking
#MINPOOLSIZE = _MAXPOOLSIZE
BUDGET = 5.0
kIPC_FIFO_FP = "/tmp/pilferedbits"


















###############################################
#        create_fifo_for_writing()            #
###############################################
def create_fifo_for_writing(IPC_FIFO_FP):

    # -overwrite existing
    if os.path.exists(IPC_FIFO_FP):
        os.unlink(IPC_FIFO_FP)
    os.mkfifo(IPC_FIFO_FP)
    # -/overwrite existing

    # -open
    # fifo_for_writing = os.open(IPC_FIFO_FP, os.O_RDWR)
    fifo_for_writing = os.open(IPC_FIFO_FP, os.O_RDWR | os.O_NONBLOCK)
    # -/open
    F_SETPIPE_SZ=1031
    result = fcntl.fcntl(fifo_for_writing, F_SETPIPE_SZ, _MAXPOOLSIZE)

    #F_GETPIPE_SZ=1032 
    #POOL_LIMIT_REPORTED = fcntl.fcntl(fifo_for_writing, 1032)
    return fifo_for_writing







##########################################################
#                      __main__                          #
##########################################################
if __name__ == "__main__":
    # parse cli arguments (viz utils.py)
    args = argparse.Namespace()
    parser = utils.build_parser("pipe entropy to the named pipe /tmp/pilferedbits")
    args = parser.parse_args()
    maindebuglog = open("main.log", "w", buffering=1)
    stderr2file = open("stderr", "w", buffering=1)
    sys.stderr = stderr2file

    # set up {to_,from_}_model_queue
    to_model_q = multiprocessing.Queue()  # message queue TO golem executor process
    from_model_q = multiprocessing.Queue()  # message queue FROM golem executor process

    # setup fifo
    fifoWriteEnd = create_fifo_for_writing(kIPC_FIFO_FP)

    try:
        # instantiate and setup view
        theview = view.View(fifoWriteEnd)

        p1 = multiprocessing.Process(target=model.model__main, daemon=True, args=[args, to_model_q, fifoWriteEnd, from_model_q, MINPOOLSIZE, MAXWORKERS, BUDGET, IMAGE_HASH, args.enable_logging])
        p1.start()
        u = theview.coro_update_mainwindow()
        next(u)
        current_total = 0.0
        count_workers=0
        while True:
            ucmd = theview.getinput(current_total, MINPOOLSIZE, BUDGET, MAXWORKERS, count_workers)
            msg_to_model = None
            if ucmd == "stop":
                raise KeyboardInterrupt
            elif 'set buflim=' in ucmd:
                tokens = ucmd.split("=")
                MINPOOLSIZE = int(tokens[-1])
                msg_to_model = {'cmd': 'set buflim', 'limit': MINPOOLSIZE}
                to_model_q.put_nowait(msg_to_model)
            elif 'set maxworkers=' in ucmd:
                tokens = ucmd.split("=")
                MAXWORKERS = int(tokens[-1])
                msg_to_model = {'cmd': 'set maxworkers', 'count': MAXWORKERS}
                to_model_q.put_nowait(msg_to_model)
            elif ucmd=='restart':
                msg_to_model = {'cmd': 'restart' }
                to_model_q.put_nowait(msg_to_model)
            if msg_to_model:
                print(msg_to_model, file=maindebuglog)
            #/if
            if not from_model_q.empty():
                msg_from_model = from_model_q.get_nowait()
                print(msg_from_model, file=maindebuglog)
                if 'cmd' in msg_from_model and msg_from_model['cmd'] == 'add_bytes':
                    msg = msg_from_model['hexstring']
                    result = u.send(msg)
                elif 'cmd' in msg_from_model and msg_from_model['cmd'] == 'update_total_cost':
                    current_total = msg_from_model['amount']
                elif 'exception' in msg_from_model:
                    raise Exception(msg_from_model['exception'])
                elif 'info' in msg_from_model and msg_from_model['info'] == 'worker started':
                    count_workers+=1
                elif 'info' in msg_from_model and msg_from_model['info'] == 'worker finished':
                    count_workers-=1
                elif 'info' in msg_from_model and msg_from_model['info'] == "payment failed":
                    if BUDGET - current_total < 0.01: # review epsilon
                        msg_to_model = {'cmd': 'pause execution'}
                        print(msg_to_model, file=maindebuglog)
                        to_model_q.put_nowait(msg_to_model)
                elif 'event' in msg_from_model:
                    print(msg_from_model, file=maindebuglog)
            #/if
            theview.refresh()
            time.sleep(0.005)
        #/while
    except Exception as e:
        theview.destroy()
        print(f"\n{e}\n")
    except KeyboardInterrupt:
        theview.destroy()
        print("+=+=+=+=+=+=+=stopping=+=+=+=+=+=+=")
        print("+=+=+=+=+=+=+=settling accounts=+=+=+=+=+=+=")
    finally:
        theview.destroy()
        cmd = {'cmd': 'stop'}
        to_model_q.put_nowait(cmd)
        p1.join()
        while not from_model_q.empty():
            msg_from_model = from_model_q.get_nowait()
            print(msg_from_model, file=maindebuglog)
            if 'cmd' in msg_from_model and msg_from_model['cmd'] == 'update_total_cost':
                current_total = msg_from_model['amount']
            elif 'exception' in msg_from_model:
                raise Exception(msg_from_model['exception'])
        print("Costs incurred were: " + str(current_total) + ".\nOn behalf of the Golem Community, thank you for your participation.")
        maindebuglog.close()
        stderr2file.close()
        # instead of closing the write end, leave it open for any pending bits that may be needed by a reader
        os.close(fifoWriteEnd)
        os.unlink(kIPC_FIFO_FP)
