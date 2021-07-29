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
        # start_time = datetime.now()
        # expiration = datetime.now(timezone.utc) + timedelta(seconds=30)
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
            # TODO instead of waiting on the download, yield and check if results were valid...
            try:
                yield ctx.commit(timeout=timedelta(minutes=6))
                task_accept(result=True) # for now blindly accept results
            except:
                task.reject_result("timeout")
            """
            future_result = yield ctx.commit()
            try:
                result = await asyncio.wait_for(future_result, timeout=60)
                if result:
                    task.accept_result(True)
                    print("STEPS: accepting result", file=sys.stderr)
            except asyncio.TimeoutError:
                print("steps: TIMEOUT", file=sys.stderr)
                task.reject_result("timeout")
            """





  #---------------------------------------------#
 #             MySummaryLogger{}               #
#---------------------------------------------#
# Required by: model__entropythief
# the log method is provided as the event-consumer for yapapi.Golem to intercept events
"""
    to_ctl_q:   the msg queue back to the controller
"""
class MySummaryLogger(yapapi.log.SummaryLogger):
    costRunning = 0.0
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
            # self.costRunning += float(event.amount)
            # to_controller_msg = {
            #    'cmd': 'update_total_cost', 'amount': self.costRunning}
            added_cost=float(event.amount)
            to_controller_msg = {
                'cmd': 'add cost', 'amount': added_cost}
            self.costRunning += added_cost
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
        
        # this would normally be a contrainst added to decorate_demand, but is here
        # for now as a convenience TODO implement via decorate_demand
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
# a callable wrapper around the pipe_writer module utilized by ctx.download_bytes in steps (a copy of which is stored in the task data)
# provides an interface for inspection of the buffer from elsewhere in the app
class TaskResultWriter:
    _bytesSeen = 0
    _writerPipe = None

    def __init__(self, to_ctl_q, POOL_LIMIT):
        self.to_ctl_q = to_ctl_q
        self._writerPipe = pipe_writer.PipeWriter(POOL_LIMIT)

    def query_len(self) -> int:
        return self._writerPipe.len()

    def count_bytes_requesting(self) -> int:
        # return how many bytes the buffer can accept
        # check if the POOL_LIMIT has not been reached
        return self._writerPipe.countAvailable()

    async def refresh(self, pool_limit=None):
        # since the PipeWriter object must be manually refreshed regularly
        if pool_limit:
            self._writerPipe._set_max_capacity(pool_limit)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(concurrent.futures.ThreadPoolExecutor(), self._writerPipe.refresh)

    async def __call__(self, randomBytes):
        self._bytesSeen += len(randomBytes)
        written = self._writerPipe.write(randomBytes)
        await asyncio.sleep(0.001) # may help yield cpu time (but steps async generator may be sufficient) REVIEW

        # inform controller
        msg = randomBytes[:written].hex()
        to_ctl_cmd = {'cmd': 'add_bytes', 'hexstring': msg}
        self.to_ctl_q.put(to_ctl_cmd)

    def __del__(self):
        if self._writerPipe:
            self._writerPipe.__del__()











  ###############################################
 #             model__entropythief()           #
###############################################
# execute tasks on the vm
# issues: not yet predicting whether the task will be rejected due to insufficient funds
#  but this is eventually caught after enough rejections
async def model__entropythief(
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
    from_ctl_q: the msg queue from the controller process
    taskResultWriter: callable that inputs random bytes acquired and writes (to buffered pipe)
    MINPOOLSIZE: the most bytes needed at any one time (actually a limit, e.g. set via set buflim=)
    to_ctl_q: the msg queue back to the controller process
    BUDGET: argument to yapapi.Golem
    MAXWORKERS: argument to golem.execute_tasks
    IMAGE_HASH: argument to vm.repo
    TASK_TIMEOUT: argument to golem.execute_task
    """

    # rdrand_arg is the string that is sent as an argument to each worker run call (if the client asked for it)
    if args.rdrand == 1:
        rdrand_arg = 'rdrand'
    else:
        rdrand_arg = ''

    loop = asyncio.get_running_loop()
    OP_STOP = False
    OP_PAUSE = False
    strat = MyLeastExpensiveLinearPayMS( # these MS parameters are not clearly documented ?
            max_fixed_price=Decimal("0.01"), # testing, ideally this works with the epsilon in model...
            # max_price_for={yapapi.props.com.Counter.CPU: Decimal("0.001"), yapapi.props.com.Counter.TIME: Decimal("0.001")}
            use_rdrand = args.rdrand
            ) 

    mySummaryLogger = MySummaryLogger(to_ctl_q)
    bytesInPipe = taskResultWriter.query_len() # note bytesInPipe is the lazy count
    while not OP_STOP:
        await taskResultWriter.refresh()

        if not from_ctl_q.empty():
            qmsg = from_ctl_q.get_nowait()
            print(f"message to model: {qmsg}", file=sys.stderr)
            if 'cmd' in qmsg and qmsg['cmd'] == 'stop':
                OP_STOP = True
                continue
            elif 'cmd' in qmsg and qmsg['cmd'] == 'set buflim':
                MINPOOLSIZE = qmsg['limit']
                await taskResultWriter.refresh(MINPOOLSIZE)
            elif 'cmd' in qmsg and qmsg['cmd'] == 'set maxworkers':
                MAXWORKERS = qmsg['count']
            elif 'cmd' in qmsg and qmsg['cmd'] == 'pause execution':
                OP_PAUSE=True
            elif 'cmd' in qmsg and qmsg['cmd'] == 'set budget':
                BUDGET=qmsg['budget']
            elif 'cmd' in qmsg and qmsg['cmd'] == 'unpause execution':
                OP_PAUSE=False
        #/if not from_ctl_q.empty()

        if not OP_PAUSE: # currently, OP_PAUSE is set whenever there are many rejections due to insufficient funds, it can be released by sending the command to restart (from the view)
            # query length of pipe -> bytesInPipe
            bytesInPipe_last = bytesInPipe
            bytesInPipe = taskResultWriter.query_len()
            if bytesInPipe != bytesInPipe_last:
                msg = {'bytesInPipe': bytesInPipe}
                # prevent message congestion by only sending updates
                to_ctl_q.put_nowait(msg)

            count_bytes_requested = taskResultWriter.count_bytes_requesting()
            if count_bytes_requested > 0 and bytesInPipe < int(MINPOOLSIZE/2) and mySummaryLogger.costRunning < BUDGET:
                # this inner loop is for future handling of a stop op that is asking for a reset
                # as from a request to rerun with a different budget or to just stop advertising for offers
                # await asyncio.sleep(0.01)
                # setup executor
                package = await vm.repo(
                        image_hash=IMAGE_HASH, min_mem_gib=0.3, min_storage_gib=0.3
                        )

                # this loop continually monitors offers then if more workers are needed (below buflim), provisions accordingly
                # the efficiency / noise factor is being reviewed

                # await asyncio.sleep(0.01)

                async with yapapi.Golem(budget=BUDGET-mySummaryLogger.costRunning,      subnet_tag=args.subnet_tag,         network=args.network
                                      , driver=args.driver, event_consumer=mySummaryLogger.log, strategy=strat
                        ) as golem:
                    await asyncio.sleep(0.01)

                    bytes_needed_per_worker = int(count_bytes_requested/MAXWORKERS)
                    # execute tasks
                    completed_tasks = golem.execute_tasks(
                            steps,
                            [yapapi.Task(data={'req_byte_count': bytes_needed_per_worker, 'writer': taskResultWriter, 'rdrand_arg':rdrand_arg}) for _ in range(MAXWORKERS)],
                            payload=package,
                            max_workers=MAXWORKERS,
                            timeout=TASK_TIMEOUT
                            )
                    # generate results
                    async for task in completed_tasks:
                        await taskResultWriter.refresh()
                        if task.result:
                            # the result has already been handled in steps, this is here for debugging purposes
                            pass
                        else:
                            pass
                            # print("entropythief: a task result was not set!", file=sys.stderr)

                        await asyncio.sleep(0.01)
                        #/async for
                    #/golem:
                #/if count_bytes_requested...
            #/if not OP_PAUSE
            await asyncio.sleep(0.01)
        #/while not OP_STOP
    msg = {'bytesPurchased': taskResultWriter._bytesSeen}
    to_ctl_q.put_nowait(msg)










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
        model__entropythief(
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
        to_ctl_q.put_nowait(msg)
    except aiohttp.client_exceptions.ClientConnectorError as e:
        _msg = str(e)
        _msg += "\ndid you forget to invoke " + utils.TEXT_COLOR_YELLOW + "yagna service run" + utils.TEXT_COLOR_DEFAULT + "?"
        msg = {'exception': "..." +  _msg }
        to_ctl_q.put_nowait(msg)
    except Exception as e:
        # this should not happen
        msg = {'model exception': {'name': e.__class__.__name__, 'what': str(e) } }
        to_ctl_q.put_nowait(msg)
    finally:
        # send a message back to the controller that the (daemonized) process has cleanly exited
        # consider a more clean exit by checking if task is running first
        try:
            task.cancel() # make sure cancel message has been propagated to EntropyThief (and Golem)
            loop.run_until_complete(task)
        except:
            pass

        msg = {'daemon': "finished"}
        to_ctl_q.put_nowait(msg)
