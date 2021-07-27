import fcntl
import os,sys
import asyncio
import termios
import json
import io
from functools import singledispatchmethod
import select
import itertools
import functools

"""
    PipeWriter
    ----------
    (_maxCapacity)
    countAvailable()                " how many bytes the object will accept at the moment
    len()                           " shall report count bytes in buffer
    write(data)                     " shall buffer input bytes
    refresh()                       " shall top off buffer as needed
    _countBytesInInternalBuffers()  " sic
    __del__()                       " shall close pipe ... cleanup


    _buffers = []
    _fdPipe
    _pipeCapacity
    _maxCapacity

    kNamedPipeFilePathString = '/tmp/pilferedbits'

    PipeWriter buffers and continually fills a pipe with bytes input via .write
    It needs to be reminded to top off the buffer when possible by a call to its refresh method.
    It shall top off the buffer when possible on every write call.
    Every frame of bytes is first sliced to top off the named pipe, then added to a stack/list.

"""

# issue: if a pipe is re-opened with data in it, it may exceed max capacity interfering with processing

try:
    _DEBUGLEVEL = int(os.environ['PYTHONDEBUGLEVEL'])
except:
    _DEBUGLEVEL = None

if not _DEBUGLEVEL:
    _DEBUGLEVEL=0


def _log_msg(msg, debug_level=0, file1=sys.stderr):
    pass
    if debug_level <= _DEBUGLEVEL:
        print(msg, file=sys.stderr)
        # print(msg, file=file1)








  #-------------------------------------------------#
 #           _write_to_pipe                         #
#-------------------------------------------------#
# required by: entropythief()
# nonblocking io!
def _write_to_pipe(fifoWriteEnd, thebytes):
    """
    fifoWriteEnd:
    thebytes:
    """
    WRITTEN = 0
    try:
        WRITTEN = os.write(fifoWriteEnd, thebytes)
    except BlockingIOError:
        _log_msg(f"_write_to_pipe: BlockingIOError, COULD NOT WRITE {len(thebytes)} bytes.", 0)
        WRITTEN=0
    except BrokenPipeError:
        WRITTEN=0
        _log_msg("BROKEN PIPE--------------------------------------", file=sys.stderr)
        raise
    except Exception as exception:
        _log_msg("_write_to_pipe: UNHANDLED EXCEPTION", file=sys.stderr)
        _log_msg(type(exception).__name__, file=sys.stderr)
        _log_msg(exception, file=sys.stderr)
        raise # asyncio.CancelledError #review
    finally:
        return WRITTEN










  #############################################################
 #                      PipeWriter{}                         #
#############################################################
class PipeWriter:
    _buffers = []
    _fdPipe = None
    _fdPoll = select.poll()
    _pipeCapacity = 0
    _maxCapacity = None

    _kNamedPipeFilePathString = '/tmp/pilferedbits'
    # _F_SETPIPE_SZ=1031
    _F_GETPIPE_SZ=1032



    # -------------------------------------------
    def __init__(self, maxCapacity=2**20):
    # -----------------------------------------
        self._maxCapacity=maxCapacity
        # _maxCapacity is the limit of bytes total the object will store (across pipe and internal buffers)
        # enforce a _maxCapacity that is no less than the theoretical maximum named pipe capacity 2**20
        assert self._maxCapacity >= 2**20

        self._open_pipe()
        if self._fdPipe:
            self._fdPoll.register(self._fdPipe)
        
        # attempt to obtain the expected maximum of one mebibyte
        try:
            pass
            # fcntl.fcntl(self._fdPipe, self._F_SETPIPE_SZ, 2**20)
        except OSError:
            pass
        finally:
            # record actually pipe size (either requested or left at system default)
            if self._fdPipe:
                self._pipeCapacity = fcntl.fcntl(self._fdPipe, self._F_GETPIPE_SZ)

        # make sure the current count of bytes in pipe is not in excess of max capacity
        bytesInPipe = self._count_bytes_in_pipe()
        assert bytesInPipe <= self._maxCapacity





    # -------------------------------------------
    def _set_max_capacity(maxcapacity):
        assert maxcapacity >= 2**20
        self._maxCapacity = maxcapacity
    # -------------------------------------------


    # -------------------------------------------
    def _whether_pipe_is_broken(self):
    # -------------------------------------------
        answer = False
        # consider a non existing fd as a broken pipe
        if self._fdPipe is None:
            answer = True
        else:
            pl = self._fdPoll.poll(0)
            # _log_msg(f"_whether_pipe_is_broken: {pl} {bin(pl[0][1])}")
            if len(pl) == 1:
                if pl[0][1] & 8: # broken pipe
                    answer = True

        return answer



    # -------------------------------------------
    def _count_bytes_in_pipe(self):
    # -------------------------------------------
        if self._whether_pipe_is_broken():
            return 0
        buf = bytearray(4)
        fcntl.ioctl(self._fdPipe, termios.FIONREAD, buf, 1)
        bytesInPipe = int.from_bytes(buf, "little")
        return bytesInPipe





    # -------------------------------------------
    def _open_pipe(self):
    # -------------------------------------------
        if self._fdPipe is not None:
            self._fdPoll.unregister(self._fdPipe)
        try:
            self._fdPipe = os.open(self._kNamedPipeFilePathString, os.O_WRONLY | os.O_NONBLOCK)
        except:
            self._fdPipe = None
        else:
            self._fdPoll.register(self._fdPipe)
            self._pipeCapacity = fcntl.fcntl(self._fdPipe, self._F_GETPIPE_SZ)
            _log_msg("\n_open_pipe: pipe opened!\n")







    # -----------------------------------------
    def refresh(self):
    # -----------------------------------------
        self.write(bytearray())




    # -----------------------------------------
    def countAvailable(self):
    # -----------------------------------------
        return self._maxCapacity - self._count_bytes_in_pipe() - self._countBytesInInternalBuffers()




    # --------------------------------------------
    def len(self):
    # -----------------------------------------
        countBytesInPipe = self._count_bytes_in_pipe()
        countBytesInInternalBuffers = self._countBytesInInternalBuffers()
        return countBytesInPipe + countBytesInInternalBuffers



    # ----------------------------------------------
    def write(self, data):
    # -----------------------------------------

        ###############################################################
        # .........................................
        def ___store_bytes(self, data):
        # .........................................
            # stores as much as the data as permitted in a bytearray added to the internal buffer list
            countAvailable = self.countAvailable()
            if len(data) > countAvailable:
                self._buffers.append(data[:countAvailable])
            else:
                self._buffers.append(data)


        # .........................................
        def ___countAvailableInPipe(self) -> int:
        # .........................................
            if self._fdPipe:
                bytesInPipe = self._count_bytes_in_pipe()
                _log_msg(f"counted {bytesInPipe} in pipe, returning difference from capacity of {self._pipeCapacity}", 4)
                return self._pipeCapacity - bytesInPipe
            else:
                _log_msg(f"___countAvailableInPipe: counted zero because self._fdPipe is {self._fdPipe}", 2)
                return 0


        # .........................................
        def ___try_write(self, data):
        # .........................................
            countBytesAvailableInPipe = ___countAvailableInPipe(self)
            remaining = len(data)
            written = 0

            # poll for broken pipe 
            if self._whether_pipe_is_broken():
                _log_msg("caught broken pipe!", 11)
                self._open_pipe()

            else: # pipe exists, try to fill
                # make sure the pipe is ready for writing
                sl = [ [], [], [] ]
                if self._fdPipe:
                    sl = select.select([], [self._fdPipe], [], 0)

                # TODO handle when pipe is in exception state

                if countBytesAvailableInPipe > 0 and len(sl[1]) > 0:
                    _log_msg(f"remaining to write to pipe: {remaining}", 2)
                    if remaining <= countBytesAvailableInPipe:
                        written = _write_to_pipe(self._fdPipe, data)
                    else:
                        written = _write_to_pipe(self._fdPipe, data[:countBytesAvailableInPipe])
                    _log_msg(f"written to pipe: {written}", 2)
                    remaining -= written
                    _log_msg(f"remaining after written to pipe: {remaining}", 2)

                    # _log_msg(f"Written: {written}, remaining: {remaining}")

            # add any remaining to buffer stacklist
            if remaining > 0:
                ___store_bytes(self, data[written:])
        ################################################################
        # reconnect a broken pipe if applicable
        if self._whether_pipe_is_broken():
            self._open_pipe()

        if self.countAvailable() == 0:
            data=bytearray() # slice to 0
            _log_msg(f"write: zeroed ... sliced data to {len(data)}", 3)
        elif len(data) > self.countAvailable():
            data=data[0:self.countAvailable()] 
            _log_msg(f"write: sliced data to {len(data)} using countAvailable = {self.countAvailable()}", 3)

        countBytesAvailableInPipe = ___countAvailableInPipe(self)
        _log_msg(f"count bytes available in pipe: {countBytesAvailableInPipe}", 1)


        if len(self._buffers) > 0:
                _log_msg(f"topping off pipe! bytes available in pipe {___countAvailableInPipe(self)}", 3)
                # regardless of the amount of data requested to be written, first top off pipe
                # top off pipe
                # countBytesInInternalBuffers = self._countBytesInInternalBuffers()
                # iterate across buffers accumulating length settling where length exceeds what pipe needs
                runningTotal = 0
                index = 0
                while runningTotal < countBytesAvailableInPipe and index < len(self._buffers):
                    # ->
                    runningTotal += len(self._buffers[index])
                    index+=1
                    # <-

                # index is now one past the last buffer in sequence to satisfy need
                # it is 1 if buffer[0] would satisfy the requirement

                # now we are interested in the total of buffers besides the last
                # as these will be emptied completely
                lastBufferIndex = index-1
                penUltimateBufferIndex = lastBufferIndex - 1
                countBytesToPenult = 0
                if lastBufferIndex > 0:
                    # count how many bytes would ideally be delivered
                    countBytesToPenult = 0
                    if penUltimateBufferIndex > 0:
                        for i in range(penUltimateBufferIndex):
                            __try_write(self, self._buffers[i]) # go ahead and write the contents
                            countBytesToPenult += self._buffers[i]
                    _log_msg(f"count bytes to penult: {countBytesToPenult}")                    
                    # lastBufferIndex will be used to as the count to pop the buffers after
                    # determine how many bytes would be taken from the last buffer if countBytesToPenult were written

                countBytesToTakeFromUlt = countBytesAvailableInPipe - countBytesToPenult
                    
                if lastBufferIndex > 0:
                    _log_msg("POP!")
                    # now pop and try to write from the buffers up to pen ult
                    for _ in range(lastBufferIndex):
                        self._buffers.pop()
               
                if countBytesToTakeFromUlt > 0:
                    _log_msg("topping off pipe using final buffer!", 3)
                    ___try_write(self, self._buffers[0][:countBytesToTakeFromUlt])
                    # rewrite buffer to exclude the part handled by the write routine
                    self._buffers[0] = self._buffers[0][countBytesToTakeFromUlt:-1]


        # after topping off, attempt to write new data (which pushed on stack as appropriate)
        ___try_write(self, data)





    # -----------------------------------------
    def _countBytesInInternalBuffers(self):
    # -----------------------------------------
        countBytesInBuffers = 0
        for ba in self._buffers:
            countBytesInBuffers += len(ba)
        return countBytesInBuffers




    # -------------------------------------------
    def __repr__(self):
    # -------------------------------------------
        output=f"""
max capacity: {self._maxCapacity}
bytes in pipe: {self._count_bytes_in_pipe()}
bytes in internal buffers: {self._countBytesInInternalBuffers()}
total available: {self.countAvailable()}
number of buffers: {len(self._buffers)}
"""
        return output


















    # -----------------------------------------
    def __del__(self):
    # -----------------------------------------
        
        try:
            os.close(self._fdPipe)
        except:
            pass
        try:
            pass
            # os.unlink(self._kNamedPipeFilePathString)
        except:
            pass

