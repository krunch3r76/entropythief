# pipe_writer
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)

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
import time

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


try:
    _DEBUGLEVEL = int(os.environ['PYTHONDEBUGLEVEL'])
except:
    _DEBUGLEVEL = None

if not _DEBUGLEVEL:
    _DEBUGLEVEL=0


def _log_msg(msg, debug_level=0, stream=sys.stderr):
    pass
    if debug_level <= _DEBUGLEVEL:
        print(f"\n{msg}\n", file=sys.stderr)








  #-------------------------------------------------#
 #           _write_to_pipe                         #
#-------------------------------------------------#
# required by: entropythief()
# pre: named pipe has been polled for writability -> nonblocking
def _write_to_pipe(fifoWriteEnd, thebytes):
    """
    fifoWriteEnd: a file descriptor the a named pipe
    thebytes: the bytes to write
    """
    WRITTEN = 0
    try:
        WRITTEN = os.write(fifoWriteEnd, thebytes)
    except BlockingIOError:
        _log_msg(f"_write_to_pipe: BlockingIOError, COULD NOT WRITE {len(thebytes)} bytes.", 1)
        WRITTEN=0
    except BrokenPipeError:
        WRITTEN=0
        _log_msg("BROKEN PIPE--------------------------------------", 0)
        raise
    except Exception as exception:
        _log_msg("_write_to_pipe: UNHANDLED EXCEPTION")
        _log_msg(type(exception).__name__)
        _log_msg(exception)
        raise
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
    _F_GETPIPE_SZ=1032


    # TODO make maxCapacity a required argument
    # -------------------------------------------
    def __init__(self, maxCapacity=2**20):
    # -----------------------------------------
        if maxCapacity < 2**20:
            maxCapacity = 2**20
        self._maxCapacity=maxCapacity
        # _maxCapacity is the limit of bytes total the object will store (across pipe and internal buffers)
        # enforce a _maxCapacity that is no less than the theoretical maximum named pipe capacity 2**20
        # assert maxcapacity >= 2**20, f"the minimum buffer size is 1 mebibyte or {int(eval('2**20'))}"
        self._open_pipe()
        if self._fdPipe:
            self._fdPoll.register(self._fdPipe)
        
            if self._fdPipe:
                self._pipeCapacity = fcntl.fcntl(self._fdPipe, self._F_GETPIPE_SZ)
            bytesInPipe = self._count_bytes_in_pipe()
            assert bytesInPipe <= self._maxCapacity





    # -------------------------------------------
    def _set_max_capacity(self, maxcapacity):
        # assert maxcapacity >= 2**20, f"the minimum buffer size is 1 mebibyte or {int(eval('2**20'))}"
        if maxcapacity < 2**20:
            maxcapacity = 2**20
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
    def _whether_pipe_is_ready_for_writing(self):
    # -------------------------------------------
        answer = False
        # consider a non existing fd as a broken/unready pipe
        if self._fdPipe is None:
            answer = False
        else:
            pl = self._fdPoll.poll(0)
            if len(pl) == 1:
                if pl[0][1] & 4: # writing will not block
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
            _log_msg("_open_pipe: pipe opened!", 3)







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
                return self._pipeCapacity - bytesInPipe
            else:
                return 0


        # .........................................
        def ___try_write(self, data):
        # .........................................
        # try writing first to pipe then whatever could not be written push as a new stack buffer
            countBytesAvailableInPipe = ___countAvailableInPipe(self)
            remaining = len(data)
            written = 0


            if countBytesAvailableInPipe > 0:
                if remaining <= countBytesAvailableInPipe:
                    written = _write_to_pipe(self._fdPipe, data)
                else:
                    written = _write_to_pipe(self._fdPipe, data[:countBytesAvailableInPipe])
                    remaining -= written

            # slice anything that was not successfully written to the name pipe and push unto internal stack
            if remaining > 0:
                ___store_bytes(self, data[written:])

        # ...
        ################################################################
        #               // begin routine //                            #
        ################################################################
        # reconnect a broken pipe if applicable
        if self._whether_pipe_is_broken():
            self._open_pipe()

        if self.countAvailable() == 0:
            data=bytearray() # no space, slice to 0
        elif len(data) > self.countAvailable():
            data=data[0:self.countAvailable()] # slice up to capacity available
            #...just in case the caller did not check first

        countBytesAvailableInPipe = ___countAvailableInPipe(self)

        # here we move data in the buffers into any available capacity of the named pipe
        # waiting until the pipe has been completely emptied prevents blocking io
        #  reduces lost bytes due to simultaneous read writes. TODO experiment with nonzero values
        if len(self._buffers) > 0 and self._whether_pipe_is_ready_for_writing() and self._count_bytes_in_pipe() == 0:
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
                            ___try_write(self, self._buffers[i]) # go ahead and write the contents
                            # time.sleep(0.001)
                            countBytesToPenult += len(self._buffers[i])
                    # lastBufferIndex will be used to as the count to pop the buffers after
                    # determine how many bytes would be taken from the last buffer if countBytesToPenult were written

                countBytesToTakeFromUlt = countBytesAvailableInPipe - countBytesToPenult
                    
                # buffers up to but not including end buffer have been consumed
                # pop them \/
                if lastBufferIndex > 0:
                    for _ in range(lastBufferIndex):
                        self._buffers.pop()
               
                if countBytesToTakeFromUlt > 0:
                # [ remaining buffer bytes can now be taken and placed in named pipe up to the calculate amount ]
                    ___try_write(self, self._buffers[0][:countBytesToTakeFromUlt])
                    # time.sleep(0.001)
                    # rewrite buffer to exclude the part handled by the write routine
                    self._buffers[0] = self._buffers[0][countBytesToTakeFromUlt:-1]


        # after topping off, attempt to write new data (which is pushed on stack as appropriate)
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
            pass
            os.close(self._fdPipe) # closing the only write end might delete the pipe?
        except:
            pass
        try:
            pass
            # os.unlink(self._kNamedPipeFilePathString)
        except:
            pass

