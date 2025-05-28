# pipe_reader
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)

import os
import json
import fcntl
import termios
import time
import select
import sys
import io

from utils.count_bytes_in_pipe import count_bytes_in_pipe

_DEBUGLEVEL = (
    int(os.environ["PYTHONDEBUGLEVEL"]) if "PYTHONDEBUGLEVEL" in os.environ else 0
)


def _log_msg(msg, debug_level=1, file_=sys.stderr):
    pass
    if debug_level <= _DEBUGLEVEL:
        print(msg, file=file_)


# ******************{}********************
class _PipeReader:
    # ******************{}********************
    """
    create an interface to read from entropythief's designated named pipe

    recreates pipe if needed (note, if another user runs this it will
    require changing permissions so entropythief can write to it) REVIEW

    methods:
        read(count): return count number of bytes as type bytes
    """
    _kNamedPipeFilePathString = "/tmp/pilferedbits"
    _F_SETPIPE_SZ = 1031  # opcode for fnctl to setpipe size

    # --------------------------------------
    def __init__(self):
        # --------------------------------------
        """set up interface to pipe, open, and populate attributes

        post:
            _fdPipe : file descriptor to opened named pipe
            _fdPoll : poll object with which to monitor pipe

            _fdPipe is None if not available at time of initialization

        notes: the named pipe open is the constant self._kNamedPipeFilePathString
        """
        self._fdPipe = None
        self._fdPoll = select.poll()
        self._open_pipe()

    # .......................
    def _open_pipe(self):
        """try to open the named pipe for reading

        pre: _fdPoll is unregistered of previous pipe (weak)
        in: none
        out: none
        post:
            _fdPipe : descriptor to current or newly created named pipe
            _fdPoll : registered with newly opened pipe

            notes:
            named pipe created if needed and pipe size set to 1mb,
             register pipe with internal poll object
        """
        # .......................
        _log_msg("opening pipe", 5)
        if not os.path.exists(self._kNamedPipeFilePathString):
            os.mkfifo(self._kNamedPipeFilePathString)
        self._fdPipe = os.open(
            self._kNamedPipeFilePathString, os.O_RDONLY | os.O_NONBLOCK
        )
        fcntl.fcntl(self._fdPipe, self._F_SETPIPE_SZ, 2**20)
        self._fdPoll.register(self._fdPipe)
        _log_msg("opened pipe", 5)

    # ........................................
    def _reopen_pipe(self):
        # ........................................
        """close pipe if applicable and open

        pre: none
        in: none
        out: none
        post: _fdPipe (None if failed to open)
        """
        if self._fdPipe:
            try:
                os.close(self._fdPipe)
            except OSError:
                pass
            self._fdPoll.unregister(self._fdPipe)
            self._fdPipe = None
        self._open_pipe()

    # ........................................
    def _whether_pipe_is_readable(self) -> bool:
        # ........................................
        """indicate whether the pipe is currently readable

        pre: none
        in: none
        out: True or False
        post: none
        """
        answer = False
        if self._fdPipe is None:
            answer = False
        else:
            pl = self._fdPoll.poll(0)
            if len(pl) == 1:
                if pl[0][1] & 1:
                    answer = True
        return answer

    # continuously read pipes until read count satisfied, then return the read count
    # revision shall asynchronously read the pipe and deliver in chunks
    # -------------------------------------------
    def read(self, count) -> bytes:
        # -------------------------------------------
        """ read from pipe until count number and return
        pre: None
        in:
            - count: the number of bytes to read and return
        post: None
        out:
            /bytes/ of length \count\
        """
        byte_stream = io.BytesIO()
        remainingCount = count
        while remainingCount > 0:
            bytesInCurrentPipe = count_bytes_in_pipe(self._fdPipe)
            if bytesInCurrentPipe >= remainingCount:
                try:
                    _ba = os.read(self._fdPipe, remainingCount)
                except BlockingIOError:
                    _log_msg("pipe reader: BLOCKING ERROR", 5)
                    pass
                except Exception as e:
                    _log_msg(f"Other exception: {e}", 5)
                else:
                    remainingCount -= len(_ba)
                    byte_stream.write(_ba)
                    # print(f"remainingCount is {remainingCount}")
            elif bytesInCurrentPipe > 0:
                try:
                    _ba = os.read(self._fdPipe, bytesInCurrentPipe)
                except BlockingIOError:
                    _log_msg("blocking io error", 5)
                    pass
                except Exception as e:
                    _log_msg(f"Other exception: {e}", 5)
                    # self._reopen_pipe()
                else:
                    remainingCount -= len(_ba)
                    byte_stream.write(_ba)

            time.sleep(0.01)
        # print(f"read returning {len(byte_stream.getbuffer() )}")
        return byte_stream.getvalue()

    # potential issues
    # undefined behavior if named pipe is deleted elsewhere

    # -------------------------------------------
    def __del__(self):
        # -------------------------------------------
        # for now, the reader will destroy anything remaining in the pipe
        os.close(self._fdPipe)
        # os.unlink(self._kNamedPipeFilePathString) # unlinking the named pipe will mean the writer will not be seen next time
        # maybe the writer should be unlinking it when done?


import io


class PipeReader(_PipeReader):
    """read entropythief's named pipe into a local before


    credits: as of this writing the implementation of this buffering logic
        can be credited almost wholly to chatgpt-4 and from whomever chatgpt-4
        sourced it
    """

    def __init__(self, buffer_size=None):
        super().__init__()
        if buffer_size is None:
            self.buffer_size = 4096
        else:
            self.buffer_size = buffer_size
        self.buffer = bytearray(self.buffer_size)
        self.buffer_pos = 0
        self.buffer_end = 0

    def read(self, count):
        remaining = self.buffer_end - self.buffer_pos
        if remaining >= count:
            # We have enough data in the buffer
            result = self.buffer[self.buffer_pos : self.buffer_pos + count]
            self.buffer_pos += count
        else:
            # Not enough data in the buffer, need to refill
            result = self.buffer[
                self.buffer_pos : self.buffer_end
            ]  # take remaining data
            new_data = super().read(
                max(self.buffer_size, count - remaining)
            )  # get more data
            result += new_data[
                : count - remaining
            ]  # append required amount to the result

            # Put the rest of the new data (if any) in the buffer
            remaining_from_new = len(new_data) - (count - remaining)
            self.buffer[:remaining_from_new] = new_data[
                count - remaining :
            ]  # move the rest to the beginning of the buffer
            self.buffer_pos = 0
            self.buffer_end = remaining_from_new

        return result
