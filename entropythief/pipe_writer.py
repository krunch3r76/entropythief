# pipe_writer
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)

import fcntl
import os, sys
import asyncio
import termios
import json
import io
from functools import singledispatchmethod
import select
import itertools
import functools
import time
from typing import Optional, Union, Any
import logging
import threading

import queue
import collections


_DEBUGLEVEL = (
    int(os.environ["PYTHONDEBUGLEVEL"]) if "PYTHONDEBUGLEVEL" in os.environ else 0
)


# Configure logging for pipe_writer
def _setup_pipe_writer_logging():
    """Set up logging for pipe_writer module with ncurses compatibility"""
    logger = logging.getLogger('pipe_writer')
    
    # Don't add handlers if already configured
    if logger.handlers:
        return logger
    
    # Set log level based on PYTHONDEBUGLEVEL
    if _DEBUGLEVEL >= 3:
        logger.setLevel(logging.DEBUG)
    elif _DEBUGLEVEL >= 2:
        logger.setLevel(logging.INFO)
    elif _DEBUGLEVEL >= 1:
        logger.setLevel(logging.WARNING)
    else:
        logger.setLevel(logging.ERROR)
    
    # Create file handler - primary log file
    log_dir = ".debug"
    log_file = os.path.join(log_dir, "pipe_writer.log")
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_file, mode='a')
    except Exception:
        # Fallback to /tmp if main log directory fails
        fallback_log = f"/tmp/pipe_writer_fallback_{os.getpid()}.log"
        file_handler = logging.FileHandler(fallback_log, mode='a')
    
    # Create formatter with thread information
    formatter = logging.Formatter(
        '[%(asctime)s] [Thread-%(thread)d] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(file_handler)
    
    # Prevent propagation to root logger (avoid any chance of stderr output)
    logger.propagate = False
    
    return logger


# Initialize the logger
_logger = _setup_pipe_writer_logging()


def _log_msg(msg: str, debug_level: int = 0, stream: Optional[Any] = None) -> None:
    """Legacy function for compatibility - now uses standard logging"""
    # Map debug levels to logging levels
    if debug_level <= 0:
        _logger.error(msg)
    elif debug_level == 1:
        _logger.warning(msg)
    elif debug_level == 2:
        _logger.info(msg)
    else:  # debug_level >= 3
        _logger.debug(msg)


# Custom exceptions for pipe writer
class PipeWriterError(Exception):
    """Base exception for pipe writer related errors"""
    pass


class PipeConnectionError(PipeWriterError):
    """Raised when there are issues connecting to or opening the pipe"""
    pass


class PipeWriteError(PipeWriterError):
    """Raised when there are issues writing to the pipe"""
    pass


class PipeConfigurationError(PipeWriterError):
    """Raised when there are pipe configuration issues"""
    pass


##################{}#####################


class MyBytesIO(io.BytesIO):
    """wraps io.BytesIO to behave like a stream"""

    def __init__(self, initial_value: bytes):
        super().__init__(initial_value)
        self.seek(0, io.SEEK_END)
        self.__end = self.tell()
        self.seek(0, io.SEEK_SET)
        self._offset = 0

    @property
    def end(self) -> int:
        return self.__end

    def len(self) -> int:
        # distance from end to current
        return self.__end - self.tell()

    def __len__(self) -> int:
        return self.len()

    def __del__(self) -> None:
        self.close()

    def putback(self, count: int) -> None:
        self.seek(-(count), io.SEEK_CUR)

    def write(self, count: Any) -> None:
        assert False, "MyBytesIO does not support write operation"


####################### {} ########################
class MyBytesDeque(collections.deque):
    """wraps collections.deque to keep track of size of contents"""

    _runningTotal: int = 0

    def __init__(self) -> None:
        super().__init__()

    def append(self, mybytesio: MyBytesIO) -> None:
        assert isinstance(mybytesio, MyBytesIO)
        self._runningTotal += len(mybytesio)
        super().append(mybytesio)

    def insert(self, index: int, mybytesio: MyBytesIO) -> None:
        self._runningTotal += len(mybytesio)
        super().insert(index, mybytesio)

    def appendleft(self, mybytesio: MyBytesIO) -> None:
        self.insert(0, mybytesio)

    def popleft(self) -> MyBytesIO:
        rv = super().popleft()
        self._runningTotal -= len(rv)
        return rv

    def len(self) -> int:
        return self._runningTotal

    def __len__(self) -> int:
        return self.len()

    # def total(self):
    #     return self.len()


def _write_to_pipe(fifoWriteEnd: int, thebytes: bytes, max_retries: int = 10) -> int:
    """writes bytes to a fifo
    required by model__entropythief
    pre: named pipe has been polled for writability -> nonblocking

    fifoWriteEnd: a file descriptor the a named pipe
    thebytes: the bytes to write
    max_retries: maximum number of retry attempts for blocked writes
    """
    # required by: entropythief()
    WRITTEN = 0
    try:
        WRITTEN = os.write(fifoWriteEnd, thebytes)
    except BlockingIOError:
        _log_msg(
            f"_write_to_pipe: BlockingIOError, retrying write of {len(thebytes)} bytes.",
            2,
        )
        for attempt in range(max_retries):
            try:
                WRITTEN = os.write(fifoWriteEnd, thebytes)
                break  # Success, exit retry loop
            except BlockingIOError:
                if attempt == max_retries - 1:  # Last attempt failed
                    raise PipeWriteError(f"Failed to write {len(thebytes)} bytes after {max_retries} attempts due to blocking IO")
                WRITTEN = 0
    except BrokenPipeError as e:
        WRITTEN = 0
        _log_msg("BROKEN PIPE: Reader disconnected", 3)
        raise PipeConnectionError(f"Pipe connection broken: {e}")
    except OSError as e:
        _log_msg(f"_write_to_pipe: OSError during write: {e}", 1)
        raise PipeWriteError(f"OS error during pipe write: {e}")
    except Exception as e:
        _log_msg(f"_write_to_pipe: Unexpected error: {type(e).__name__}: {e}", 0)
        raise PipeWriteError(f"Unexpected error during pipe write: {type(e).__name__}: {e}")
    
    return WRITTEN


##################################{}#########################3
class PipeWriter:
    """writes as much as it can to a named pipe buffering the rest"""

    # Class constants (these are fine to be shared)
    _F_GETPIPE_SZ = 1032
    _F_SETPIPE_SZ = 1031
    
    # Configuration constants
    DEFAULT_CHUNK_SIZE = 4096          # bytes per chunk when queuing data
    DEFAULT_ASYNC_SLEEP = 0.01         # seconds to sleep during async chunking
    DEFAULT_PIPE_CAPACITY = 2**20      # 1 MiB default pipe capacity
    MAX_WRITE_RETRIES = 10             # maximum retry attempts for blocked writes

    def __init__(self, namedPipeFilePathString: str = "/tmp/pilferedbits") -> None:
        """initializes and sets the pipe size to the system's maximum pipe size"""
        _logger.debug("PipeWriter initializing")
        
        # Basic input validation - but don't be too strict
        if not namedPipeFilePathString:
            _logger.warning("Empty pipe path provided, using default")
            namedPipeFilePathString = "/tmp/pilferedbits"
        
        # Initialize instance variables (these should NOT be shared between instances)
        self._byteQ: MyBytesDeque = MyBytesDeque()
        self._fdPipe: Optional[int] = None
        
        self._kNamedPipeFilePathString: str = str(namedPipeFilePathString).strip()
        _logger.debug(f"Using pipe path: {self._kNamedPipeFilePathString}")
        
        try:
            with open("/proc/sys/fs/pipe-max-size", "r") as f:
                self._desired_pipe_capacity: int = int(f.read().strip())
                _logger.debug(f"Read system pipe max size: {self._desired_pipe_capacity}")
        except (FileNotFoundError, PermissionError, ValueError) as e:
            self._desired_pipe_capacity = self.DEFAULT_PIPE_CAPACITY
            _logger.warning(f"Could not read system pipe max size ({e}), using default of {self.DEFAULT_PIPE_CAPACITY}")
        
        # Don't try to open pipe during initialization - let it happen on first write
        _logger.debug("Initialization complete, pipe will be opened on first write")

    @property
    def named_pipe_system_capacity(self) -> int:
        """Return the current system capacity of the named pipe (via F_GETPIPE_SZ)."""
        if self._fdPipe:
            return fcntl.fcntl(self._fdPipe, self._F_GETPIPE_SZ)
        return 0

    def _open_pipe(self) -> None:
        """assigns the pipe to an internal file descriptor if not already set, and sets its size"""
        if not self._fdPipe:
            try:
                _logger.debug(f"Attempting to open pipe: {self._kNamedPipeFilePathString}")
                self._fdPipe = os.open(
                    self._kNamedPipeFilePathString, os.O_WRONLY | os.O_NONBLOCK
                )
                _logger.debug(f"Successfully opened pipe fd: {self._fdPipe}")
                
                # Set the pipe size to the desired value
                try:
                    fcntl.fcntl(self._fdPipe, self._F_SETPIPE_SZ, self._desired_pipe_capacity)
                    _logger.debug(f"Set pipe size to: {self._desired_pipe_capacity}")
                except (OSError, IOError) as e:
                    _logger.warning(f"Failed to set pipe size to {self._desired_pipe_capacity}: {e}")
                    # Continue anyway - pipe size setting is not critical
                # Log the actual pipe size
                try:
                    actual_size = fcntl.fcntl(self._fdPipe, self._F_GETPIPE_SZ)
                    _logger.info(f"Named pipe opened with system capacity: {actual_size} bytes")
                except (OSError, IOError) as e:
                    _logger.warning(f"Could not read pipe capacity: {e}")
            except FileNotFoundError:
                _logger.warning(f"Named pipe not found: {self._kNamedPipeFilePathString}")
                # Don't raise - this might be expected during startup
            except PermissionError as e:
                _logger.warning(f"Permission denied accessing pipe: {self._kNamedPipeFilePathString} - {e}")
                # Don't raise - might be temporary, let caller handle
            except OSError as e:
                if e.errno == 6:  # ENXIO - no reader
                    _logger.debug(f"No reader connected to pipe: {self._kNamedPipeFilePathString}")
                    # Don't raise exception - this is expected when no reader is connected yet
                else:
                    _logger.error(f"OS error opening pipe: {e} (errno: {e.errno})")
                    # For unexpected OS errors, still don't raise - let the system retry
            except Exception as e:
                _logger.error(f"Unexpected error opening pipe: {type(e).__name__}: {e}")
                # Don't raise - unexpected errors should be logged but not break the flow

    def get_bytes_in_pipeline(self) -> int:
        """returns the total number of bytes currently stored in both the pipe and internal buffer"""
        return self.len()

    # -------------------------------------------
    def _whether_pipe_is_broken(self) -> bool:
        """determines if the pipe is still available to be written to"""
        # -------------------------------------------
        answer = False
        # consider a non existing fd as a broken pipe
        if self._fdPipe is None:
            answer = True

        return answer

    # -------------------------------------------
    def _count_bytes_in_pipe(self) -> int:
        """counts how many bytes are currently residing in the named pipe"""
        # -------------------------------------------
        if self._whether_pipe_is_broken():
            return 0

        bytes_in_pipe = 0
        if self._fdPipe:
            try:
                buf = bytearray(4)
                fcntl.ioctl(self._fdPipe, termios.FIONREAD, buf, 1)
                bytes_in_pipe = int.from_bytes(buf, "little")
            except OSError as e:
                _log_msg(f"Failed to read pipe byte count: {e}", 3)
                # Return 0 - if we can't read the count, assume empty
                bytes_in_pipe = 0
            except Exception as e:
                _log_msg(f"Unexpected error reading pipe byte count: {type(e).__name__}: {e}", 1)
                bytes_in_pipe = 0

        return bytes_in_pipe

    # -------------------------------------------
    async def refresh(self) -> None:
        """opens a named pipe if not connected and calls to write any buffered"""
        # -----------------------------------------
        self._open_pipe()
        await self.write(bytearray())

    # -----------------------------------------
    def count_available(self) -> int:
        """computes at a given moment how many bytes could be accepted assuming all asynchronous work is done"""
        # -----------------------------------------
        available = self.named_pipe_system_capacity - self._count_bytes_in_pipe() - self._byteQ.len()

        return available

    # --------------------------------------------
    def len(self) -> int:
        # -----------------------------------------
        """computes the sum of bytes from both the named pipe and internal queued bytechunks"""
        countBytesInPipe = self._count_bytes_in_pipe()
        countBytesInInternalBuffers = self._count_bytes_in_internal_buffers()

        return countBytesInPipe + countBytesInInternalBuffers

    # ----------------------------------------------
    async def write(self, data: Union[bytes, bytearray, memoryview]) -> int:
        """queues/buffers any incoming data then dequeues data to write into named pipe"""
        # Validate input - accept bytes, bytearray, and memoryview (from book.getbuffer())
        if data is not None and not isinstance(data, (bytes, bytearray, memoryview)):
            error_msg = f"Data must be bytes, bytearray, or memoryview, got {type(data).__name__}"
            _log_msg(f"write: Input validation failed: {error_msg}", 1)
            # Don't raise in async context - just log and return 0
            return 0
        
        data_len = len(data) if data else 0
        if data_len > 0:
            _log_msg(f"write: received {data_len} bytes ({type(data).__name__})", 3)
        else:
            _log_msg(f"write: received empty/None data", 3)
            
        try:
            # Queue the incoming data and return the queued amount
            _log_msg(f"write: queuing {data_len} bytes", 3)
            bytes_queued = await self._queue_data(data)
            
            # Attempt to flush queued data to the pipe (but return queued amount)
            _log_msg("write: starting flush to pipe", 3)
            await self._flush_to_pipe()
            _log_msg(f"write: completed, returning {bytes_queued} bytes queued (controller expects queue amount)", 2)
            
            return bytes_queued
        except (PipeWriteError, PipeConnectionError) as e:
            # Log our custom exceptions but don't re-raise in async context
            _log_msg(f"write: Pipe error occurred: {type(e).__name__}: {e}", 3)
            # Return the queued amount even if pipe write failed
            return data_len if data_len > 0 else 0
        except Exception as e:
            # Log unexpected exceptions but don't re-raise in async context  
            _log_msg(f"write: Unexpected error during write operation: {type(e).__name__}: {e}", 0)
            # Return the queued amount even if other errors occurred
            return data_len if data_len > 0 else 0

    async def _queue_data(self, data: Union[bytes, bytearray, memoryview]) -> int:
        """Queue incoming data in chunks for writing to pipe"""
        if not data or len(data) == 0:
            _log_msg("_queue_data: No data to queue", 3)
            return 0
            
        bytes_to_store = len(data)
        _log_msg(f"_queue_data: Queuing {bytes_to_store} bytes in chunks", 3)
        
        # Convert memoryview to bytes for BytesIO
        if isinstance(data, memoryview):
            data = data.tobytes()
        
        bytestream = io.BytesIO(data)
        
        # Chunk input into pages added to the byteQ - helps prevent blocking io
        # and facilitates asynchronous implementation
        chunks_created = 0
        while True:
            chunk_of_bytes = bytestream.read(self.DEFAULT_CHUNK_SIZE)
            if len(chunk_of_bytes) == 0:
                break
            self._byteQ.append(MyBytesIO(chunk_of_bytes))
            chunks_created += 1
            await asyncio.sleep(self.DEFAULT_ASYNC_SLEEP)
            
        _log_msg(f"_queue_data: Created {chunks_created} chunks, total queue size now: {self._byteQ.len()}", 3)
        return bytes_to_store

    async def _flush_to_pipe(self) -> None:
        """Move data from queue to pipe when possible"""
        _log_msg(f"_flush_to_pipe: Starting flush, queue size: {self._byteQ.len()}", 3)
        
        # Reconnect broken pipe if applicable
        if self._whether_pipe_is_broken():
            _log_msg("_flush_to_pipe: Pipe broken, attempting reconnection", 3)
            try:
                self._open_pipe()
                if self._whether_pipe_is_broken():
                    _log_msg("_flush_to_pipe: Reconnection failed, pipe still broken", 3)
                    return
                else:
                    _log_msg("_flush_to_pipe: Reconnection successful", 3)
            except Exception as e:
                # If reconnection fails, don't raise - just log and return
                _log_msg(f"_flush_to_pipe: Exception during reconnection: {type(e).__name__}: {e}", 1)
                return
            
        # Move data from queue to pipe
        available_in_pipe = self._count_available_in_pipe()
        blocked = False
        
        _log_msg(f"_flush_to_pipe: Available space in pipe: {available_in_pipe}", 3)
        
        while available_in_pipe > 0 and not blocked and self._byteQ.len() > 0:
            try:
                first = self._byteQ.popleft()
                _log_msg(f"_flush_to_pipe: Processing chunk of {first.len()} bytes", 3)
                
                if first.len() <= available_in_pipe:
                    try:
                        written = _write_to_pipe(self._fdPipe, first.getbuffer(), self.MAX_WRITE_RETRIES)
                        if written == 0:
                            blocked = True
                            self._byteQ.appendleft(first)
                            _log_msg("_flush_to_pipe: Write blocked, requeuing chunk", 3)
                        else:
                            _log_msg(f"_flush_to_pipe: Wrote {written} bytes (full chunk)", 3)
                            available_in_pipe -= written
                    except (PipeWriteError, PipeConnectionError) as e:
                        _log_msg(f"_flush_to_pipe: Pipe write failed (full): {e}", 3)
                        self._byteQ.appendleft(first)
                        # Mark pipe as broken but don't raise - just log and continue
                        self._fdPipe = None
                        break
                    except Exception as e:
                        _log_msg(f"_flush_to_pipe: Unexpected error in write (full): {type(e).__name__}: {e}", 0)
                        self._byteQ.appendleft(first)
                        # Don't raise - log and continue
                        break
                else:  # len(first) > available_in_pipe
                    frame = first.read(available_in_pipe)
                    try:
                        written = _write_to_pipe(self._fdPipe, frame[:available_in_pipe], self.MAX_WRITE_RETRIES)
                        if written == 0:
                            blocked = True
                            first.putback(available_in_pipe)
                            self._byteQ.appendleft(first)
                            _log_msg("_flush_to_pipe: Partial write blocked, putting back data", 2)
                        else:
                            _log_msg(f"_flush_to_pipe: Wrote {written} bytes (partial chunk)", 3)
                            if written < available_in_pipe:
                                # Partial write - put back the unwritten portion
                                first.putback(available_in_pipe - written)
                            self._byteQ.appendleft(first)
                            available_in_pipe = 0  # Used all or blocked
                    except (PipeWriteError, PipeConnectionError) as e:
                        _log_msg(f"_flush_to_pipe: Pipe write failed (partial): {e}", 1)
                        first.putback(available_in_pipe)
                        self._byteQ.appendleft(first)
                        # Mark pipe as broken but don't raise - just log and continue
                        self._fdPipe = None
                        break
                    except Exception as e:
                        _log_msg(f"_flush_to_pipe: Unexpected error in write (partial): {type(e).__name__}: {e}", 0)
                        first.putback(available_in_pipe)
                        self._byteQ.appendleft(first)
                        # Don't raise - log and continue
                        break
            except IndexError:
                _log_msg("_flush_to_pipe: Queue empty", 3)
                break  # Queue is empty
            except Exception as e:
                _log_msg(f"_flush_to_pipe: Unexpected error in main loop: {type(e).__name__}: {e}", 0)
                # Don't raise - log and continue
                break
                
        _log_msg(f"_flush_to_pipe: Completed flush", 3)

    # -----------------------------------------
    def _count_bytes_in_internal_buffers(self) -> int:
        # -----------------------------------------
        """Return the total bytes currently in internal buffer queue"""
        return self._byteQ.len()

    def _count_available_in_pipe(self) -> int:
        """Count how many bytes can be written to the pipe right now"""
        if self._fdPipe:
            bytes_in_pipe = self._count_bytes_in_pipe()
            return self.named_pipe_system_capacity - bytes_in_pipe
        else:
            return 0

    # -------------------------------------------
    def __repr__(self) -> str:
        # -------------------------------------------
        output = f"""
max capacity: {self.named_pipe_system_capacity}
bytes in pipe: {self._count_bytes_in_pipe()}
bytes in internal buffers: {self._count_bytes_in_internal_buffers()}
total available: {self.count_available()}
total bytes: {self._count_bytes_in_internal_buffers() + self._count_bytes_in_pipe()}
"""
        return output

    # -----------------------------------------
    def close(self) -> None:
        """Close the writer's file descriptor to the pipe (but not the pipe itself)"""
        if self._fdPipe is not None:
            try:
                os.close(self._fdPipe)
                _logger.debug(f"Closed writer's file descriptor {self._fdPipe}")
            except OSError as e:
                _logger.warning(f"Error closing writer's fd {self._fdPipe}: {e}")
                # Don't raise - closing is best effort, and fd might already be closed
            except Exception as e:
                _logger.error(f"Unexpected error closing fd {self._fdPipe}: {type(e).__name__}: {e}")
                # Don't raise - cleanup should be resilient
            finally:
                self._fdPipe = None

    def __enter__(self) -> 'PipeWriter':
        """Context manager entry"""
        return self

    def __exit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[Any]) -> bool:
        """Context manager exit - pipe connection management is external responsibility"""
        return False  # Don't suppress exceptions

    def __del__(self) -> None:
        """PipeWriter doesn't auto-close since it doesn't manage pipe lifecycle"""
        pass
