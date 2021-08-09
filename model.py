#!/usr/bin/python3
#entropythief
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)
##external modules

# standard
import  aiohttp # to catch connection exception
import  base64
import  sys
import  os
import  termios
import  fcntl
import  asyncio
from    io          import StringIO
from    datetime    import timedelta, datetime, timezone
from    pathlib     import Path
from    typing      import AsyncIterable, Iterator
from    decimal     import  Decimal
from    dataclasses import dataclass, field
import  json
import  concurrent.futures
from    tempfile    import gettempdir
from uuid import uuid4
import  yapapi.rest

## 3rd party
import  yapapi
from    yapapi          import log
from    yapapi.payload  import vm
# Market Strategy imports, REVIEW
from types import MappingProxyType
from typing import Dict, Mapping, Optional
from yapapi.props import com, Activity
from yapapi import rest
from yapapi.strategy import *

# internal
import  utils
import  worker_public
from TaskResultWriter import Interleaver

ENTRYPOINT_FILEPATH = Path("/golem/run/worker")
kTASK_TIMEOUT = timedelta(minutes=10)
DEVELOPER_LOG_EVENTS = True









  #---------------------------------------------#
 #             steps                           #
#---------------------------------------------#
# required by:  entropythief
async def steps(ctx: yapapi.WorkContext, tasks: AsyncIterable[yapapi.Task]):
    loop = asyncio.get_running_loop()
    async for task in tasks:
        await task.data['writer'].refresh()
        # start_time = datetime.now()
        # expiration = datetime.now(timezone.utc) + timedelta(seconds=30)
        # request <count> bytes from provider and wait
        ctx.run(ENTRYPOINT_FILEPATH.as_posix(), str(task.data['req_byte_count']), task.data['rdrand_arg'])
        """
        future_results = yield ctx.commit()
        results = await future_results

        # download bytes only if there is no stderr message from provider
        stderr=results[-1].stderr
        if stderr:
            print("A WORKER REPORTED AN ERROR:\n", stderr, file=sys.stderr)
            task.reject_result(stderr)
        elif results[-1].success == False:
            task.reject_result()
        else:
        """
        output_file = Path(gettempdir()) / str(uuid4())
        try:
            ctx.download_file(worker_public.RESULT_PATH, str(output_file))
            yield ctx.commit(timeout=timedelta(minutes=2))
            # print(f"CALLING ACCEPT RESULT {output_file}", file=sys.stderr)
        except rest.activity.BatchTimeoutError: # credit to Golem's blender.py
            print(
                    f"{utils.TEXT_COLOR_RED}"
                    f"Task {task} timed out on {ctx.provider_name}, time: {task.running_time}"
                    f"{utils.TEXT_COLOR_DEFAULT}"
                    , file=sys.stderr
                    )
            task.reject_result("timeout", retry=True) # need to ensure a retry occurs! TODO
        except Exception as e: # define exception TODO
            print(
                    f"{utils.TEXT_COLOR_RED}"
                    f"A task threw an exception."
                    f"{utils.TEXT_COLOR_DEFAULT}"
                    , file=sys.stderr
            )
            print(e, file=sys.stderr)
            task.reject_result("unspecified error", retry=True) # timeout maybe?
        else:
            task.accept_result(result=str(output_file))







  #---------------------------------------------#
 #             MySummaryLogger{}               #
#---------------------------------------------#
# Required by: model__entropythief
# the log method is provided as the event-consumer for yapapi.Golem to intercept events
"""
    to_ctl_q:   the msg queue back to the controller
"""
class MySummaryLogger(yapapi.log.SummaryLogger):
    costRunning = 0.0 # keeps track of cost so far to enforce a budget check
    event_log_file=open('/dev/null')
    to_ctl_q = None

    def __init__(self, to_ctl_q):
        # self.costRunning = 0.0
        self.to_ctl_q = to_ctl_q
        super().__init__()
        self.event_log_file = open("events.log", "w")

    def log(self, event: yapapi.events.Event) -> None:
        to_controller_msg = None
        if isinstance(event, yapapi.events.PaymentAccepted):
            added_cost=float(event.amount)
            self.costRunning += added_cost
            to_controller_msg = {
                'event': event.__class__.__name__ # PaymentAccepted
                , 'agr_id': event.agr_id
                , 'inv_id': event.inv_id
                , 'amount': event.amount
            }
            #to_controller_msg = {
            #    'cmd': 'add cost', 'amount': added_cost}

        elif isinstance(event, yapapi.events.PaymentFailed):
            to_controller_msg = {
                'info': 'payment failed'
            }
        elif isinstance(event, yapapi.events.WorkerStarted):
            to_controller_msg = {
                'info': 'worker started'
            }
        elif isinstance(event, yapapi.events.WorkerFinished):
            to_controller_msg = {
                'info': 'worker finished'
            }
        elif isinstance(event, yapapi.events.AgreementTerminated):
            to_controller_msg = {
                'event': 'AgreementTerminated'
            }
        elif isinstance(event, yapapi.events.AgreementCreated):
            to_controller_msg = {
                'event': 'AgreementCreated'
                ,'agr_id': event.agr_id
                ,'provider_id': event.provider_id
                ,'provider_info': event.provider_info.name
            }
        elif hasattr(event, 'agr_id'):
            to_controller_msg = {
                'event': event.__class__.__name__
                , 'agr_id': event.agr_id
                , 'struct': str(event)
            }
        
        # uncomment to log all the Event types as they occur to the specified file
        if DEVELOPER_LOG_EVENTS:
            print(event, file=self.event_log_file)


        """
        if hasattr(event, 'agr_id'):
            agreement = { 'agr_id': event.agr_id
                         , 
            to_controller_msg = {
                'agreement_event': {}   
            }
        """
        #/if

        if to_controller_msg:
            self.to_ctl_q.put_nowait(to_controller_msg)

        super().log(event)


    def __del__(self):
        self.event_log_file.close()







@dataclass
############################ {} #########################
class MyLeastExpensiveLinearPayMS(yapapi.strategy.LeastExpensiveLinearPayuMS, object):
#########################################################
    """
        expected_time_secs: ? TODO, copied from api, required for super
        max_fixed_price: ? TODO, copied from api, required for super
        max_price_for: ? TODO, copied from api, required for super
        use_rdrand: indicates whether the market strategy shall filter offers with the rdrand cpu capability
    """
    golem = None
    def __init__(
        self
        , expected_time_secs: int = 60
        , max_fixed_price: Decimal = Decimal("inf")
        , max_price_for: Mapping[com.Counter, Decimal] = MappingProxyType({})
        , use_rdrand=False
        ):
            super().__init__(expected_time_secs, max_fixed_price, max_price_for)
            self.use_rdrand=use_rdrand

    async def decorate_demand(self, demand: DemandBuilder) -> None:
        if self.use_rdrand:
            demand.ensure("(golem.inf.cpu.architecture=x86_64)")
        await super().decorate_demand(demand)
    
    async def score_offer(
        self, offer: rest.market.OfferProposal, history: Optional[ComputationHistory] = None
    ) -> float:
        score = SCORE_REJECTED

        """
        # retained as an example of how to blacklist a specific provider by name
        if offer.props["golem.node.id.name"] == "friendly-winter":
            score = await super().score_offer(offer, history)
        # return score
        """
        # print(offer.props, file=sys.stderr) # it may be useful to log and review offers
        
        """
        if self.use_rdrand:
            if offer.props["golem.inf.cpu.architecture"] == "x86_64":
                if 'rdrand' in offer.props["golem.inf.cpu.capabilities"]:
                    score = await super().score_offer(offer, history)
        else:
            score = await super().score_offer(offer, history)
        return score
        """

        if self.use_rdrand:
            # it is not clear at this time how to create a demand that constrains according to cpu
            # features, therefore, we inspect the offer itself and score only if the offer
            # meets this constraint.
            if 'rdrand' in offer.props["golem.inf.cpu.capabilities"]:
                score = await super().score_offer(offer, history)
        else:
            # we are not using rdrand (using system entropy) so proceed as normal without filtering
            score = await super().score_offer(offer, history)
        return score

"""
    model__EntropyThief
    -------------------
    MINPOOLSIZE             " the target maximum number of random bytes available for reading (misnomer!) {dynamic}
    MAXWORKERS              " the number of workers to provision per network request (misnomer?) {dynamic}
    BUDGET                  " the most the clinet is willing to spend before pausing execution {dynamic}
    IMAGE_HASH              " the hash link for providers to look up the image
    TASK_TIMEOUT            " how long to give a provider to finish the task

    from_ctl_q              " signals from controller
    to_ctl_q                " signals to controller
    taskResultWriter        " the object from TaskResultWriter.py that processes each finished collection of results
    loop                    " the running loop (same as get_running_loop)
    args                    " from the argparse module

    _hook_controller(...)   " callback for controller signals
    _provision()            " start a vm on Golem to collect the results

    internal dependencies: [ 'worker_public.py', 'TaskResultWriter.py', 'utils' ]


    summary:
        TODO
"""


class model__EntropyThief:
    taskResultWriter = None



 # __          __   __          
# |  \        |  \ |  \         
 # \▓▓_______  \▓▓_| ▓▓_        
# |  \       \|  \   ▓▓ \       
# | ▓▓ ▓▓▓▓▓▓▓\ ▓▓\▓▓▓▓▓▓       
# | ▓▓ ▓▓  | ▓▓ ▓▓ | ▓▓ __      
# | ▓▓ ▓▓  | ▓▓ ▓▓ | ▓▓|  \     
# | ▓▓ ▓▓  | ▓▓ ▓▓  \▓▓  ▓▓     
 # \▓▓\▓▓   \▓▓\▓▓   \▓▓▓▓      

# model__EntropyThief

    def __init__(self
        , loop
        , args
        , from_ctl_q
        , to_ctl_q
        , MINPOOLSIZE
        , MAXWORKERS
        , BUDGET
        , IMAGE_HASH
        , TASK_TIMEOUT=kTASK_TIMEOUT
    ):
        self._loop = loop
        self.args = args
        self.from_ctl_q = from_ctl_q
        self.to_ctl_q = to_ctl_q
        self.MINPOOLSIZE = MINPOOLSIZE
        self.MAXWORKERS = MAXWORKERS
        self.BUDGET = BUDGET
        self.IMAGE_HASH = IMAGE_HASH
        self.TASK_TIMEOUT = TASK_TIMEOUT
        # uncomment to output yapapi logger INFO events to stderr and INFO+DEBUG to args.log_fle
        if self.args.enable_logging:
            yapapi.log.enable_default_logger(
                log_file=args.log_file
                , debug_activity_api=True
                , debug_market_api=True
                , debug_payment_api=True)

        self.taskResultWriter = Interleaver(self.to_ctl_q, self.MINPOOLSIZE)
        





    # -----------model__EntropyThief------------------------ #
    def hasBytesInPipeChanged(self):
    # ------------------------------------------------------ #
        bytesInPipe_last = self.bytesInPipe
        self.bytesInPipe = self.taskResultWriter.query_len()
        return bytesInPipe_last != self.bytesInPipe







    # -----------model__EntropyThief------------------------ #
    def _hook_controller(self, qmsg):
    # ------------------------------------------------------ #
        # print(f"message to model: {qmsg}", file=sys.stderr)
        if 'cmd' in qmsg and qmsg['cmd'] == 'stop':
            self.OP_STOP = True
        elif 'cmd' in qmsg and qmsg['cmd'] == 'set buflim':
            self.MINPOOLSIZE = qmsg['limit']
            self.taskResultWriter.update_capacity(self.MINPOOLSIZE)
        elif 'cmd' in qmsg and qmsg['cmd'] == 'set maxworkers':
            self.MAXWORKERS = qmsg['count']
        elif 'cmd' in qmsg and qmsg['cmd'] == 'pause execution':
            self.OP_PAUSE=True
        elif 'cmd' in qmsg and qmsg['cmd'] == 'set budget':
            self.BUDGET=qmsg['budget']
        elif 'cmd' in qmsg and qmsg['cmd'] == 'unpause execution':
            self.OP_PAUSE=False
    #/if not from_ctl_q.empty()







    # ----------------- model__EntropyThief --------------- #
    async def _provision(self):
    # ----------------------------------------------------- #
        count_bytes_requested = self.taskResultWriter.count_bytes_requesting()
        if count_bytes_requested > 0 and self.bytesInPipe < int(self.MINPOOLSIZE/2) and self.mySummaryLogger.costRunning < self.BUDGET:
            package = await vm.repo(
                    image_hash=self.IMAGE_HASH
                    , min_mem_gib=0.3
                    , min_storage_gib=0.3
                )

            async with yapapi.Golem(
                    budget=self.BUDGET-self.mySummaryLogger.costRunning
                    , subnet_tag=self.args.subnet_tag
                    , network=self.args.network
                    , driver=self.args.driver
                    , event_consumer=self.mySummaryLogger.log
                    , strategy=self.strat
            ) as golem:

                bytes_needed_per_worker = int(count_bytes_requested/self.MAXWORKERS)

                completed_tasks = golem.execute_tasks(
                        steps
                        , [yapapi.Task(data={'req_byte_count': bytes_needed_per_worker, 'writer': self.taskResultWriter, 'rdrand_arg':self.rdrand_arg}) for _ in range(self.MAXWORKERS)]
                        , payload=package
                        , max_workers=self.MAXWORKERS
                        , timeout=self.TASK_TIMEOUT
                   )

                async for task in completed_tasks:
                    if task.result:
                        self.taskResultWriter.add_file(task.result)

                        if self.hasBytesInPipeChanged():
                            msg = {'bytesInPipe': self.bytesInPipe}; self.to_ctl_q.put_nowait(msg)
                    else:
                        pass # no result implies rejection which steps reprovisions

                # control will have been returned between task results but after this point all results are collected
                self.taskResultWriter.commit_added_files()




                   # __ __ 
                  # |  \  \
  # _______  ______ | ▓▓ ▓▓
 # /       \|      \| ▓▓ ▓▓
# |  ▓▓▓▓▓▓▓ \▓▓▓▓▓▓\ ▓▓ ▓▓
# | ▓▓      /      ▓▓ ▓▓ ▓▓
# | ▓▓_____|  ▓▓▓▓▓▓▓ ▓▓ ▓▓
 # \▓▓     \\▓▓    ▓▓ ▓▓ ▓▓
  # \▓▓▓▓▓▓▓ \▓▓▓▓▓▓▓\▓▓\▓▓
                         
# model__EntropyThief

    async def __call__(self):
        if self.args.rdrand == 1:
            self.rdrand_arg = 'rdrand'
        else:
            self.rdrand_arg = 'devrand'

        self.OP_STOP = False
        self.OP_PAUSE = False
        self.strat = MyLeastExpensiveLinearPayMS( # these MS parameters are not clearly documented ?
                    max_fixed_price=Decimal("0.00") # testing, ideally this works with the epsilon in model...
                    , max_price_for={yapapi.props.com.Counter.CPU: Decimal("0.05")
                        , yapapi.props.com.Counter.TIME: Decimal("0.0011")}
                    , use_rdrand = self.args.rdrand
                ) 
        self.mySummaryLogger = MySummaryLogger(self.to_ctl_q)
        try:
            self.bytesInPipe = self.taskResultWriter.query_len() # note bytesInPipe is the lazy count

            while not self.OP_STOP:
                await self.taskResultWriter.refresh()

                if self.hasBytesInPipeChanged():
                    msg = {'bytesInPipe': self.bytesInPipe}; self.to_ctl_q.put_nowait(msg)
                
                if not self.from_ctl_q.empty():
                    self._hook_controller(self.from_ctl_q.get_nowait())
                    
                if not self.OP_STOP and not self.OP_PAUSE: # OP_STOP might have been set by the controller hook
                    await self._provision()

                await asyncio.sleep(0.01)
        except KeyboardInterrupt:
            pass # if the task has not exited in response to this already, finally will propagate a cancel
        except yapapi.NoPaymentAccountError as e:
            handbook_url = (
                "https://handbook.golem.network/requestor-tutorials/"
                "flash-tutorial-of-requestor-development"
            )
            emsg = f"{utils.TEXT_COLOR_RED}" \
                f"No payment account initialized for driver `{e.required_driver}` " \
                f"and network `{e.required_network}`.\n\n" \
                f"See {handbook_url} on how to initialize payment accounts for a requestor node." \
                f"{utils.TEXT_COLOR_DEFAULT}"
            emsg += f"\nMaybe you forgot to invoke {utils.TEXT_COLOR_YELLOW}yagna payment init --sender{utils.TEXT_COLOR_DEFAULT}"
            msg = {'exception': emsg }
            self.to_ctl_q.put_nowait(msg)
        except aiohttp.client_exceptions.ClientConnectorError as e:
            _msg = str(e)
            _msg += "\ndid you forget to invoke " + utils.TEXT_COLOR_YELLOW + "yagna service run" + utils.TEXT_COLOR_DEFAULT + "?"
            msg = {'exception': "..." +  _msg }
            self.to_ctl_q.put_nowait(msg)
        except Exception as e:
            # this should not happen
            msg = {'model exception': {'name': e.__class__.__name__, 'what': str(e) } }
            self.to_ctl_q.put_nowait(msg)
        finally:
            msg = {'bytesPurchased': self.taskResultWriter._bytesSeen}
            self.to_ctl_q.put_nowait(msg)
            # send a message back to the controller that the (daemonized) process has cleanly exited
            # consider a more clean exit by checking if task is running first
            try:
                pass
                #task.cancel() # make sure cancel message has been propagated to EntropyThief (and Golem)
                # loop.run_until_complete(task)
            except:
                pass
            msg = {'daemon': "finished"}
            self.to_ctl_q.put_nowait(msg)





