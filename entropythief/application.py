#!/usr/bin/env python3
# entropythief.py
# author: krunch3r (KJM)
# license: poetic/GPL 3

"""
    coordinate activites between the view and the model
    where the model is where Golem task execution occurs
    for more information, see README.md
"""


import os
import sys
import multiprocessing
import time
import argparse
import fcntl
import locale
import asyncio

from . import utils
from . import view
from . import model
from .TaskResultWriter import Interleaver

_kMEBIBYTE  = 2**20                   # constant count


_DEBUGLEVEL = True if 'PYTHONDEBUGLEVEL' in os.environ else False


"""
    Controller
    ----------
    IMAGE_HASH                      " the hash link for providers to look up the image
    MAXWORKERS                      " the number of workers to provision per network request {dynamic}
    MINPOOLSIZE                     " the target maximum number of random bytes available for reading (misnomer!) {dynamic}
    BUDGET                          " the most the client is willing to spend before pausing execution

    to_model_q                      " signals going to the model
    from_model_q                    " signals coming from the model
    count_workers                   " the number of active workers in the current execution
    bytesInPipe                     " the number of bytes that the model has made available for reading
    payment_failed_count            " the current count of successive payment failure events
    current_total                   " the total costs so far
    theview                         " the view object
    themodeltask                    " the model (runs Golem) task object
    u_update_main_window            " generator that writes the input hexstring to the display

    _hook_model(...)                 " handles the last message from the model (queue element)
    _hook_view(...)                  " handles the last message from the view (return value)
    __call__()                      " start provisioning to obtain random bytes

    internal dependencies: [ 'view.py', 'model.py', 'utils.py' ]

    summary:

        The controller is initialized and called from main asynchronously. By default it is initialized
        with a subclass of the abstract class TaskResultWriter, Interleaver. The
        client may subclass TaskResultWriter if interested in handling the task results in an alternative
        fashion than that to Interleaver (see TaskResultWriter.py).
        
        The Controller initializes the controller-view and when __call__ed begins provisioning work via
        the model according to the current BUDGET vs current_total, and current MINPOOLSIZE vs bytesInPipe.
        Execution is paused if several (10) successive payment failures occur or the current_total is at
        least within a small amount (0.01) of the BUDGET, and the client must issue a restart command.

        The Controller runs in a loop to poll and process events from the view and the model asynchronously.
        
        The view has two components: a display and a input box. If new data (a hexstream) is received from
        the model, it is fed to a generator on the view to update the display. The generator will write
        all or a portion of the stream and queue further writes for later to return control for the
        other asynchronous operations. The controller sends empty messages to the view to prompt for
        writing any buffered display data. On each iteration, the controller also updates the input
        box, and its status indicators (e.g. worker count, costs, bytesInPipe), and receives and
        processes any input from the client.

        The model asynchronously requests work whenever there is available funds and the bytes in the
        writer have fallen beneath a target level (half the MINPOOLSIZE). The results from the last
        pool are sent as a signal to controller for processing. The model sends various signals to
        the controller about its state including events during work (such as PaymentAccepted events
        to track current_total costs) and state information about the PipeWriter, specifically the
        number of total bytes stored/readable.

        flow:
        initialize model to start work on Golem
        \---------------model------------------------
        /  -> handle signal  from controller        | 
        |  <- emit work results                     |
        |  <- emit Golem specific events            |
        |  <- emit total bytes in writer            /
        --------------------------------------------\

        \---------------view-------------------------
        /  -> handle signal from controller         |
        |   -> (display) handle new a hexstring     |
        |   -> (box) handle status updates          |
        |  <- (box) emit client input               /
        --------------------------------------------\

        >-------------- controller ------------------------------
        |                                                       |
        | update status line and receive client input (if any)  |
        | process client input                                  |
        | process model signal                                  |
        |    refresh display if signal is a task pool result    |
        | flush writes to display                               |
        --------------------------------------------------------<
        X read closing messages from message queue to get
           stats (namely bytesPurchased)
"""

class Controller:

    IMAGE_HASH  = "81e0a936ef13f89622e1b59f3934caf8109244c5f8f6998f0f338ed6"
    MAXWORKERS  = 5
    MINPOOLSIZE = 10 * _kMEBIBYTE + 5
    BUDGET      = 2.0
    DEVELOPERDEBUG=_DEBUGLEVEL
    to_model_q = asyncio.Queue()
    from_model_q = asyncio.Queue()
   
    count_workers = 0
    bytesInPipe = 0
    payment_failed_count = 0
    current_total = 0.0
    whether_paused = True

    theview = None
    themodeltask = None
    u_update_main_window = None # generator (function with state) to write some output to main display






 # __          __   __          
# |  \        |  \ |  \         
 # \▓▓_______  \▓▓_| ▓▓_        
# |  \       \|  \   ▓▓ \       
# | ▓▓ ▓▓▓▓▓▓▓\ ▓▓\▓▓▓▓▓▓       
# | ▓▓ ▓▓  | ▓▓ ▓▓ | ▓▓ __      
# | ▓▓ ▓▓  | ▓▓ ▓▓ | ▓▓|  \     
# | ▓▓ ▓▓  | ▓▓ ▓▓  \▓▓  ▓▓     
 # \▓▓\▓▓   \▓▓\▓▓   \▓▓▓▓      
                              
                              
                              
    #   ---------Controller------------
    def __init__(self, loop):
    #   -------------------------------
    # comments: starts golem task
        # parse cli arguments (viz utils.py)
        self.args = argparse.Namespace() # redundant?
        parser = utils.build_parser("pipe entropy to the named pipe /tmp/pilferedbits")
        self.args = parser.parse_args()

        # setup console streams
        self.mainlog = open("main.log", "w", buffering=1) # monitoring events mostly or other things thought informative for dev ideas
        self.devdebuglog = open("devdebug.log", "w", buffering=1) # special log messaging for temporary debugging purposes
        self.stderr2file = open("stderr", "w", buffering=1) # messages from project and if logging enabled INFO messages from rest
        sys.stderr = self.stderr2file # replace stderr stream with file stream

        if self.MINPOOLSIZE < 2**20: # enforce minimum pool size
            self.MINPOOLSIZE = 2**20

        self.theview = view.View()

        # self.taskResultWriter = Interleaver(self.to_ctl_q, self.MINPOOLSIZE)

        self.themodeltask=loop.create_task(model.model__EntropyThief(loop
            , self.args
            , self.to_model_q
            , self.from_model_q
            , self.MINPOOLSIZE
            , self.MAXWORKERS
            , self.BUDGET
            , self.IMAGE_HASH
            , Interleaver(self.from_model_q, self.MINPOOLSIZE)
            )()
            )


        # setup generator that writes any buffered bytes to the main display
        self.u_update_main_window = self.theview.coro_update_mainwindow()
        next(self.u_update_main_window)




                   # __ __ 
                  # |  \  \
  # _______  ______ | ▓▓ ▓▓
 # /       \|      \| ▓▓ ▓▓
# |  ▓▓▓▓▓▓▓ \▓▓▓▓▓▓\ ▓▓ ▓▓
# | ▓▓      /      ▓▓ ▓▓ ▓▓
# | ▓▓_____|  ▓▓▓▓▓▓▓ ▓▓ ▓▓
 # \▓▓     \\▓▓    ▓▓ ▓▓ ▓▓
  # \▓▓▓▓▓▓▓ \▓▓▓▓▓▓▓\▓▓\▓▓
                         
    # this is the main entrypoint!                     
                         
    #   ---------Controller------------
    async def __call__(self):
    #   -------------------------------

        if not self.args.start_paused:
            msg_to_model = {'cmd': 'unpause execution' }
            self.to_model_q.put_nowait(msg_to_model)
            self.whether_paused=False

        try:
            while True:

                #########################################################
                #   update status line and receive client input if any  #
                #########################################################
                ucmd = self.theview.getinput(self.current_total
                        , self.MINPOOLSIZE
                        , self.BUDGET
                        , self.MAXWORKERS
                        , self.count_workers
                        , self.bytesInPipe
                        , self.whether_paused)
                
                #############################################
                #   process any client input                #
                #############################################
                #   exit loop on "error" or request to stop #
                if ucmd:                                    #
                    ERROR = self._hook_view(ucmd)
                    if ERROR:
                        break

                #####################################################
                #   process model signal                            #
                #####################################################
                # internally calls self.u_update_main_window
                # exit loop on error
                if not self.from_model_q.empty():
                    msg_from_model = self.from_model_q.get_nowait()
                    ERROR = self._hook_model(msg_from_model)
                    if ERROR:
                        break

                #############################################
                #   flush writes to display                 #     
                #############################################
                REFRESH = next(self.u_update_main_window)
                if REFRESH:
                    self.theview.refresh()

                await asyncio.sleep(0.01)
            #/while
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.theview.destroy()
            print("generic exception from entropythief controller:")
            print(e.__class__.__name__)
            print(e)
        except asyncio.CancelledError:
            print("\n\nasyncio cancellederror\n\n")
        finally:
            self.theview.destroy()
            # sys.stderr=sys.__stderr__
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
                        msg_from_model = self.from_model_q.get_nowait()
                        # if self.DEVELOPERDEBUG:
                        #     if 'hex' in msg_from_model:
                        #         print(len(msg_from_model['hex']))
                        #     else:
                        #         print(msg_from_model)
                        if 'bytesPurchased' in msg_from_model:
                            bytesPurchased = msg_from_model['bytesPurchased']
                        elif 'event' in msg_from_model and msg_from_model['event'] == 'PaymentAccepted':
                            self.current_total += float(msg_from_model['amount'])
                        elif 'exception' in msg_from_model:
                            print("unhandled exception reported by model:\n")
                            print(msg_from_model['exception'])
                        elif 'daemon' in msg_from_model:
                            daemon_exited = True
                    await asyncio.sleep(0.01)
                await self.themodeltask

            locale.setlocale(locale.LC_NUMERIC, '')
            print("Bytes purchased were: " + locale.format_string("%d", bytesPurchased, grouping=True))
            if bytesPurchased > 0:
                rate = float(self.current_total/bytesPurchased)*1000*_kMEBIBYTE
                print("cost/gigabyte: " + ("%6f" % rate) )
            print()
            print(utils.TEXT_COLOR_GREEN + "Costs incurred were: " + str(self.current_total) + utils.TEXT_COLOR_DEFAULT)
            print(utils.TEXT_COLOR_WHITE + "\nOn behalf of the Golem Community, thank you for your participation." + utils.TEXT_COLOR_DEFAULT)
            self.stderr2file.close()





    #   ---------Controller------------
    def _hook_model(self, msg_from_model):
    #   -------------------------------
    # process model signal
    # post: current_total, count_workers, payment_failed_count, bytesInPipe, ui updated
    # output: error is true if an exception occurs
        ERROR = False
        # log most msg's to mainlog (main.log)
        if 'cmd' in msg_from_model and msg_from_model['cmd'] == 'add_bytes':
            # msg = msg_from_model['hexstring']
            msg = msg_from_model['hex'].hex()
            self.u_update_main_window.send(msg) # TODO coroutine only updates one line at a time, buffering between calls
            concat_msg = { msg_from_model['cmd']: len(msg_from_model['hex']) }
            print(concat_msg, file=self.mainlog)
        elif 'exception' in msg_from_model:
            raise Exception(msg_from_model['exception'])
        elif 'info' in msg_from_model and msg_from_model['info'] == 'worker started':
            self.count_workers+=1
        elif 'info' in msg_from_model and msg_from_model['info'] == "payment failed":
            self.payment_failed_count+=1
            if self.BUDGET - self.current_total < 0.02 or self.payment_failed_count==10: # review epsilon
                msg_to_model = {'cmd': 'pause execution'}; self.to_model_q.put_nowait(msg_to_model)
                self.whether_paused=True
        elif 'event' in msg_from_model and msg_from_model['event'] == 'AgreementTerminated':
            self.count_workers-=1
        elif 'event' in msg_from_model and msg_from_model['event'] == 'PaymentAccepted':
            self.current_total += float(msg_from_model['amount'])
        elif 'event' in msg_from_model:
            print(msg_from_model, file=self.mainlog) # report event to developer stream
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
    def _hook_view(self, ucmd):
    #   -------------------------------
    # process client input
    # post: MINPOOLSIZE, MAXWORKERS, payment_failed_count, BUDGET
    # output: error true is view asks controller to stop
        ERROR = False
        if ucmd == "stop":
            ERROR = True
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
        elif ucmd=='restart' or ucmd=='start':
            self.payment_failed_count=0 # reset counter
            msg_to_model = {'cmd': 'unpause execution' }
            self.to_model_q.put_nowait(msg_to_model)
            self.whether_paused=False
        elif 'set budget=' in ucmd:
            tokens = ucmd.split("=")
            self.BUDGET = float(tokens[-1])
            msg_to_model = {'cmd': 'set budget', 'budget': self.BUDGET}
            self.to_model_q.put_nowait(msg_to_model)
        elif ucmd =='pause':
            msg_to_model = {'cmd': 'pause execution'}; self.to_model_q.put_nowait(msg_to_model)
            self.whether_paused=True
        return ERROR










def main():
    loop = asyncio.get_event_loop()
    controller = Controller(loop)
    task = loop.create_task(controller())
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        loop.run_until_complete(task)
        print(task.exception(), file=sys.stderr)
    finally:
        print("\nCREDITS")
        print("entropythief was inspired by gandom https://github.com/reza-hackathons/gandom")
        print("the splash screen ascii art was obtained from https://asciiart.website/index.php?art=logos%20and%20insignias/smiley")


