# pipe_reader
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)

import os
import fcntl
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

        notes: the named pipe open is the constant self._kNamedPipeFilePathString
        """
        self._fdPipe = None
        self._open_pipe()

    # .......................
    def _open_pipe(self):
        """try to open the named pipe for reading

        pre: none
        in: none
        out: none
        post:
            _fdPipe : descriptor to current or newly created named pipe

            notes:
            named pipe created if needed and pipe size set to 1mb
        """
        _log_msg("opening pipe", 5)
        if not os.path.exists(self._kNamedPipeFilePathString):
            os.mkfifo(self._kNamedPipeFilePathString)
        self._fdPipe = os.open(
            self._kNamedPipeFilePathString, os.O_RDONLY | os.O_NONBLOCK
        )
        fcntl.fcntl(self._fdPipe, self._F_SETPIPE_SZ, 2**20)
        _log_msg("opened pipe", 5)

    # ........................................
    def _reopen_pipe(self):
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
            self._fdPipe = None
        self._open_pipe()

    def _whether_pipe_is_readable(self, timeout_ms=0) -> bool:
        """Check if pipe is readable, waiting up to timeout_ms milliseconds"""
        if self._fdPipe is None:
            return False
        
        # Convert milliseconds to seconds for select
        timeout_seconds = timeout_ms / 1000.0
        
        # Use select.select() instead of poll() - avoids concurrency issues
        rlist, _, _ = select.select([self._fdPipe], [], [], timeout_seconds)
        return bool(rlist)

    # continuously read pipes until read count satisfied, then return the read count
    # revision shall asynchronously read the pipe and deliver in chunks
    # -------------------------------------------

    def read(self, count) -> bytes:
        result = bytearray()
        remainingCount = count

        while remainingCount > 0:
            if not self._whether_pipe_is_readable(0):  # Pure immediate polling - max performance
                continue
            
            try:
                _ba = os.read(self._fdPipe, remainingCount)
            except BlockingIOError:
                _log_msg("pipe reader: BLOCKING ERROR", 5)
                continue
            except Exception as e:
                _log_msg(f"Other exception: {e}", 5)
                continue
            else:
                if not _ba:
                    break  # EOF reached
                remainingCount -= len(_ba)
                result.extend(_ba)
        return bytes(result)


    # potential issues
    # undefined behavior if named pipe is deleted elsewhere

    # -------------------------------------------
    def __del__(self):
        # -------------------------------------------
        """close the pipe when the object is destroyed

        pre: none
        in: none
        out: none
        post: _fdPipe is closed
        """
        try:
            if self._fdPipe is not None:
                os.close(self._fdPipe)
        except Exception:
            pass



import io


class PipeReader(_PipeReader):
    """read entropythief's named pipe into a local buffer with 4KB max read size

    credits: as of this writing the implementation of this buffering logic
        can be credited almost wholly to chatgpt-4 and from whomever chatgpt-4
        sourced it
    """

    def __init__(self, buffer_size=None, max_read_size=4096):
        super().__init__()
        if buffer_size is None:
            self.buffer_size = 2**30  # 1GB default buffer
        else:
            self.buffer_size = buffer_size
        self.max_read_size = max_read_size  # 4KB default max read - matches pipe page size
        self.buffer = bytearray(self.buffer_size)
        self.buffer_pos = 0
        self.buffer_end = 0

    def read(self, count):
        remaining = self.buffer_end - self.buffer_pos
        if remaining >= count:
            # Use memoryview to avoid extra copy
            result_mv = memoryview(self.buffer)[self.buffer_pos : self.buffer_pos + count]
            self.buffer_pos += count
            return bytes(result_mv)  # Ensure return type is bytes
        else:
            # Not enough data in the buffer, need to refill
            result = bytearray()
            if remaining > 0:
                # Use memoryview for the buffer slice
                result += memoryview(self.buffer)[self.buffer_pos : self.buffer_end]
            
            # KEY FIX: Cap read size to max_read_size (4KB) instead of entire buffer
            need = count - remaining
            read_amount = min(max(need, 4096), self.max_read_size)  # 4KB minimum, 4KB maximum
            new_data = super().read(read_amount)
            
            # Use memoryview for new_data as well
            result += memoryview(new_data)[:need]
            # Save any excess in the buffer for next time
            remaining_from_new = len(new_data) - need
            if remaining_from_new > 0:
                self.buffer[:remaining_from_new] = memoryview(new_data)[need:]
            self.buffer_pos = 0
            self.buffer_end = remaining_from_new
            return bytes(result)
