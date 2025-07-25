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
import platform
import subprocess
import shutil
import datetime

# Note: EntopyThief is a pure writer - expects external reader to be connected

from . import utils
from . import view
from . import model
from .TaskResultWriter import Interleaver

_kMEBIBYTE = 2**20  # constant count


_DEBUGLEVEL = True if "PYTHONDEBUGLEVEL" in os.environ else False


class Controller:
    """asynchronously interacts with the view and model"""

    IMAGE_HASH = "2cab8ac654056acbb90baaf208d253b9a10172c7139e40f8d20fbfd6de67711d"
    MAXWORKERS = 5
    ENTROPY_BUFFER_CAPACITY = 10 * _kMEBIBYTE + 5
    BUDGET = 2.0
    DEVELOPERDEBUG = _DEBUGLEVEL
    to_model_q = asyncio.Queue()
    from_model_q = asyncio.Queue()

    count_workers = 0
    bytesInPipe = 0
    payment_failed_count = 0
    current_total = 0.0
    whether_paused = True

    theview = None
    themodeltask = None
    u_update_main_window = (
        None  # generator (function with state) to write some output to main display
    )

    #   ---------Controller------------
    def __init__(self, loop, args):
        """initializes object, asynchronously launches golem task, sets up view coroutine"""
        # parse cli arguments (viz utils.py)
        # self.args = argparse.Namespace() # redundant?
        # parser = utils.build_parser("pipe entropy to the named pipe /tmp/pilferedbits")
        # self.args = parser.parse_args()
        self.args = args

        # setup console streams - clear logs on each run
        self.mainlog = open(
            "main.log", "w", buffering=1
        )  # monitoring events mostly or other things thought informative for dev ideas
        self.devdebuglog = open(
            "devdebug.log", "w", buffering=1
        )  # special log messaging for temporary debugging purposes
        self.stderr2file = open(
            "stderr", "w", buffering=1
        )  # messages from project and if logging enabled INFO messages from rest
        sys.stderr = self.stderr2file  # replace stderr stream with file stream
        
        # Clear PipeWriter log file on startup
        import os
        import datetime
        os.makedirs('.logs', exist_ok=True)
        with open('.logs/pipewriter.log', 'w') as f:
            f.write("")  # Clear the file
            
        # Log session start in main logs
        session_start = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"=== EntopyThief Session Started: {session_start} ===", file=self.mainlog)
        print(f"=== EntopyThief Session Started: {session_start} ===", file=self.stderr2file)

        if self.ENTROPY_BUFFER_CAPACITY < 2*2**20:  # enforce minimum pool size
            self.ENTROPY_BUFFER_CAPACITY = 2*2**20

        self.theview = view.View(concealedview=self.args.conceal_view)

        # EntopyThief is a pure writer - external reader should already be connected

        # self.taskResultWriter = Interleaver(self.to_ctl_q)

        self.themodeltask = loop.create_task(
            model.model__EntropyThief(
                loop=loop,
                args=self.args,
                from_ctl_q=self.to_model_q,
                to_ctl_q=self.from_model_q,
                ENTROPY_BUFFER_CAPACITY=self.ENTROPY_BUFFER_CAPACITY,
                MAXWORKERS=self.MAXWORKERS,
                BUDGET=self.BUDGET,
                IMAGE_HASH=self.IMAGE_HASH,
                taskResultWriter=Interleaver(self.from_model_q),
            )()
        )

        # setup generator that writes any buffered bytes to the main display
        self.u_update_main_window = self.theview.coro_update_mainwindow()
        next(self.u_update_main_window)

        if platform.system() == "Linux":
            try:
                subprocess.Popen(
                    ["aplay", "entropythief/sounds/903__sleep__weird-loop-1.wav"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except:
                pass

    #   ---------Controller------------
    async def __call__(self):
        """asynchronously loops to handle and relay signals between the model and view"""
        if not self.args.start_paused:
            msg_to_model = {"cmd": "unpause execution"}
            self.to_model_q.put_nowait(msg_to_model)
            self.whether_paused = False

        try:
            while True:

                #########################################################
                #   update status line and receive client input if any  #
                #########################################################
                ucmd = self.theview.getinput(
                    self.current_total,
                    self.ENTROPY_BUFFER_CAPACITY,
                    self.BUDGET,
                    self.MAXWORKERS,
                    self.count_workers,
                    self.bytesInPipe,
                    self.whether_paused,
                )

                #############################################
                #   process any client input                #
                #############################################
                #   exit loop on "error" or request to stop #
                if ucmd:  #
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

                await asyncio.sleep(0.001)  # 1ms for responsive UI (was 0.01 = 10ms)
            # /while
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
                cmd = {"cmd": "stop"}
                self.to_model_q.put_nowait(cmd)
                # get pending messages from the model to update total cost or report on "returned" exceptions (may not be implemented yet)
                daemon_exited = False
                while not daemon_exited:
                    if not self.from_model_q.empty():  # revise boolean efficiency
                        msg_from_model = self.from_model_q.get_nowait()
                        # if self.DEVELOPERDEBUG:
                        #     if 'hex' in msg_from_model:
                        #         print(len(msg_from_model['hex']))
                        #     else:
                        #         print(msg_from_model)
                        if "bytesPurchased" in msg_from_model:
                            bytesPurchased = msg_from_model["bytesPurchased"]
                        elif (
                            "event" in msg_from_model
                            and msg_from_model["event"] == "InvoiceAccepted"
                        ):
                            self.current_total += float(msg_from_model["amount"])
                        elif "exception" in msg_from_model:
                            print("unhandled exception reported by model:\n")
                            print(msg_from_model["exception"])
                        elif "daemon" in msg_from_model:
                            daemon_exited = True
                    #                        else:
                    #                            print(f"\033[1mevent message seen but not handled: {msg_from_model}\033[0m", file=sys.stderr)
                    await asyncio.sleep(0.01)
                await self.themodeltask

            locale.setlocale(locale.LC_NUMERIC, "")
            print(
                "Bytes purchased were: "
                + locale.format_string("%d", bytesPurchased, grouping=True)
            )
            if bytesPurchased > 0:
                rate = float(self.current_total / bytesPurchased) * 1000 * _kMEBIBYTE
                print("cost/gigabyte: " + ("%6f" % rate))
            print()
            print(
                utils.TEXT_COLOR_GREEN
                + "Costs incurred were: "
                + str(self.current_total)
                + utils.TEXT_COLOR_DEFAULT
            )
            print(
                utils.TEXT_COLOR_WHITE
                + "\nOn behalf of the Golem Community, thank you for your participation."
                + utils.TEXT_COLOR_DEFAULT
            )
            self.stderr2file.close()

    #   ---------Controller------------
    def _hook_model(self, msg_from_model):
        """handles messages from the model"""
        # process model signal
        # post: current_total, count_workers, payment_failed_count, bytesInPipe, ui updated
        # output: error is true if an exception occurs
        ERROR = False
        # log most msg's to mainlog (main.log)
        if "cmd" in msg_from_model and msg_from_model["cmd"] == "add_bytes":
            # msg = msg_from_model['hexstring']
            msg = msg_from_model["hex"].hex()
            self.u_update_main_window.send(
                msg
            )  # TODO coroutine only updates one line at a time, buffering between calls
            concat_msg = {msg_from_model["cmd"]: len(msg_from_model["hex"])}
            print(concat_msg, file=self.mainlog)
        elif "exception" in msg_from_model:
            raise Exception(msg_from_model["exception"])
        elif "info" in msg_from_model and msg_from_model["info"] == "worker started":
            self.count_workers += 1
        elif "info" in msg_from_model and msg_from_model["info"] == "payment failed":
            self.payment_failed_count += 1
            if (
                self.BUDGET - self.current_total < 0.02
                or self.payment_failed_count == 10
            ):  # review epsilon
                msg_to_model = {"cmd": "pause execution"}
                self.to_model_q.put_nowait(msg_to_model)
                self.whether_paused = True
        elif (
            "event" in msg_from_model
            and msg_from_model["event"] == "AgreementTerminated"
        ):
            self.count_workers -= 1
        elif "event" in msg_from_model and msg_from_model["event"] == "InvoiceAccepted":
            self.current_total += float(msg_from_model["amount"])
        elif "event" in msg_from_model:
            print(msg_from_model, file=self.mainlog)  # report event to developer stream
        elif "debug" in msg_from_model:
            print(msg_from_model, file=self.devdebuglog)  # record debug message
        elif "bytesInPipe" in msg_from_model:
            self.bytesInPipe = msg_from_model["bytesInPipe"]
        elif "model exception" in msg_from_model:
            self.theview.destroy()  # to do, use the idiomatic del?
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            # Copy yagna log
            home = os.path.expanduser("~")
            src = os.path.join(home, ".local/share/yagna/yagna_rCURRENT.log")
            dst = f"/tmp/yagna_rCURRENT_{timestamp}.log"
            try:
                shutil.copy2(src, dst)
            except Exception as e:
                print(f"Failed to copy yagna log: {e}")
            
            print(
                utils.TEXT_COLOR_BLUE
                + "The model threw the following exception:"
                + utils.TEXT_COLOR_DEFAULT
                + "\n"
                + f"[{timestamp}] "
                + msg_from_model["model exception"]["name"]
                + "\n"
                + msg_from_model["model exception"]["what"]
            )
            ERROR = True
        return ERROR

    #   ---------Controller------------
    def _hook_view(self, ucmd):
        """handles messages from the view"""
        # process client input
        # post: ENTROPY_BUFFER_CAPACITY, MAXWORKERS, payment_failed_count, BUDGET
        # output: error true is view asks controller to stop
        ERROR = False
        if ucmd == "stop":
            ERROR = True
        elif "set buflim=" in ucmd:
            tokens = ucmd.split("=")
            self.ENTROPY_BUFFER_CAPACITY = int(eval(tokens[-1]))
            if self.ENTROPY_BUFFER_CAPACITY < 2*2**20:
                self.ENTROPY_BUFFER_CAPACITY = (
                    2*2**20
                )  # the pool writer minimum buffer size is set to 2 MiB
                # ideally this requirement would be done on the model end and an update occur over the wire
                # TODO
            msg_to_model = {"cmd": "set buflim", "limit": self.ENTROPY_BUFFER_CAPACITY}
            self.to_model_q.put_nowait(msg_to_model)
        elif "set maxworkers=" in ucmd:
            tokens = ucmd.split("=")
            self.MAXWORKERS = int(tokens[-1])
            msg_to_model = {"cmd": "set maxworkers", "count": self.MAXWORKERS}
            self.to_model_q.put_nowait(msg_to_model)
        elif ucmd == "restart" or ucmd == "start":
            self.payment_failed_count = 0  # reset counter
            msg_to_model = {"cmd": "unpause execution"}
            self.to_model_q.put_nowait(msg_to_model)
            self.whether_paused = False
        elif "set budget=" in ucmd:
            tokens = ucmd.split("=")
            self.BUDGET = float(tokens[-1])
            msg_to_model = {"cmd": "set budget", "budget": self.BUDGET}
            self.to_model_q.put_nowait(msg_to_model)
        elif ucmd == "pause":
            msg_to_model = {"cmd": "pause execution"}
            self.to_model_q.put_nowait(msg_to_model)
            self.whether_paused = True
        return ERROR


def main(args):
    """sets up asynchronous loop and launches a Controller object into it"""
    loop = asyncio.get_event_loop()
    controller = Controller(loop, args)
    task = loop.create_task(controller())
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        loop.run_until_complete(task)
        print(task.exception(), file=sys.stderr)
    finally:
        print("\nCREDITS")
        print(
            "entropythief was inspired by gandom https://github.com/reza-hackathons/gandom"
        )
        print(
            "the splash screen ascii art was obtained from https://asciiart.website/index.php?art=logos%20and%20insignias/smiley"
        )
