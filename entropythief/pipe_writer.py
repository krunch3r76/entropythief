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


_DEBUGLEVEL = int(os.environ['PYTHONDEBUGLEVEL']) if 'PYTHONDEBUGLEVEL' in os.environ else 0


def _log_msg(msg, debug_level=0, stream=sys.stderr):
    pass
    if debug_level <= _DEBUGLEVEL:
        print(f"\n[pipe_writer.py] {msg}\n", file=sys.stderr)



##################{}#####################

class MyBytesIO(io.BytesIO):
    """wraps io.BytesIO to behave like a stream"""

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


    def putback(self, count):
        self.seek(-(count), io.SEEK_CUR)

    def write(self, count):
        assert False, "MyBytesIO does not support write operation"






####################### {} ########################
class MyBytesDeque(collections.deque):
    """wraps collections.deque to keep track of size of contents"""
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









def _write_to_pipe(fifoWriteEnd, thebytes):
    """ writes bytes to a fifo
        required by model__entropythief
        pre: named pipe has been polled for writability -> nonblocking

        fifoWriteEnd: a file descriptor the a named pipe
        thebytes: the bytes to write
    """
    # required by: entropythief()
    WRITTEN = 0
    try:
        WRITTEN = os.write(fifoWriteEnd, thebytes)
    except BlockingIOError:
        _log_msg(f"_write_to_pipe: BlockingIOError, COULD NOT WRITE {len(thebytes)} bytes.", 2)
        for _ in range(10):
            try:
                WRITTEN = os.write(fifoWriteEnd, thebytes)
            except BlockingIOError:
                WRITTEN = 0
            else:
                break
    except BrokenPipeError:
        WRITTEN=0
        _log_msg("BROKEN PIPE--------------------------------------", 2)
        # make fd_pipe none
        raise # review whether the exception should be raised TODO
    except Exception as exception:
        _log_msg("_write_to_pipe: UNHANDLED EXCEPTION")
        _log_msg(type(exception).__name__)
        _log_msg(exception)
        raise
    finally:
        return WRITTEN









##################################{}#########################3
class PipeWriter:
    """writes as much as it can to a named pipe buffering the rest"""
    _byteQ = MyBytesDeque()
    _fdPipe = None
    _pipeCapacity = 0
    _maxCapacity = None
    _kNamedPipeFilePathString = '/tmp/pilferedbits'
    _F_GETPIPE_SZ=1032


    # TODO make maxCapacity a required argument
    # ---------PipeWriter------------------------
    def __init__(self, maxCapacity=2**20):
        """initializes with how much the named pipe itself is expected to accept"""
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





    # --------------PipeWriter-------------------
    def _set_max_capacity(self, maxcapacity):
        """informs on a new upper limit for the named pipe"""
        # assert maxcapacity >= 2**20, f"the minimum buffer size is 1 mebibyte or {int(eval('2**20'))}"
        if maxcapacity < 2**20:
            maxcapacity = 2**20
        self._maxCapacity = maxcapacity
    # -------------------------------------------






    # -------------------------------------------
    def _whether_pipe_is_broken(self):
        """determines if the pipe is still available to be written to"""
    # -------------------------------------------
        answer = False
        # consider a non existing fd as a broken pipe
        if self._fdPipe is None:
            answer = True

        return answer






    # -------------------------------------------
    def _count_bytes_in_pipe(self):
        """counts how many bytes are currently residing in the named pipe"""
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
        """assigns the pipe to an internal file descriptor if not already set"""
    # -------------------------------------------
        if not self._fdPipe:
            try:
                self._fdPipe = os.open(self._kNamedPipeFilePathString, os.O_WRONLY | os.O_NONBLOCK)
                self._pipeCapacity = fcntl.fcntl(self._fdPipe, self._F_GETPIPE_SZ)
                _log_msg("_open_pipe: pipe opened!", 1)
            except OSError:
                pass






    # -----------------------------------------
    async def refresh(self):
        """opens a named pipe if not connected and calls to write any buffered"""
    # -----------------------------------------
        self._open_pipe()
        await self.write(bytearray())




    # -----------------------------------------
    def countAvailable(self):
        """computes at a given moment how many bytes could be accepted assuming all asynchronous work is done"""
    # -----------------------------------------
        return self._maxCapacity - self._count_bytes_in_pipe() - self._byteQ.len()




    # --------------------------------------------
    def len(self):
    # -----------------------------------------
        """computes the sum of bytes from both the named pipe and internal queued bytechunks"""
        countBytesInPipe = self._count_bytes_in_pipe()
        countBytesInInternalBuffers = self._countBytesInInternalBuffers()

        return countBytesInPipe + countBytesInInternalBuffers



    # ----------------------------------------------
    async def write(self, data):
        """queues/buffers any incoming data then dequeues data to write into named pipe"""
        if data and len(data) > 0:
            _log_msg(f"::[write] received {len(data)} bytes", 3)
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


        # 1 append queue with input data
        countBytesIn = len(data)

        if countBytesIn > self.countAvailable():
            countBytesIn = self.countAvailable()

        bytesToStore=countBytesIn

        bytestream = io.BytesIO(data)

        if countBytesIn > 0:
            # chunk input into pages added to the byteQ, might help prevent blocking io
            # might facilitate asynchronous implementation
            debugCount=0
            while True:
                chunk_of_bytes = bytestream.read(4096)
                debugCount+=len(chunk_of_bytes)
                if len(chunk_of_bytes) == 0:
                    break
                self._byteQ.append(MyBytesIO(chunk_of_bytes))
                await asyncio.sleep(0.01) 

            #### reconnect a broken pipe if applicable
            if self._whether_pipe_is_broken():
                self._open_pipe()


        # 2 move any data from queue to top of pipe
        # _log_msg(f"[::write]] topping off pipe", 10)
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
                        
                    self._byteQ.appendleft(first)
            except IndexError:
                break

        if len(data) > 0:
            return len(data[:countBytesIn]) # stub
        else:
            return 0





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

