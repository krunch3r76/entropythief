# pipe_reader
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)

import os
import fcntl
import time
import select
import sys
import io
import threading

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))
from count_bytes_in_pipe import count_bytes_in_pipe

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
        self._lock = threading.Lock()  # Thread safety for file descriptor operations
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
        # Validate input parameter
        if count is None:
            raise ValueError("read() count parameter cannot be None")
        if not isinstance(count, int) or count < 0:
            raise ValueError(f"read() count parameter must be a non-negative integer, got {type(count).__name__}: {count}")
        
        with self._lock:  # Thread-safe file descriptor access
            result = bytearray()
            remainingCount = count

            while remainingCount > 0:
                if not self._whether_pipe_is_readable(0):  # Pure immediate polling - max performance
                    # FIX: Add small sleep to prevent 100% CPU usage when no entropy available
                    time.sleep(0.001)  # 1ms yield to prevent busy-waiting
                    continue
                
                try:
                    _ba = os.read(self._fdPipe, remainingCount)
                except BlockingIOError:
                    _log_msg("pipe reader: BLOCKING ERROR", 5)
                    # FIX: Also yield CPU on blocking errors
                    time.sleep(0.001)  # 1ms yield
                    continue
                except Exception as e:
                    _log_msg(f"Other exception: {e}", 5)
                    # FIX: Yield CPU on other exceptions too
                    time.sleep(0.001)  # 1ms yield
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
    """read entropythief's named pipe into a local buffer with 4KB max read size and greedy buffering

    credits: as of this writing the implementation of this buffering logic
        can be credited almost wholly to chatgpt-4 and from whomever chatgpt-4
        sourced it
    """

    def __init__(self, buffer_size=None, max_read_size=None, greedy_read_size=None):
        super().__init__()
        if buffer_size is None:
            self.buffer_size = 100 * 1024 * 1024  # 100MB default buffer (down from 1GB for efficiency)
        else:
            self.buffer_size = buffer_size
            
        # Optimize defaults for better performance
        if max_read_size is None:
            self.max_read_size = 256 * 1024  # 256KB default (up from 4KB for much better performance)
        else:
            self.max_read_size = max_read_size
        
        # Set default greedy_read_size if None
        if greedy_read_size is None:
            self.greedy_read_size = 256 * 1024  # 256KB default greedy read size (up from 64KB)
        else:
            self.greedy_read_size = greedy_read_size
            
        self.buffer = bytearray(self.buffer_size)
        self.buffer_pos = 0
        self.buffer_end = 0
        
        # Thread safety for buffer operations and statistics
        self._buffer_lock = threading.Lock()
        
        # Stats tracking for performance monitoring
        self._total_requests = 0
        self._total_pipe_reads = 0
        self._total_bytes_requested = 0
        self._total_bytes_read_from_pipe = 0

    def read(self, count):
        with self._buffer_lock:  # Thread-safe buffer and statistics access
            self._total_requests += 1
            self._total_bytes_requested += count
            
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
                
                # GREEDY BUFFERING STRATEGY: Read much more than needed for future requests
                need = count - remaining
                
                # For very small requests (like dice rolls), be maximally greedy
                if need <= 64:  # Small requests like dice rolls (8 bytes) 
                    # Use full greedy read size to dramatically improve efficiency
                    read_amount = self.greedy_read_size
                else:
                    # For larger requests, use normal logic with max_read_size cap
                    read_amount = min(max(need, 4096), self.max_read_size)
                
                    # Safeguard: ensure read_amount is valid
                    if read_amount is None or read_amount <= 0:
                        read_amount = max(need, 4096)  # Fallback to at least what we need or 4KB
                    
                new_data = super().read(read_amount)
                self._total_pipe_reads += 1
                self._total_bytes_read_from_pipe += len(new_data)
                
                # Use memoryview for new_data as well
                result += memoryview(new_data)[:need]
                # Save any excess in the buffer for next time
                remaining_from_new = len(new_data) - need
                if remaining_from_new > 0:
                    self.buffer[:remaining_from_new] = memoryview(new_data)[need:]
                self.buffer_pos = 0
                self.buffer_end = remaining_from_new
                return bytes(result)
    
    def get_efficiency_stats(self) -> dict:
        """Return efficiency statistics for performance monitoring"""
        with self._buffer_lock:  # Thread-safe access to statistics
            if self._total_requests == 0:
                return {
                    "total_requests": 0,
                    "total_pipe_reads": 0,
                    "efficiency_ratio": 0,
                    "average_requests_per_pipe_read": 0,
                    "bytes_requested": 0,
                    "bytes_read_from_pipe": 0,
                    "amplification_factor": 0,
                    "buffer_utilization": f"{self.buffer_end - self.buffer_pos} bytes available"
                }
        
            efficiency_ratio = self._total_requests / max(1, self._total_pipe_reads)
            amplification = self._total_bytes_read_from_pipe / max(1, self._total_bytes_requested)
        
            return {
                "total_requests": self._total_requests,
                "total_pipe_reads": self._total_pipe_reads,
                "efficiency_ratio": efficiency_ratio,
                "average_requests_per_pipe_read": efficiency_ratio,
                "bytes_requested": self._total_bytes_requested,
                "bytes_read_from_pipe": self._total_bytes_read_from_pipe,
                "amplification_factor": amplification,
                "buffer_utilization": f"{self.buffer_end - self.buffer_pos} bytes available",
                "greedy_read_size": f"{self.greedy_read_size} bytes"
            }
