#!/usr/bin/env python3
# entropythief.py
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
import fcntl
import locale
import asyncio

import utils
import view



class Controller:

    IMAGE_HASH  = "81e0a936ef13f89622e1b59f3934caf8109244c5f8f6998f0f338ed6"
    MAXWORKERS  = 5                      # ideal number of workers to provision to at a time
    _kMEBIBYTE  = 2**20                   # constant count
    MINPOOLSIZE = 10 * _kMEBIBYTE + 5      # as as buflim, the most random bytes that will be buffered at time
    BUDGET      = 2.0                         # maximum budget (as of this version runtime constant)
    DEVELOPERDEBUG=False
    to_model_q = asyncio.Queue()
    from_model_q = asyncio.Queue()
   
    count_workers = 0
    bytesInPipe = 0
    payment_failed_count = 0
    current_total = 0.0

    theview = None
    u_update_main_window = None # generator to write output to main display






    #   ---------Controller------------
    def __init__(self):
    #   -------------------------------
        # parse cli arguments (viz utils.py)
        self.args = argparse.Namespace() # redundant?
        parser = utils.build_parser("pipe entropy to the named pipe /tmp/pilferedbits")
        self.args = parser.parse_args()

        # setup console streams
        self.maindebuglog = open("main.log", "w", buffering=1) # monitoring events mostly or other things thought informative for dev ideas
        self.devdebuglog = open("devdebug.log", "w", buffering=1) # special log messaging for temporary debugging purposes
        self.stderr2file = open("stderr", "w", buffering=1) # messages from project and if logging enabled INFO messages from rest
        sys.stderr = self.stderr2file # replace stderr stream with file stream

        if self.MINPOOLSIZE < 2**20: # enforce minimum pool size
            self.MINPOOLSIZE = 2**20

        self.theview = view.View()



        self.loop = asyncio.get_running_loop()
        self.loop.create_task(model.model__main( self.args
            , self.to_model_q
            , None
            , self.from_model_q
            , self.MINPOOLSIZE
            , self.MAXWORKERS
            , self.BUDGET
            , self.IMAGE_HASH
            , self.args.enable_logging
            ))

        # setup generator to update the view's main display to write any pending/buffered pages of hex
        self.u_update_mainwindow = self.theview.coro_update_mainwindow()
        next(self.u_update_mainwindow)





    #   ---------Controller------------
    def hook_model(self, msg_from_model):
    #   -------------------------------
    # post: current_total, count_workers, payment_failed_count, bytesInPipe, ui updated
        ERROR = False
        # log most msg's to maindebuglog (main.log)
        if 'cmd' in msg_from_model and msg_from_model['cmd'] == 'add_bytes':
            msg = msg_from_model['hexstring']
            self.u_update_mainwindow.send(msg) # TODO coroutine only updates one line at a time, buffering between calls
            concat_msg = { msg_from_model['cmd']: len(msg_from_model['hexstring']) }
            print(concat_msg, file=self.maindebuglog)
        elif 'cmd' in msg_from_model and msg_from_model['cmd'] == 'add cost':
            self.current_total += msg_from_model['amount']
        elif 'exception' in msg_from_model:
            raise Exception(msg_from_model['exception'])
        elif 'info' in msg_from_model and msg_from_model['info'] == 'worker started':
            self.count_workers+=1
        elif 'event' in msg_from_model and msg_from_model['event'] == 'AgreementTerminated':
            self.count_workers-=1
        elif 'info' in msg_from_model and msg_from_model['info'] == "payment failed":
            self.payment_failed_count+=1
            if self.BUDGET - self.current_total < 0.01 or self.payment_failed_count==10: # review epsilon
                # to be implemented
                msg_to_model = {'cmd': 'pause execution'} # give the logs a rest, don't bother requesting until budget is increased
                to_model_q.put_nowait(msg_to_model)
        elif 'event' in msg_from_model:
            print(msg_from_model, file=self.maindebuglog) # report event to developer stream
        elif 'debug' in msg_from_model:
            print(msg_from_model, file=self.devdebuglog) # record debug message
        elif 'bytesInPipe' in msg_from_model:
            self.bytesInPipe = msg_from_model['bytesInPipe']
        elif 'model exception' in msg_from_model:
            self.theview.destroy() # to do, use the idiomatic del?
            print(utils.TEXT_COLOR_BLUE + "The model threw the following exception:" + utils.TEXT_COLOR_DEFAULT + "\n" + msg_from_model['model exception']['name'] + "\n" + msg_from_model['model exception']['what'])
            ERROR = True
        return ERROR








    #   ---------Controller------------
    def hook_view(self, ucmd):
    #   -------------------------------
    # post: MINPOOLSIZE, MAXWORKERS, payment_failed_count, BUDGET
    # output: error true is view asks controller to stop
        ERROR = False
        if ucmd == "stop":
            Error = True
        elif 'set buflim=' in ucmd:
            tokens = ucmd.split("=")
            self.MINPOOLSIZE = int(eval(tokens[-1]))
            if self.MINPOOLSIZE < 2**20:
                self.MINPOOLSIZE = 2**20 # the pool writer minimum buffer size is set to 1 MiB
                # ideally this requirement would be done on the model end and an update occur over the wire
                # TODO
            msg_to_model = {'cmd': 'set buflim', 'limit': self.MINPOOLSIZE}
            self.to_model_q.put_nowait(msg_to_model)
        elif 'set maxworkers=' in ucmd:
            tokens = ucmd.split("=")
            self.MAXWORKERS = int(tokens[-1])
            msg_to_model = {'cmd': 'set maxworkers', 'count': self.MAXWORKERS}
            self.to_model_q.put_nowait(msg_to_model)
        elif ucmd=='restart':
            self.payment_failed_count=0 # reset counter
            self.msg_to_model = {'cmd': 'unpause execution' }
            self.to_model_q.put_nowait(msg_to_model)
        elif 'set budget=' in ucmd:
            tokens = ucmd.split("=")
            self.BUDGET = float(tokens[-1])
            msg_to_model = {'cmd': 'set budget', 'budget': BUDGET}
            self.to_model_q.put_nowait(msg_to_model)
        return ERROR







    #   ---------Controller------------
    async def __call__(self):
    #   -------------------------------
        try:
            # instantiate and setup view

            while True:
                # update the views status line and get any complete input
                ucmd = self.theview.getinput(self.current_total, self.MINPOOLSIZE, self.BUDGET, self.MAXWORKERS, self.count_workers, self.bytesInPipe)
                # handle message from view
                if ucmd:
                    ERROR = self.hook_view(ucmd)
                    if ERROR:
                        break

                # handle mesage from model
                if not self.from_model_q.empty():
                    msg_from_model = self.from_model_q.get_nowait()
                    ERROR = self.hook_model(msg_from_model)
                    if ERROR:
                        break

                next(self.u_update_mainwindow)
                self.theview.refresh()
                await asyncio.sleep(0.01)
            #/while
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.theview.destroy()
            print("generic exception from entropythief controller:")
            msg = {'model exception': {'name': e.__class__.__name__, 'what': str(e) } }
            print(msg)
        except asyncio.CancelledError:
            print("\n\nasyncio cancellederror\n\n")
        finally:
            self.theview.destroy()
            print("+=+=+=+=+=+=+=stopping and settling accounts=+=+=+=+=+=+=")
            bytesPurchased = 0
            if True:
                print("asking entropythief golem executor to stop provisioning")
                cmd = {'cmd': 'stop'}
                self.to_model_q.put_nowait(cmd)
                # get pending messages from the model to update total cost or report on "returned" exceptions (may not be implemented yet)
                daemon_exited = False
                while not daemon_exited:
                    if not self.from_model_q.empty(): # revise boolean efficiency
                        msg_from_model = from_model_q.get_nowait()
                        if DEVELOPERDEBUG:
                            print(msg_from_model)
                        if 'cmd' in msg_from_model and msg_from_model['cmd'] == 'add cost':
                            self.current_total += msg_from_model['amount']
                        if 'bytesPurchased' in msg_from_model:
                            bytesPurchased = msg_from_model['bytesPurchased']
                        elif 'exception' in msg_from_model:
                            print("unhandled exception reported by model:\n")
                            print(msg_from_model['exception'])
                        elif 'daemon' in msg_from_model:
                            daemon_exited = True
                    await asyncio.sleep(0.01)

            locale.setlocale(locale.LC_NUMERIC, '')
            print("Bytes purchased were: " + locale.format_string("%d", bytesPurchased, grouping=True))
            if bytesPurchased > 0:
                rate = float(self.current_total/bytesPurchased)*1000*_kMEBIBYTE
                print("cost/gigabyte: " + ("%6f" % rate) )
            print()
            print(utils.TEXT_COLOR_GREEN + "Costs incurred were: " + str(self.current_total) + utils.TEXT_COLOR_DEFAULT)
            print(utils.TEXT_COLOR_WHITE + "\nOn behalf of the Golem Community, thank you for your participation." + utils.TEXT_COLOR_DEFAULT)
            self.stderr2file.close()








##########################################################
#                      __main__                          #
##########################################################
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    controller = Controller()
    task = loop.create_task(controller())
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        loop.run_until_complete(task)
        print(task.exception(), file=sys.stderr)
    finally:
        pass

