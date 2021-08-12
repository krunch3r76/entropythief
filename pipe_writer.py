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


import queue
import collections

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


_DEBUGLEVEL = int(os.environ['PYTHONDEBUGLEVEL']) if 'PYTHONDEBUGLEVEL' in os.environ else 0


def _log_msg(msg, debug_level=0, stream=sys.stderr):
    pass
    if debug_level <= _DEBUGLEVEL:
        print(f"\n{msg}\n", file=sys.stderr)



# MyBytesIO wraps StringIO so that reads advance the stream to behavior like a file stream
##################{}#####################
class MyBytesIO(io.BytesIO):
#########################################

    def __init__(self, initial_value):
        super().__init__(initial_value)
        self.seek(0, io.SEEK_END)
        self.__end = self.tell()
        self.seek(0, io.SEEK_SET)
        self._offset=0

    @property
    def end(self):
        return self.__end

    def len(self):
        # distance from end to current
        return self.__end - self.tell()

    def __len__(self):
        return self.len()

    def __del__(self):
        self.close()

    """
    def read(self, count):
        rv = super().read(count)
        return rv
    """

    def putback(self, count):
        self.seek(-count, io.SEEK_CUR)

    def write(self, count):
        assert False, "MyBytesIO does not support write operation"


class MyBytesDeque(collections.deque):
    _runningTotal = 0

    def __init__(self):
        super().__init__()

    def append(self, mybytesio):
        assert isinstance(mybytesio, MyBytesIO)
        self._runningTotal += len(mybytesio)
        super().append(mybytesio)

    def insert(self, index, mybytesio):
        self._runningTotal += len(mybytesio)
        super().insert(index, mybytesio)

    def appendleft(self, mybytesio):
        self.insert(0, mybytesio)

    def popleft(self):
        rv = super().popleft()
        self._runningTotal -= len(rv)
        return rv

    def len(self):
        return self._runningTotal

    def __len__(self):
        return self.len()

    # def total(self):
    #     return self.len()


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
        for _ in range(10):
            try:
                WRITTEN = os.write(fifoWriteEnd, thebytes)
            except BlockingIOError:
                WRITTEN = 0
            else:
                break
    except BrokenPipeError:
        WRITTEN=0
        _log_msg("BROKEN PIPE--------------------------------------", 1)
        # make fd_pipe none
        raise # review whether the exception should be raised TODO
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
    _byteQ = MyBytesDeque()
    _fdPipe = None
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

        return answer


    # -------------------------------------------
    def _whether_pipe_is_ready_for_writing(self):
    # -------------------------------------------
        answer = False
        # consider a non existing fd as a broken/unready pipe
        if self._fdPipe is None:
            answer = False
        else:
            answer = True

        return answer





    # -------------------------------------------
    def _count_bytes_in_pipe(self):
    # -------------------------------------------
        if self._whether_pipe_is_broken():
            return 0

        bytesInPipe = 0
        if self._fdPipe:
            buf = bytearray(4)
            fcntl.ioctl(self._fdPipe, termios.FIONREAD, buf, 1)
            bytesInPipe = int.from_bytes(buf, "little")
            
        return bytesInPipe





    # -------------------------------------------
    def _open_pipe(self):
    # -------------------------------------------
        if not self._fdPipe:
            try:
                self._fdPipe = os.open(self._kNamedPipeFilePathString, os.O_WRONLY | os.O_NONBLOCK)
                self._pipeCapacity = fcntl.fcntl(self._fdPipe, self._F_GETPIPE_SZ)
                _log_msg("_open_pipe: pipe opened!", 1)
            except OSError:
                pass






    # -----------------------------------------
    def refresh(self):
    # -----------------------------------------
        self._open_pipe()
        self.write(bytearray())




    # -----------------------------------------
    def countAvailable(self):
    # -----------------------------------------
        return self._maxCapacity - self._count_bytes_in_pipe() - self._byteQ.len()




    # --------------------------------------------
    def len(self):
    # -----------------------------------------
        countBytesInPipe = self._count_bytes_in_pipe()
        countBytesInInternalBuffers = self._countBytesInInternalBuffers()

        return countBytesInPipe + countBytesInInternalBuffers


    def _len_q(self):
        running_total = 0
        for i in len(self._byteQ):
            running_total += self._byteQ.len()

        return running_total

    # ----------------------------------------------
    def write(self, data):
    # -----------------------------------------
        if data and len(data) > 0:
            print(f"pipe_writer.py write received {len(data)} bytes", file=sys.stderr)
        ###############################################################

        # .........................................
        def ___countAvailableInPipe(self) -> int:
        # .........................................
            if self._fdPipe:
                bytesInPipe = self._count_bytes_in_pipe()
                return self._pipeCapacity - bytesInPipe
            else:
                return 0





        # ...
        ################################################################
        #               // begin routine write //                      #
        ################################################################

        # append queue with data
        countBytesIn = len(data)

        if countBytesIn > self.countAvailable():
            countBytesIn = self.countAvailable()
        bytesToStore=countBytesIn

        bytestream = io.BytesIO(data)

        # chunk input into pages added to the byteQ, might help prevent blocking io
        # might facilitate asynchronous implementation
        while True:
            chunk_of_bytes = bytestream.read(4096)
            if len(chunk_of_bytes) == 0:
                break
            self._byteQ.append(MyBytesIO(chunk_of_bytes))

        if countBytesIn > 0 or bytesToStore > 0:
            print(f"stored!", file=sys.stderr)

        # reconnect a broken pipe if applicable
        if self._whether_pipe_is_broken():
            self._open_pipe()

        # move data from queue to top of pipe
        free = ___countAvailableInPipe(self) # empty count
        BLOCKED = False
        while free > 0 and not BLOCKED:
            try:
                first = self._byteQ.popleft()
                if first.len() <= free:
                    written = _write_to_pipe(self._fdPipe, first.getbuffer())
                    if written == 0:
                        BLOCKED = True
                        self._byteQ.appendleft(first)
                    else:
                        free -= first.len() # assumes all written
                        continue # superfluous
                else: # len(first) > free
                    frame = first.read(free)
                    written = _write_to_pipe(self._fdPipe, frame[:free])
                    if written == 0:
                        BLOCKED = True
                        first.putback(free)
                    else:
                        self._byteQ.appendleft(first)
            except IndexError:
                break

        return len(data) # stub





    # -----------------------------------------
    def _countBytesInInternalBuffers(self):
    # -----------------------------------------
        """
        countBytesInBuffers = 0
        for ba in self._buffers:
            countBytesInBuffers += len(ba)
        return countBytesInBuffers
        """
        return self._byteQ.len()
        # return self._byteQ.qsize()
        


    # -------------------------------------------
    def __repr__(self):
    # -------------------------------------------
        output=f"""
max capacity: {self._maxCapacity}
bytes in pipe: {self._count_bytes_in_pipe()}
bytes in internal buffers: {self._countBytesInInternalBuffers()}
total available: {self.countAvailable()}
number of buffers: {len(self._buffers)}
total bytes: {self._countBytesInInternalBuffers() + self._count_bytes_in_pipe()}
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

