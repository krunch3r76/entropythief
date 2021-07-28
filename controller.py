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
import argparse
import view
import fcntl

import utils

IMAGE_HASH = "238e362f7b52aa21c3f2a26ade9ba3952ae8c715c9efe37af0ef8258"
MAXWORKERS = 3
_MEBIBYTE = 2**20
_MAXPOOLSIZE = 1000 * _MEBIBYTE # this is the theoretical max
MINPOOLSIZE = _MAXPOOLSIZE
#MINPOOLSIZE= 30000 - 4096
BUDGET = 20.0
kIPC_FIFO_FP = "/tmp/pilferedbits"


















##########################################################
#                      __main__                          #
##########################################################
if __name__ == "__main__":
    debug_list = []
    # parse cli arguments (viz utils.py)
    args = argparse.Namespace()
    parser = utils.build_parser("pipe entropy to the named pipe /tmp/pilferedbits")
    args = parser.parse_args()
    maindebuglog = open("main.log", "w", buffering=1)
    stderr2file = open("stderr", "w", buffering=1)
    # devdebuglog = open("devdebug.log", "w", buffering=1)
    sys.stderr = stderr2file

    # set up {to_,from_}_model_queue
    to_model_q = multiprocessing.Queue()  # message queue TO golem executor process
    from_model_q = multiprocessing.Queue()  # message queue FROM golem executor process

    # setup fifo
    # fifoWriteEnd = create_fifo_for_writing(kIPC_FIFO_FP)

    try:
        # instantiate and setup view
        theview = view.View()
        # invoke model__main on separate process
        p1 = multiprocessing.Process(target=model.model__main, daemon=True
                , args=[args
                    , to_model_q
                    , None
                    , from_model_q
                    , MINPOOLSIZE
                    , MAXWORKERS
                    , BUDGET
                    , IMAGE_HASH
                    , args.enable_logging
                    ])
        payment_failed_count=0
        p1.start()
        u = theview.coro_update_mainwindow()
        next(u)
        current_total = 0.0
        count_workers=0
        bytesInPipe = 0
        while True:
            ucmd = theview.getinput(current_total, MINPOOLSIZE, BUDGET, MAXWORKERS, count_workers, bytesInPipe)
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
                if not ('cmd' in msg_from_model and msg_from_model['cmd'] == 'add_bytes'):
                    print(msg_to_model, file=maindebuglog)
            #/if
            if not from_model_q.empty():
                msg_from_model = from_model_q.get_nowait()
                print(msg_from_model, file=maindebuglog)
                if 'cmd' in msg_from_model and msg_from_model['cmd'] == 'add_bytes':
                    msg = msg_from_model['hexstring']
                    if msg in debug_list:
                        print("WTF!")
                        raise
                    debug_list.append(msg)

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
                    payment_failed_count+=1
                    if BUDGET - current_total < 0.01 or payment_failed_count==25: # review epsilon
                        msg_to_model = {'cmd': 'pause execution'}
                        print(msg_to_model, file=maindebuglog)
                        to_model_q.put_nowait(msg_to_model)
                elif 'event' in msg_from_model:
                    print(msg_from_model, file=maindebuglog)
                elif 'debug' in msg_from_model:
                    print(msg_from_model, file=devdebuglog)
                elif 'bytesInPipe' in msg_from_model:
                    bytesInPipe = msg_from_model['bytesInPipe']
                elif 'model exception' in msg_from_model:
                    theview.destroy()
                    print(msg_from_model)
                    raise KeyboardInterrupt

            #/if
            theview.refresh()
            time.sleep(0.005)
        #/while
    except Exception as e:
        theview.destroy()
        print(f"\n{e}\n")
    except KeyboardInterrupt:
        cmd = {'cmd': 'stop'}
        to_model_q.put_nowait(cmd)
        theview.destroy()
        print("+=+=+=+=+=+=+=stopping=+=+=+=+=+=+=")
        print("+=+=+=+=+=+=+=settling accounts=+=+=+=+=+=+=")
        raise
    finally:
        theview.destroy()
        cmd = {'cmd': 'stop'}
        to_model_q.put_nowait(cmd)
        p1.join(30) # a daemonized process need not be joined?
        while not from_model_q.empty():
            msg_from_model = from_model_q.get_nowait()
            print(msg_from_model, file=maindebuglog)
            if 'cmd' in msg_from_model and msg_from_model['cmd'] == 'update_total_cost':
                current_total = msg_from_model['amount']
            elif 'exception' in msg_from_model:
                print("unhandled exception reported by model:\n")
                print(msg_from_model['exception'])
                # raise Exception(msg_from_model['exception'])
        print("Costs incurred were: " + str(current_total) + ".\nOn behalf of the Golem Community, thank you for your participation.")
        stderr2file.close()
