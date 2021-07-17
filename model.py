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
# 3rd party
import  yapapi
from    yapapi          import log
from    yapapi.payload  import vm

# internal
import  utils
import  worker




ENTRYPOINT_FILEPATH = Path("/golem/run/worker.py")
kTASK_TIMEOUT = timedelta(minutes=6)
# EXPECTED_ENTROPY = 1044480 # the number of bytes we can expect from any single provider's entropy pool
# TODO dynamically adjust based on statistical data







  #-------------------------------------------------#
 #           write_to_pipe                         #
#-------------------------------------------------#
# required by: entropythief()
async def write_to_pipe(fifoWriteEnd, thebytes, POOL_LIMIT):
    WRITTEN = 0
    try:
        loop = asyncio.get_running_loop()

        buf = bytearray(4)
        fcntl.ioctl(fifoWriteEnd, termios.FIONREAD, buf, 1)
        bytesInPipe = int.from_bytes(buf, "little")
        bytesNeeded = POOL_LIMIT - bytesInPipe

        count_to_write = 0
        if bytesNeeded > 0:
            count_to_write = len(thebytes)
            if count_to_write + bytesInPipe > POOL_LIMIT:
                count_to_write = POOL_LIMIT - bytesInPipe 
            if count_to_write > len(thebytes): #review
                count_to_write = len(thebytes)
            count_remaining = count_to_write
            written = os.write(fifoWriteEnd, thebytes[:count_remaining])
            total_written = written
            offset=written
            WRITTEN = written
            """
            # while count_remaining - written >= 4096 and total_written < count_to_write:
            while count_remaining - written > 1 and total_written < count_to_write:
                count_remaining -= written
                POOL_LIMIT_F = fcntl.fcntl(fifoWriteEnd, 1032)
                buf = bytearray(4)
                fcntl.ioctl(fifoWriteEnd, termios.FIONREAD, buf, 1)
                bytesInPipe = int.from_bytes(buf, "little")
                written = os.write(fifoWriteEnd, thebytes[offset:(offset + count_remaining)])
                offset+=written
                total_written+=written
            """
        return WRITTEN
    except BlockingIOError:
        print(f"write_to_pipe: COULD NOT WRITE. count_remaining = {count_remaining}", file=sys.stderr)
        WRITTEN=0
        pass
    except BrokenPipeError:
        WRITTEN=0
        raise
    except Exception as exception:
        print("write_to_pipe: UNHANDLED EXCEPTION", file=sys.stderr)
        print(type(exception).__name__, file=sys.stderr)
        print(exception, file=sys.stderr)
        raise asyncio.CancelledError #review
    finally:
        return WRITTEN









  #---------------------------------------------#
 #             steps                           #
#---------------------------------------------#
# required by:  entropythief
async def steps(ctx: yapapi.WorkContext, tasks: AsyncIterable[yapapi.Task]):
    loop = asyncio.get_running_loop()
    async for task in tasks:
        try:
            start_time = datetime.now()
            expiration = datetime.now(timezone.utc) + timedelta(seconds=30)
            #taskid=task.data
            ctx.run(ENTRYPOINT_FILEPATH.as_posix(), str(task.data['req_byte_count']))

            # TODO ensure worker does not output on error
            future_results = yield ctx.commit()
            results = await future_results
            print(results, file=sys.stderr)
            stderr=results[-1].stderr
            if stderr:
                print("A WORKER REPORTED AN ERROR:\n", stderr, file=sys.stderr)
                task.reject_result(stderr)
            elif results[-1].success == False:
                task.reject_result()
            else:
                ctx.download_bytes(worker.RESULT_PATH.as_posix(), task.data['writer'], sys.maxsize)
                future_result = yield ctx.commit()
                # block/await here before switching to the other tasks otherwise state change
                # on buffer causes more work than necessary in my loop
                await asyncio.wait_for(future_result, timeout=30)
                # result = await future_result
                task.accept_result()
        except asyncio.TimeoutError:
            print("steps: TIMEOUT", file=sys.stderr)
            task.reject_result()
        except Exception as exception:
            print("steps: UNHANDLED EXCEPTION", file=sys.stderr)
            print(type(exception).__name__, file=sys.stderr)
            print(exception, file=sys.stderr)
            raise exception
        finally:
            try:
                pass
            except FileNotFoundError:
                pass






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








# TEMPORARY SCAFFOLDING
from types import MappingProxyType
from typing import Dict, Mapping, Optional
from yapapi.props import com, Activity
from yapapi import rest
from yapapi.strategy import *
@dataclass
class MyLeastExpensiveLinearPayMS(yapapi.strategy.LeastExpensiveLinearPayuMS, object):
    golem = None
    def __init__(
        self
        , expected_time_secs: int = 60
        , max_fixed_price: Decimal = Decimal("inf")
        , max_price_for: Mapping[com.Counter, Decimal] = MappingProxyType({})
        ):
            super().__init__(expected_time_secs, max_fixed_price, max_price_for)

    
    async def score_offer(
        self, offer: rest.market.OfferProposal, history: Optional[ComputationHistory] = None
    ) -> float:
        score = SCORE_REJECTED
        print(offer.props, file=sys.stderr)
        if offer.props["golem.inf.cpu.architecture"] == "x86_64":
            if 'rdrand' in offer.props["golem.inf.cpu.capabilities"]:
                score = await super().score_offer(offer, history)
        """
        if offer.props["golem.node.id.name"] == "friendly-winter":
            print("******************** SAW AND REJECTED FRIENDLY WINTER !!!!! MUAHAHAHHAHAH", file=sys.stderr)
        else:
            score = await super().score_offer(offer, history)
        return score
        """
        # return await super().score_offer(offer, history)
        if score == SCORE_REJECTED:
            print("REJECTED------------------------------------------\n\n\n", file=sys.stderr)
        return score










  ###################################
 # TaskResultWriter{}              #
###################################
class TaskResultWriter:
    def __init__(self, fifoWriteEnd, to_ctl_q, POOL_LIMIT):
        self.to_ctl_q = to_ctl_q
        self.fifoWriteEnd = fifoWriteEnd
        self.POOL_LIMIT = POOL_LIMIT

    async def __call__(self, randomBytes):
        written = await write_to_pipe(self.fifoWriteEnd, randomBytes, self.POOL_LIMIT)
        msg = randomBytes[:written].hex()
        to_ctl_cmd = {'cmd': 'add_bytes', 'hexstring': msg}
        self.to_ctl_q.put(to_ctl_cmd)










  ###############################################
 #             entropythief()                  #
###############################################
async def entropythief(args, from_ctl_q, fifoWriteEnd, MINPOOLSIZE, to_ctl_q, BUDGET, MAXWORKERS, IMAGE_HASH, TASK_TIMEOUT=kTASK_TIMEOUT):
    taskResultWriter = TaskResultWriter(fifoWriteEnd, to_ctl_q, MINPOOLSIZE)
    # sel = selectors.DefaultSelector()
    # sel.register(fifoWriteEnd, selectors.EVENT_WRITE)
    try:
        loop = asyncio.get_running_loop()
        OP_STOP = False
        OP_PAUSE = False
        strat = MyLeastExpensiveLinearPayMS(
                # max_fixed_price=Decimal("0.0001"),
                # max_price_for={yapapi.props.com.Counter.CPU: Decimal("0.001"), yapapi.props.com.Counter.TIME: Decimal("0.001")}
                ) 

        while not OP_STOP:
            await asyncio.sleep(0.05)
            mySummaryLogger = MySummaryLogger(to_ctl_q)
            # setup executor
            package = await vm.repo(
                image_hash=IMAGE_HASH, min_mem_gib=0.001, min_storage_gib=0.001
            )

            while (not OP_STOP): # can catch OP_STOP here and/or in outer
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
                        # events = sel.select()[0] # (SelectorKey, <integer>) <- []
                        # print(type(events), file=sys.stderr)
                        # print(len(events), file=sys.stderr)
                        # print(f"---------------------------------{events}", file=sys.stderr)
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
                        buf = bytearray(4)
                        fcntl.ioctl(fifoWriteEnd, termios.FIONREAD, buf, 1)
                        # await loop.run_in_executor(None, fcntl.ioctl, fifoWriteEnd, termios.FIONREAD, buf, 1)
                        bytesInPipe = int.from_bytes(buf, "little")
                        if bytesInPipe < int(MINPOOLSIZE/2):
                            bytes_needed = MINPOOLSIZE - bytesInPipe
                            # estimate how many workers it would take given the EXPECTED_ENTROPY per worker
                            workers_needed = int(bytes_needed/MAXWORKERS)
                            if workers_needed == 0:
                                workers_needed = 1 # always at least one to get at least 1 byte
                            # adjust down workers_needed if exceeding max
                            if workers_needed > MAXWORKERS:
                                workers_needed = MAXWORKERS

                            bytes_needed_per_worker = int(bytes_needed/workers_needed)
                            # execute tasks
                            completed_tasks = golem.execute_tasks(
                                steps,
                                [yapapi.Task(data={'req_byte_count': bytes_needed_per_worker, 'writer': taskResultWriter}) for _ in range(workers_needed)],
                                payload=package,
                                max_workers=workers_needed,
                                timeout=TASK_TIMEOUT
                            )
                            # generate results
                            async for task in completed_tasks:
                                if task.result:
                                    try:
                                        print("++++++++++++++++++++COMPLETED TASK!!!!!!!!!", file=sys.stderr)
                                        pass
                                        # msg = randomBytes.hex()
                                        # to_ctl_cmd = {'cmd': 'add_bytes', 'hexstring': msg}
                                        # to_ctl_q.put(to_ctl_cmd)
                                        # await write_to_pipe(fifoWriteEnd, randomBytes)

                                    except Exception as exception:
                                        print(task.result, file=sys.stderr)
                                        print("completed_tasks: UNHANDLED EXCEPTION", file=sys.stderr)
                                        print(type(exception).__name__, file=sys.stderr)
                                        print(exception, file=sys.stderr)
                                        raise asyncio.CancelledError #review
                            #/async for
                        #/if
                    #/while True
                #/while not OP_PAUSE
            #/while not OP_STOP
    except Exception as exception:
        print("entropythief: UNHANDLED EXCEPTION", file=sys.stderr)
        print(type(exception).__name__, file=sys.stderr)
        print(exception, file=sys.stderr)
        raise
        # raise asyncio.CancelledError #review













###########################################################################
#                               model__main                               #
#   main entry for the model                                              #
#   launches entropythief attaching message queues                        #
###########################################################################
def model__main(args, from_ctl_q, fifoWriteEnd, to_ctl_q, MINPOOLSIZE, MAXWORKERS, BUDGET, IMAGE_HASH, use_default_logger=True):
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
    task = loop.create_task(
        entropythief(
            args
            , from_ctl_q
            , fifoWriteEnd
            , MINPOOLSIZE
            , to_ctl_q
            , BUDGET
            , MAXWORKERS
            , IMAGE_HASH)
    )

    try:
        loop.run_until_complete(task)
    except asyncio.exceptions.CancelledError:
        pass
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
        msg = {'exception': str(type(e)) + ": " + str(e) }
        to_ctl_q.put_nowait(msg)

    finally:
        cmd = {'cmd': 'stop'}
        to_ctl_q.put_nowait(cmd)
        """
        pending = asyncio.all_tasks()
        for task in pending:
            task.cancel()

        print("gathering")
        group = asyncio.gather(*pending, return_exceptions=True)
        print("run until complete")
        results_with_any_exceptions = loop.run_until_complete(group)
        # all exceptions should have been handled, on the off chance
        # not, this effectively ignores and stores them so all
        # tasks not raising can be shutdown
        print("close")
        loop.close()
        """
