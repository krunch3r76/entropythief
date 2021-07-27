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
import  pipe_writer


ENTRYPOINT_FILEPATH = Path("/golem/run/worker.py")
kTASK_TIMEOUT = timedelta(minutes=10)
# EXPECTED_ENTROPY = 1044480 # the number of bytes we can expect from any single provider's entropy pool
# TODO dynamically adjust based on statistical data









  #---------------------------------------------#
 #             steps                           #
#---------------------------------------------#
# required by:  entropythief
async def steps(ctx: yapapi.WorkContext, tasks: AsyncIterable[yapapi.Task]):
    loop = asyncio.get_running_loop()
    async for task in tasks:
        start_time = datetime.now()
        expiration = datetime.now(timezone.utc) + timedelta(seconds=30)
        #taskid=task.data
        # request <count> bytes from provider and wait
        ctx.run(ENTRYPOINT_FILEPATH.as_posix(), str(task.data['req_byte_count']), task.data['rdrand_arg'])
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
            # download_bytes and invoke callback at task.data['writer']
            ctx.download_bytes(worker_public.RESULT_PATH.as_posix(), task.data['writer'], sys.maxsize)
            future_result = yield ctx.commit()
            # block/await here before switching to the other tasks otherwise state change
            # on buffer causes more work than necessary in my loop
            # task.accept_result(True)
            try:
                result = await asyncio.wait_for(future_result, timeout=60)
                if result:
                    task.accept_result(True)
                    print("STEPS: accepting result", file=sys.stderr)
            except asyncio.TimeoutError:
                print("steps: TIMEOUT", file=sys.stderr)
                task.reject_result("timeout")


  #---------------------------------------------#
 #             MySummaryLogger{}               #
#---------------------------------------------#
# Required by: entropythief
class MySummaryLogger(yapapi.log.SummaryLogger):
    costRunning = 0.0
    event_log_file=open('/dev/null')
    to_ctl_q = None

    def __init__(self, to_ctl_q):
        self.costRunning = 0.0
        self.to_ctl_q = to_ctl_q
        super().__init__()
        self.event_log_file = open("events.log", "w")

    def log(self, event: yapapi.events.Event) -> None:
        to_controller_msg = None
        if isinstance(event, yapapi.events.PaymentAccepted):
            self.costRunning += float(event.amount)
            to_controller_msg = {
                'cmd': 'update_total_cost', 'amount': self.costRunning}
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
        # print(event, file=self.event_log_file)


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
            self.to_ctl_q.put(to_controller_msg)

        super().log(event)


    def __del__(self):
        self.event_log_file.close()







@dataclass
class MyLeastExpensiveLinearPayMS(yapapi.strategy.LeastExpensiveLinearPayuMS, object):
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

    
    async def score_offer(
        self, offer: rest.market.OfferProposal, history: Optional[ComputationHistory] = None
    ) -> float:
        score = SCORE_REJECTED

        """
        if offer.props["golem.node.id.name"] == "friendly-winter":
            score = await super().score_offer(offer, history)
        # return score
        """
        # print(offer.props, file=sys.stderr)
        
        if self.use_rdrand:
            if offer.props["golem.inf.cpu.architecture"] == "x86_64":
                if 'rdrand' in offer.props["golem.inf.cpu.capabilities"]:
                    score = await super().score_offer(offer, history)
        else:
            score = await super().score_offer(offer, history)

        return score






  ###################################
 # TaskResultWriter{}              #
###################################
class TaskResultWriter:
    _writerPipe = None
    def __init__(self, to_ctl_q, POOL_LIMIT):
        self.to_ctl_q = to_ctl_q
        self._writerPipe = pipe_writer.PipeWriter(POOL_LIMIT)
        self.POOL_LIMIT = POOL_LIMIT

    def query_len(self) -> int:
        return self._writerPipe.len()

    def count_bytes_requesting(self) -> int:
        # check if the POOL_LIMIT has not been reached
        bytesInPipes = self._writerPipe.len()
        if bytesInPipes < self.POOL_LIMIT:
            return self.POOL_LIMIT - bytesInPipes
        else:
            return 0

    def refresh(self):
        self._writerPipe.refresh()

    async def __call__(self, randomBytes):
        written = self._writerPipe.write(randomBytes)
        await asyncio.sleep(0.01)
        # written = await write_to_pipe(self.fifoWriteEnd, randomBytes, self.POOL_LIMIT)
        msg = randomBytes[:written].hex()
        to_ctl_cmd = {'cmd': 'add_bytes', 'hexstring': msg}
        self.to_ctl_q.put(to_ctl_cmd)

    def __del__(self):
        if self._writerPipe:
            self._writerPipe.__del__()











  ###############################################
 #             entropythief()                  #
###############################################
async def entropythief(
        args
        , from_ctl_q
        , taskResultWriter
        , MINPOOLSIZE
        , to_ctl_q
        , BUDGET
        , MAXWORKERS
        , IMAGE_HASH
        , TASK_TIMEOUT=kTASK_TIMEOUT):
    """
    taskResultWriter: callable that inputs random bytes acquired
    """
    rdrand_arg = ''
    if args.rdrand:
        rdrand_arg = 'rdrand'
    try:
        loop = asyncio.get_running_loop()
        OP_STOP = False
        OP_PAUSE = False
        strat = MyLeastExpensiveLinearPayMS(
                # max_fixed_price=Decimal("0.0001"),
                # max_price_for={yapapi.props.com.Counter.CPU: Decimal("0.001"), yapapi.props.com.Counter.TIME: Decimal("0.001")}
                use_rdrand = args.rdrand
                ) 

        while not OP_STOP:
            await asyncio.sleep(0.05)
            mySummaryLogger = MySummaryLogger(to_ctl_q)
            # setup executor
            package = await vm.repo(
                image_hash=IMAGE_HASH, min_mem_gib=0.001, min_storage_gib=0.001
            )

            while (not OP_STOP): # can catch OP_STOP here and/or in outer
                taskResultWriter.refresh()
                await asyncio.sleep(0.05)
                if OP_PAUSE: # burn queue messages unless stop message seen
                    if not from_ctl_q.empty():
                        qmsg = from_ctl_q.get_nowait()
                        print(qmsg, file=sys.stderr)
                        if 'cmd' in qmsg and qmsg['cmd'] == 'stop':
                            OP_STOP = True
                        elif 'cmd' in qmsg and qmsg['cmd'] == 'resume execution':
                            OP_PAUSE=False # currently resume execution is not part of the design, included for future designs
                    continue # always rewind outer loop on OP_PAUSE

                # check that the pipe is writable before assigning work
                async with yapapi.Golem(
                    budget=BUDGET
                    , subnet_tag=args.subnet_tag
                    , network=args.network
                    , driver=args.driver
                    , event_consumer=mySummaryLogger.log
                    , strategy=strat
                ) as golem:
                    OP_STOP = False
                    while (not OP_STOP and not OP_PAUSE):
                        taskResultWriter.refresh()
                        await asyncio.sleep(0.05)
                        if not from_ctl_q.empty():
                            qmsg = from_ctl_q.get_nowait()
                            print(qmsg, file=sys.stderr)
                            if 'cmd' in qmsg and qmsg['cmd'] == 'stop':
                                OP_STOP = True
                                continue
                            elif 'cmd' in qmsg and qmsg['cmd'] == 'set buflim':
                                MINPOOLSIZE = qmsg['limit']
                            elif 'cmd' in qmsg and qmsg['cmd'] == 'set maxworkers':
                                MAXWORKERS = qmsg['count']
                            elif 'cmd' in qmsg and qmsg['cmd'] == 'pause execution':
                                OP_PAUSE=True
                        #/if

                        # query length of pipe -> bytesInPipe
                        bytesInPipe = taskResultWriter.query_len()
                        msg = {'bytesInPipe': bytesInPipe}
                        to_ctl_q.put_nowait(msg)

                        count_bytes_requested = taskResultWriter.count_bytes_requesting()
                        if count_bytes_requested > 0 and bytesInPipe < int(MINPOOLSIZE/2):
                            # TESTING
                            # if count_bytes_requested > 1024*1024:
                            #    count_bytes_requested = 1024*1024
                            # THIS IS TO TEST WHETHER THERE IS A HARD LIMIT ON DOWNLOAD_BYTES IN WORKER CONTEXT

                            # estimate how many workers it would take given the EXPECTED_ENTROPY per worker
                            workers_needed = int(count_bytes_requested/MAXWORKERS)
                            if workers_needed == 0:
                                workers_needed = 1 # always at least one to get at least 1 byte
                            # adjust down workers_needed if exceeding max
                            if workers_needed > MAXWORKERS:
                                workers_needed = MAXWORKERS

                            bytes_needed_per_worker = int(count_bytes_requested/workers_needed)
                            # execute tasks
                            completed_tasks = golem.execute_tasks(
                                steps,
                                [yapapi.Task(data={'req_byte_count': bytes_needed_per_worker, 'writer': taskResultWriter, 'rdrand_arg':rdrand_arg}) for _ in range(workers_needed)],
                                payload=package,
                                max_workers=workers_needed,
                                timeout=TASK_TIMEOUT
                            )
                            # generate results
                            async for task in completed_tasks:
                                taskResultWriter.refresh()
                                if task.result:
                                    # for now only the callback on task.data is used within steps
                                    pass
                                else:
                                    print("entropythief: a task result was not set!", file=sys.stderr)
                                await asyncio.sleep(0.003)
                            #/async for
                        #/if count_bytes_req...
                    #/while (not OP_...
                #/golem:
            #/while not OP_STOP
        #/while not OP_STOP
    except asyncio.CancelledError:
        taskResultWriter.__del__()
        pass












###########################################################################
#                               model__main                               #
#   main entry for the model                                              #
#   launches entropythief attaching message queues                        #
###########################################################################
def model__main(args
        , from_ctl_q
        , fifoWriteEnd
        , to_ctl_q
        , MINPOOLSIZE
        , MAXWORKERS
        , BUDGET
        , IMAGE_HASH
        , use_default_logger=True):
    """
        args := result of argparse.Namespace() from the controller/cli
        from_ctl_q := Queue of messages coming from controller
        fifoWriteEnd := named pipe where (valid) results are written
        to_ctl_q := Queue of messages going to controller
        MINPOOLSIZE := threshold count of random bytes above which workers temporarily stop
        MAXWORKERS := the maximum number of workers assigned at a time for results (may be reduced internally)
        BUDGET := the maxmum amount of GLM spendable per run
        IMAGE_HASH := the hash link to the vm that providers will run
    """

    # loop
    loop = asyncio.get_event_loop()

    # uncomment to output yapapi logger INFO events to stderr and INFO+DEBUG to args.log_fle
    if use_default_logger:
        yapapi.log.enable_default_logger(
            log_file=args.log_file
            , debug_activity_api=True
            , debug_market_api=True
            , debug_payment_api=True)

    # create the task
    taskResultWriter = TaskResultWriter(to_ctl_q, MINPOOLSIZE)
    task = loop.create_task(
        entropythief(
            args
            , from_ctl_q
            , taskResultWriter
            , MINPOOLSIZE
            , to_ctl_q
            , BUDGET
            , MAXWORKERS
            , IMAGE_HASH
            )
    )

    # gracefully conclude the task
    try:
        loop.run_until_complete(task)

    except KeyboardInterrupt:
        task.cancel()
        loop.run_until_complete(task)

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
        to_ctl_q.put_nowait(msg)

    except aiohttp.client_exceptions.ClientConnectorError as e:
        _msg = str(e)
        _msg += "\ndid you forget to invoke " + utils.TEXT_COLOR_YELLOW + "yagna service run" + utils.TEXT_COLOR_DEFAULT + "?"
        msg = {'exception': "..." +  _msg }
        to_ctl_q.put_nowait(msg)

    except Exception as e:
        task.cancel()
        msg = {'model exception': str(type(e)) + ": " + str(e) }
        to_ctl_q.put_nowait(msg)

    finally:
        taskResultWriter.__del__()
        # task.cancel()
        # loop.run_until_complete(task)
        print("MODEL: process exiting", file=sys.stderr)
        sys.exit(0)
        # cmd = {'cmd': 'stop'}
        # to_ctl_q.put_nowait(cmd)
