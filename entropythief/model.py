#!/usr/bin/python3
# entropythief
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)
##external modules

import decimal

MAX_PRICE_CPU_HR = decimal.Decimal("0.2")
MAX_PRICE_DUR_HR = decimal.Decimal("0.2")
MAX_FIXED_PRICE = decimal.Decimal("0.0")

# standard
import aiohttp  # to catch connection exception
import base64
import sys
import os
import termios
import fcntl
import asyncio
from io import StringIO
from datetime import timedelta, datetime, timezone
from pathlib import Path
from typing import AsyncIterable, Iterator
from decimal import Decimal
from dataclasses import dataclass, field
import json
import concurrent.futures
from tempfile import gettempdir
from uuid import uuid4
import yapapi.rest

try:
    moduleFilterProviderMS = False
    from gc__filterms import FilterProviderMS
except ModuleNotFoundError:
    pass
else:
    moduleFilterProviderMS = True

## 3rd party
import yapapi
from yapapi import log
from yapapi.payload import vm

# Market Strategy imports, REVIEW
from types import MappingProxyType
from typing import Dict, Mapping, Optional
from yapapi.props import com, Activity
from yapapi.props.builder import DemandBuilder
from yapapi import rest
from yapapi.strategy import *

# internal
from . import utils
from .worker import worker_public

# from TaskResultWriter import Interleaver

ENTRYPOINT_FILEPATH = Path("/golem/run/worker")
kTASK_TIMEOUT = timedelta(
    minutes=5  # should be >= script timeout, which is actually used
)
DEVELOPER_LOG_EVENTS = True


_DEBUGLEVEL = (
    int(os.environ["PYTHONDEBUGLEVEL"]) if "PYTHONDEBUGLEVEL" in os.environ else 0
)

def _log_msg(msg, debug_level=0, color=utils.TEXT_COLOR_MAGENTA):
    pass
    if debug_level <= _DEBUGLEVEL:
        print(f"\n[model.py] {color}{msg}{utils.TEXT_COLOR_DEFAULT}\n", file=sys.stderr)
        # print(f"\n[model.py] {utils.TEXT_COLOR_MAGENTA}{msg}{utils.TEXT_COLOR_DEFAULT}\n", file=sys.stderr)


# ==============================================================================
# OPTIMIZED ASYNC TASK EXECUTION (from model_optimized.py)
# ==============================================================================

async def execute_tasks_with_yielding(golem, steps, tasks, **kwargs):
    """
    Wrapper around golem.execute_tasks that yields control more frequently
    to prevent event loop starvation during intensive Golem operations
    """
    
    # Get the original async generator
    completed_tasks = golem.execute_tasks(steps, tasks, **kwargs)
    
    task_count = 0
    
    # Process tasks with frequent yielding
    async for task in completed_tasks:
        # Yield every task to prevent blocking
        await asyncio.sleep(0)
        
        yield task
        task_count += 1
        
        # Extra yield every 5 tasks for heavily loaded systems
        if task_count % 5 == 0:
            await asyncio.sleep(0.001)  # Small delay to ensure other coroutines run


class model__EntropyThief:
    """
    __init__
    hasBytesInPipeChanges
    _hook_controller
    _provision
    __call__

    """

    # ---------model_EntropyThief----------
    def __init__(
        self,
        loop,
        args,
        from_ctl_q,
        to_ctl_q,
        ENTROPY_BUFFER_CAPACITY,
        MAXWORKERS,
        BUDGET,
        IMAGE_HASH,
        taskResultWriter,
        TASK_TIMEOUT=kTASK_TIMEOUT,
    ):
        self._loop = loop
        self.args = args
        self.from_ctl_q = from_ctl_q
        self.to_ctl_q = to_ctl_q
        self.MAXWORKERS = MAXWORKERS
        self.BUDGET = BUDGET
        self.IMAGE_HASH = IMAGE_HASH
        self.taskResultWriter = taskResultWriter
        self.TASK_TIMEOUT = TASK_TIMEOUT
        self._costRunning = 0.0
        self.ENTROPY_BUFFER_CAPACITY = ENTROPY_BUFFER_CAPACITY

        # output yapapi logger INFO events to stderr and INFO+DEBUG to args.log_fle
        if not self.args.disable_logging:
            yapapi.log.enable_default_logger(
                log_file=args.log_file,
                debug_activity_api=True,
                debug_market_api=True,
                debug_payment_api=True,
            )

    # -----------model__EntropyThief------------------------ #
    def hasBytesInPipeChanged(self):
        """queries whether data has been read from the pipe since last call"""
        # ------------------------------------------------------ #
        # bytesInPipe_last = self.bytesInPipe
        # self.bytesInPipe = len(self.taskResultWriter)
        # return bytesInPipe_last - self.bytesInPipe
        # This method is now obsolete since we no longer track previous value.
        pass

    # -----------model__EntropyThief------------------------ #
    def _hook_controller(self, qmsg):
        """processes the signal from the controller to update internal state"""
        # ------------------------------------------------------ #
        if "cmd" in qmsg and qmsg["cmd"] == "stop":
            self.OP_STOP = True
        elif "cmd" in qmsg and qmsg["cmd"] == "set buflim":
            self.ENTROPY_BUFFER_CAPACITY = qmsg["limit"]
            self.taskResultWriter.update_capacity(self.ENTROPY_BUFFER_CAPACITY)
        elif "cmd" in qmsg and qmsg["cmd"] == "set maxworkers":
            self.MAXWORKERS = qmsg["count"]
        elif "cmd" in qmsg and qmsg["cmd"] == "pause execution":
            self.OP_PAUSE = True
        elif "cmd" in qmsg and qmsg["cmd"] == "set budget":
            self.BUDGET = qmsg["budget"]
        elif "cmd" in qmsg and qmsg["cmd"] == "unpause execution":
            self.OP_PAUSE = False

    # ----------------- model__EntropyThief --------------- #
    async def _provision(self):
        """divides work to be executed in steps on the golem network
        required by __call__
        """

        # ----------------------------------------------------- #

        ## HELPERS
        # ...........................................#
        # partition                                 #
        #  divide a total into a list of partition  #
        #   counts                                  #
        # ...........................................#
        def helper__partition(total, maxcount=6):
            if total == 1:
                return [total]

            if total <= maxcount:
                count = total
            else:
                count = maxcount

            minimum = int(total / count)
            while minimum == 1:
                count -= 1
                minimum = int(total / count)

            extra = total % count

            rv = []
            for _ in range(count - 1):
                rv.append(minimum)
            rv.append(minimum + extra)
            return rv

        ## BEGIN ROUTINE _provision
        count_bytes_requested = self.ENTROPY_BUFFER_CAPACITY - len(self.taskResultWriter)
        
        # DEBUG: Log provisioning decision details
        current_buffered = len(self.taskResultWriter)
        
        # DEBUG: Break down what's in the buffer
        pipe_writer = self.taskResultWriter._writerPipe
        pipe_bytes = pipe_writer.len_accessible() if hasattr(pipe_writer, 'len_accessible') else 'N/A'
        internal_bytes = pipe_writer._count_bytes_in_internal_buffers() if hasattr(pipe_writer, '_count_bytes_in_internal_buffers') else 'N/A'
        total_pipe_writer = pipe_writer.len_total_buffered() if hasattr(pipe_writer, 'len_total_buffered') else 'N/A'
        
        _log_msg(f"_provision() - ENTROPY_BUFFER_CAPACITY: {self.ENTROPY_BUFFER_CAPACITY:,}", 3)
        _log_msg(f"_provision() - len(taskResultWriter): {current_buffered:,}", 3)
        _log_msg(f"_provision() - PipeWriter breakdown:", 3)
        _log_msg(f"    pipe_bytes (accessible): {pipe_bytes}", 3)
        _log_msg(f"    internal_buffer_bytes: {internal_bytes}", 3)
        _log_msg(f"    total_pipe_writer_bytes: {total_pipe_writer}", 3)
        _log_msg(f"_provision() - count_bytes_requested: {count_bytes_requested:,}", 3)
        _log_msg(f"_provision() - pending: {self.taskResultWriter.pending}", 3)
        _log_msg(f"_provision() - cost_running: {self._costRunning:.4f}", 3)
        _log_msg(f"_provision() - budget_remaining: {(self.BUDGET - 0.02):,.4f}", 3)

        # 2.4.1)  test if bytes available from task result writer are beneath threshold
        #     2   test if within budget
        condition_1 = count_bytes_requested > 0
        condition_2 = not self.taskResultWriter.pending
        condition_3 = len(self.taskResultWriter) < int(self.ENTROPY_BUFFER_CAPACITY / 2)
        condition_4 = self._costRunning < (self.BUDGET - 0.02)
        
        _log_msg(f"Provisioning conditions:", 3)
        _log_msg(f"  bytes_requested > 0: {condition_1} ({count_bytes_requested:,} > 0)", 3)
        _log_msg(f"  not pending: {condition_2}", 3)
        _log_msg(f"  buffer < 50% capacity: {condition_3} ({current_buffered:,} < {int(self.ENTROPY_BUFFER_CAPACITY / 2):,})", 3)
        _log_msg(f"  within budget: {condition_4} ({self._costRunning:.4f} < {(self.BUDGET - 0.02):.4f})", 3)
        _log_msg(f"  ALL CONDITIONS MET: {condition_1 and condition_2 and condition_3 and condition_4}", 3)
        
        if (
            condition_1 and condition_2 and condition_3 and condition_4
        ):
            package = await vm.repo(
                image_hash=self.IMAGE_HASH, min_mem_gib=0.3, min_storage_gib=0.3
            )

            if moduleFilterProviderMS:
                strategy = FilterProviderMS(self.strat)
            else:
                strategy = self.strat

            ############################################################################\
            # initialize and spread work across task objects                            #
            async with yapapi.Golem(
                budget=self.BUDGET - self._costRunning,
                subnet_tag=self.args.subnet_tag,
                payment_network=self.args.payment_network,
                payment_driver=self.args.payment_driver,
                event_consumer=MySummaryLogger(self).log,
                strategy=strategy,
            ) as golem:
                # partition the work into evenly spaced lengths except for last
                bytes_partitioned = helper__partition(
                    count_bytes_requested, self.MAXWORKERS
                )

                _log_msg(
                    f"::[provision()] {count_bytes_requested} bytes, partition counts: {bytes_partitioned}",
                    1,
                )

                # 2.4.3)  initialize work needed per node across a list of Task objects
                completed_tasks = golem.execute_tasks(
                    steps,
                    [
                        yapapi.Task(
                            data={
                                "req_byte_count": bytes_needed_on_worker,
                                "writer": self.taskResultWriter,
                                "rdrand_arg": self.rdrand_arg,
                            }
                        )
                        for bytes_needed_on_worker in bytes_partitioned
                    ],
                    payload=package,
                    max_workers=self.MAXWORKERS,
                    timeout=self.TASK_TIMEOUT,
                )
                #                                                                           /

                # 2.4.4)  run tasks asynchronously collecting results and returning control after
                #            each result collected
                async for task in completed_tasks:
                    if task.result:
                        _log_msg(
                            f"::[provision()] saw a task result, its contents are {task.result}",
                            1,
                        )
                        self.taskResultWriter.add_result_file(task.result)
                        _log_msg(
                            f"::[provision()] number of task results added to writer: {self.taskResultWriter.count_uncommitted()}",
                            1,
                        )
                        # await self.taskResultWriter.refresh() # review

                    else:
                        _log_msg(f"::[provision()] saw rejected result", 1)
                        pass  # no result implies rejection which steps reprovisions
                #                                                                   /

                _log_msg(f"::[provision()] committing added files now", 1)
                self.taskResultWriter.commit_added_result_files()

                ####################################################################\
        else:
            _log_msg(f"DEBUG: Provisioning SKIPPED - conditions not met", 3)

    # ---------model_EntropyThief----------
    async def __call__(self):
        """asynchronously launches a writer then asyncrhonously provisions tasks to submit to it"""
        # asynchronously launch taskResultWriter's refresh method instead of calling directly
        thetask = asyncio.create_task(self.taskResultWriter.refresh())

        self.rdrand_arg = "rdrand"

        self.OP_STOP = False
        self.OP_PAUSE = True  # wait for controller to send start signal as restart
        self.strat = None

        if self.args.payment_network in ["rinkeby", "goerli", "holesky"]:
            max_price_for_cpu = Decimal("inf")
            max_price_for_dur = Decimal("inf")
            max_fixed_price = Decimal("inf")
        else:
            max_price_for_cpu = Decimal(MAX_PRICE_CPU_HR)
            max_price_for_dur = Decimal(MAX_PRICE_DUR_HR)
            max_fixed_price = Decimal(MAX_FIXED_PRICE)
        try:
            self.strat = MyLeastExpensiveLinearPayuMS(
                LeastExpensiveLinearPayuMS(  # these MS parameters are not clearly documented ?
                    max_fixed_price=Decimal(
                        max_fixed_price
                    ),  # testing, ideally this works with the epsilon in model...
                    max_price_for={
                        yapapi.props.com.Counter.CPU: max_price_for_cpu
                        / Decimal("3600.0"),
                        yapapi.props.com.Counter.TIME: max_price_for_dur
                        / Decimal("3600.0"),
                    },
                ),
                use_rdrand=True
            )
        except Exception as e:
            print(f"Exception thrown in call to model: {e}\n", file=sys.stderr)
            sys.exit(1)
        try:
            # see if there are any bytes already in the pipe # may not be necessary
            # self.bytesInPipe = len(self.taskResultWriter)

            while not self.OP_STOP:
                # 2.1) flush any pending processes/buffers in the task result writer
                # await self.taskResultWriter.refresh()

                # 2.2) query task result writer for the number of bytes stored and relay to controller
                msg = {"bytesInPipe": len(self.taskResultWriter)}
                self.to_ctl_q.put_nowait(msg)

                # 2.3) receive and handle a message from the controller if any
                if not self.from_ctl_q.empty():
                    self._hook_controller(self.from_ctl_q.get_nowait())
                # [[state change]]

                # 2.4) provision work if possible               #
                if (
                    not self.OP_STOP and not self.OP_PAUSE
                ):  # OP_STOP might have been set by the controller hook
                    await self._provision()  # only if needed, tested inside

                await asyncio.sleep(0.01)
            thetask.cancel()
        except KeyboardInterrupt:
            pass  # if the task has not exited in response to this already, finally will propagate a cancel
        except yapapi.NoPaymentAccountError as e:
            handbook_url = (
                "https://handbook.golem.network/requestor-tutorials/"
                "flash-tutorial-of-requestor-development"
            )
            emsg = (
                f"{utils.TEXT_COLOR_RED}"
                f"No payment account initialized for driver `{e.required_driver}` "
                f"and network `{e.required_network}`.\n\n"
                f"See {handbook_url} on how to initialize payment accounts for a requestor node."
                f"{utils.TEXT_COLOR_DEFAULT}"
            )
            emsg += (
                f"\nMaybe you forgot to invoke {utils.TEXT_COLOR_YELLOW}yagna payment"
                f" init --sender{utils.TEXT_COLOR_DEFAULT}"
                "\nalternatively, ensure YAGNA_APPKEY environment variable corresponds to the current"
                " payment account."
            )
            msg = {"exception": emsg}
            self.to_ctl_q.put_nowait(msg)
        except aiohttp.client_exceptions.ClientConnectorError as e:
            _msg = str(e)
            _msg += (
                "\ndid you forget to invoke "
                + utils.TEXT_COLOR_YELLOW
                + "yagna service run"
                + utils.TEXT_COLOR_DEFAULT
                + "?"
            )
            msg = {"exception": "..." + _msg}
            self.to_ctl_q.put_nowait(msg)
        except Exception as e:
            # this should not happen
            msg = {"model exception": {"name": e.__class__.__name__, "what": str(e)}}
            self.to_ctl_q.put_nowait(msg)
        finally:
            msg = {"bytesPurchased": self.taskResultWriter._bytesSeen}
            self.to_ctl_q.put_nowait(msg)
            # send a message back to the controller that the (daemonized) process has cleanly exited
            # consider a more clean exit by checking if task is running first
            try:
                pass
                # task.cancel() # make sure cancel message has been propagated to EntropyThief (and Golem)
                # loop.run_until_complete(task)
            except:
                pass
            msg = {"daemon": "finished"}
            self.to_ctl_q.put_nowait(msg)


##############################################################################
# TODO rename to worker or work or provider_work etc
async def steps(_ctx: yapapi.WorkContext, tasks: AsyncIterable[yapapi.Task]):
    """perform steps to produce task result on a provider
    called from model__entropythief
    """
    SCRIPT_TIMEOUT = (  # has to be at least kTASK_TIMEOUT, assigned to task itself
        # previously on the executor
        kTASK_TIMEOUT
    )

    ##############################################################################
    Path_output_file = None
    loop = asyncio.get_running_loop()
    # allow for time for naive providers to download the image
    script = _ctx.new_script(timeout=SCRIPT_TIMEOUT)

    async for task in tasks:
        ################################################
        # execute the worker in the vm                 #
        ################################################
        script.run(
            ENTRYPOINT_FILEPATH.as_posix(),
            str(task.data["req_byte_count"]),
            task.data["rdrand_arg"],
        )

        ################################################
        # download the results on successful execution #
        ################################################
        Path_output_file = Path(gettempdir()) / str(uuid4())
        script.download_file(worker_public.RESULT_PATH, str(Path_output_file))

        # note: reject_result on exceptions behavior may have changed with recent yapapi updates
        # TODO: test
        try:
            yield script
        except rest.activity.BatchTimeoutError:  # credit to Golem's blender.py
            print(
                f"{utils.TEXT_COLOR_RED}"
                f"Task {task} timed out on {_ctx.provider_name}, time: {task.running_time}"
                f"{utils.TEXT_COLOR_DEFAULT}",
                file=sys.stderr,
            )
            task.reject_result("timeout", retry=True)  # retry false is scary
        except Exception as e:  # define exception TODO
            print(
                f"{utils.TEXT_COLOR_RED}"
                f"A task threw an exception."
                f"{utils.TEXT_COLOR_DEFAULT}",
                file=sys.stderr,
            )
            print(e, file=sys.stderr)
            # raise # exception will be caught by yapapi to place the task back in the queue???
            # maybe don't raise because we need to cleanup reject instead
            task.reject_result("unspecified error", retry=True)  # retry false is scary
        else:
            ###################################################
            # accept the downloaded file as the task result   #
            ###################################################
            task.accept_result(result=str(Path_output_file))
            script = _ctx.new_script(timeout=SCRIPT_TIMEOUT)
        finally:
            if not task.result:
                if Path_output_file and Path_output_file.exists():
                    Path_output_file.unlink()


##########################{}##################################################
class MySummaryLogger(yapapi.log.SummaryLogger):
    """communicate event driven data to controller"""

    # Required by: model__entropythief
    # the log method is provided as the event-consumer for yapapi.Golem to intercept events
    to_ctl_q = None  # the msg queue back to the controller
    model = None

    # can be removed
    @property
    def costRunning(self):
        return self.model._costRunning

    @costRunning.setter
    def costRunning(self, amount):
        _log_msg(f"[MySummaryLogger{{}}] Setting costRunning to {amount}", 3)
        self.model._costRunning = amount

    def __init__(self, model):
        self.model = model
        # self.costRunning = 0.0
        self.to_ctl_q = model.to_ctl_q
        super().__init__()
        # self.event_log_file = open("events.log", "w")

    def log(self, event: yapapi.events.Event) -> None:
        # during an execution we are interested in updating the state
        # while executions are pending, we hook to inspect the buffer
        # state and update the controller here while events are emitted
        # there is probably a more Pythonic + yapapi way to handle this TODO

        # _log_msg(f"[MySummaryLogger{{}}] REFRESHing taskResultWriter on log event", 10)
        delta = self.model.hasBytesInPipeChanged()
        if delta != 0:
            msg = {"bytesInPipe": len(self.model.taskResultWriter)}
            self.model.to_ctl_q.put_nowait(msg)

        to_controller_msg = None
        if isinstance(event, yapapi.events.InvoiceAccepted):
            added_cost = float(event.amount)
            self.costRunning = self.costRunning + added_cost
            to_controller_msg = {
                "event": event.__class__.__name__,  # InvoiceAccepted
                "agr_id": event.agr_id,
                "inv_id": event.job_id,
                "amount": event.amount,
            }

            # to_controller_msg = {
            #    'cmd': 'add cost', 'amount': added_cost}

        elif isinstance(event, yapapi.events.PaymentFailed):
            to_controller_msg = {"info": "payment failed"}
        elif isinstance(event, yapapi.events.WorkerStarted):
            to_controller_msg = {"info": "worker started"}
        elif isinstance(event, yapapi.events.WorkerFinished):
            to_controller_msg = {"info": "worker finished"}
        elif isinstance(event, yapapi.events.AgreementTerminated):
            to_controller_msg = {"event": "AgreementTerminated"}
        elif isinstance(event, yapapi.events.AgreementCreated):
            to_controller_msg = {
                "event": "AgreementCreated",
                "agr_id": event.agr_id,
                "provider_id": event.provider_id,
                "provider_info": event.provider_info.name,
            }
        elif hasattr(event, "agr_id"):
            to_controller_msg = {
                "event": event.__class__.__name__,
                "agr_id": event.agr_id,
                "struct": str(event),
            }

        """
        if hasattr(event, 'agr_id'):
            agreement = { 'agr_id': event.agr_id
                         , 
            to_controller_msg = {
                'agreement_event': {}   
            }
        """
        # /if

        if to_controller_msg:
            self.to_ctl_q.put_nowait(to_controller_msg)

        super().log(event)

    def __del__(self):
        pass
        # self.event_log_file.close()


############################ {} ######################################################
class MyLeastExpensiveLinearPayuMS(WrappingMarketStrategy):
    def __init__(self, base_strategy: BaseMarketStrategy, use_rdrand):
        self.use_rdrand = use_rdrand
        super().__init__(base_strategy)

    async def score_offer(self, offer: rest.market.OfferProposal) -> float:
        score = SCORE_REJECTED

        """
        # deprecated
        if self.use_rdrand:
            if offer.props["golem.inf.cpu.architecture"] == "x86_64":
                if 'rdrand' in offer.props["golem.inf.cpu.capabilities"]:
                    score = await super().score_offer(offer, history)
        else:
            score = await super().score_offer(offer, history)
        return score
        """

        if self.use_rdrand:
            # review
            # it is not clear at this time how to create a demand that constrains according to cpu
            # features, therefore, we inspect the offer itself and score only if the offer
            # meets this constraint.

            if (
                "golem.inf.cpu.capabilities" in offer.props
                and "rdrand" in offer.props["golem.inf.cpu.capabilities"]
            ):
                try:
                    score = await self.base_strategy.score_offer(offer)
                except Exception as e:
                    print(
                        f"unhandled exception in MyLeastExpensiveLinearPayuMS: {e}",
                        file=sys.stderr,
                    )
        else:
            # we are not using rdrand (using system entropy) so proceed as normal without filtering
            score = await self.base_strategy.score_offer(offer)
        return score
