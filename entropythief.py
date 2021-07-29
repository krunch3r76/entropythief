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
import locale

import utils

IMAGE_HASH = "238e362f7b52aa21c3f2a26ade9ba3952ae8c715c9efe37af0ef8258"
MAXWORKERS = 5                       # ideal number of workers to provision to at a time
_kMEBIBYTE = 2**20                   # constant count
MINPOOLSIZE = 100 * _kMEBIBYTE       # as as buflim, the most random bytes that will be buffered at time
BUDGET = 2.0                         # maximum budget (as of this version runtime constant)


















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
    devdebuglog = open("devdebug.log", "w", buffering=1) # special log messaging for debugging purposes
    sys.stderr = stderr2file

    # set up {to_,from_}_model_queue
    to_model_q = multiprocessing.Queue()  # message queue TO golem executor process
    from_model_q = multiprocessing.Queue()  # message queue FROM golem executor process


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
                break
            elif 'set buflim=' in ucmd:
                tokens = ucmd.split("=")
                MINPOOLSIZE = int(eval(tokens[-1]))
                msg_to_model = {'cmd': 'set buflim', 'limit': MINPOOLSIZE}
                to_model_q.put_nowait(msg_to_model)
            elif 'set maxworkers=' in ucmd:
                tokens = ucmd.split("=")
                MAXWORKERS = int(tokens[-1])
                msg_to_model = {'cmd': 'set maxworkers', 'count': MAXWORKERS}
                to_model_q.put_nowait(msg_to_model)
            elif ucmd=='restart':
                payment_failed_count=0 # reset counter
                msg_to_model = {'cmd': 'unpause execution' }
                to_model_q.put_nowait(msg_to_model)
            elif 'set budget=' in ucmd:
                tokens = ucmd.split("=")
                BUDGET = float(tokens[-1])
                msg_to_model = {'cmd': 'set budget', 'budget': BUDGET}
                to_model_q.put_nowait(msg_to_model)


            #/if
            if not from_model_q.empty():
                msg_from_model = from_model_q.get_nowait()

                # log most msg's to maindebuglog (main.log)
                if msg_from_model:
                    if 'bytesInPipe' in msg_from_model:
                        pass # don't fill up log file with this
                    if not ('cmd' in msg_from_model and msg_from_model['cmd'] == 'add_bytes'):
                        print(msg_from_model, file=maindebuglog)
                    else:
                        concat_msg = { msg_from_model['cmd']: len(msg_from_model['hexstring']) }
                        print(concat_msg, file=maindebuglog)

                if 'cmd' in msg_from_model and msg_from_model['cmd'] == 'add_bytes':
                    msg = msg_from_model['hexstring']
                    result = u.send(msg)
                if 'cmd' in msg_from_model and msg_from_model['cmd'] == 'add cost':
                    current_total += msg_from_model['amount']
                elif 'exception' in msg_from_model:
                    raise Exception(msg_from_model['exception'])
                elif 'info' in msg_from_model and msg_from_model['info'] == 'worker started':
                    count_workers+=1
#                elif 'info' in msg_from_model and msg_from_model['info'] == 'worker finished':
                elif 'event' in msg_from_model and msg_from_model['event'] == 'AgreementTerminated':
                    count_workers-=1
                elif 'info' in msg_from_model and msg_from_model['info'] == "payment failed":
                    payment_failed_count+=1
                    if BUDGET - current_total < 0.01 or payment_failed_count==10: # review epsilon
                        # to be implemented
                        msg_to_model = {'cmd': 'pause execution'} # give the logs a rest, don't bother requesting until budget is increased
                        to_model_q.put_nowait(msg_to_model)
                        # print(msg_to_model, file=maindebuglog)
                elif 'event' in msg_from_model:
                    print(msg_from_model, file=maindebuglog)
                elif 'debug' in msg_from_model:
                    print(msg_from_model, file=devdebuglog)
                elif 'bytesInPipe' in msg_from_model:
                    bytesInPipe = msg_from_model['bytesInPipe']
                elif 'model exception' in msg_from_model:
                    theview.destroy()
                    print(utils.TEXT_COLOR_BLUE + "The model threw the following exception:" + utils.TEXT_COLOR_DEFAULT + "\n" + msg_from_model['model exception']['name'] + "\n" + msg_from_model['model exception']['what'])
                    break
            #/if
            theview.refresh()
            time.sleep(0.005)
        #/while
    except KeyboardInterrupt:
        pass # go onto finally
    except Exception as e:
        theview.destroy()
        print("generic exception from entropythief controller:")
        print(f"{e}\n")
    finally:
        theview.destroy()
        print("+=+=+=+=+=+=+=stopping and settling accounts=+=+=+=+=+=+=")
        bytesPurchased = 0
        if p1.is_alive():
            cmd = {'cmd': 'stop'}
            to_model_q.put_nowait(cmd)
            # get pending messages from the model to update total cost or report on "returned" exceptions (may not be implemented yet)
            daemon_exited = False
            while not daemon_exited:
                if not from_model_q.empty(): # revise boolean efficiency
                    msg_from_model = from_model_q.get_nowait()
                    print(msg_from_model, file=maindebuglog)
                    if 'cmd' in msg_from_model and msg_from_model['cmd'] == 'add cost':
                        current_total += msg_from_model['amount']
                    if 'bytesPurchased' in msg_from_model:
                        bytesPurchased = msg_from_model['bytesPurchased']
                    elif 'exception' in msg_from_model:
                        print("unhandled exception reported by model:\n")
                        print(msg_from_model['exception'])
                    elif 'daemon' in msg_from_model:
                        daemon_exited = True
                        print("DEV MESSAGE: DAEMON EXITED")
                time.sleep(0.0001)

        print("Costs incurred were: " + str(current_total))
        locale.setlocale(locale.LC_NUMERIC, '')
        print("Bytes purchased were: " + locale.format_string("%d", bytesPurchased, grouping=True))
        if bytesPurchased > 0:
            rate = float(current_total/bytesPurchased)*1000*_kMEBIBYTE
            print("cost/gigabyte: " + ("%6f" % rate) )
        print("\nOn behalf of the Golem Community, thank you for your participation.")
        stderr2file.close()
