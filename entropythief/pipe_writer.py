# pipe_writer
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)

"""
Advanced pipe writer for named pipes with buffering, caching, and configurable performance.

Usage Examples:
    # Default configuration (optimized for performance)
    writer = PipeWriter("/tmp/myfifo")
    
    # High-performance configuration
    config = PipeWriterConfig.high_performance()
    writer = PipeWriter("/tmp/myfifo", config=config)
    
    # Rate-limited configuration (intentional throttling)
    config = PipeWriterConfig.rate_limited(delay_seconds=0.01)
    writer = PipeWriter("/tmp/myfifo", config=config)
    
    # Custom configuration
    custom_config = PipeWriterConfig(
        chunk_size=8192,
        async_sleep=0,        # No delays for maximum performance
        max_write_retries=20
    )
    writer = PipeWriter("/tmp/myfifo", config=custom_config)
    
    # Using as context manager
    with PipeWriter("/tmp/myfifo") as writer:
        await writer.write(b"some data")
"""

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


# Configuration class for centralized settings
class PipeWriterConfig:
    """Centralized configuration for PipeWriter performance and behavior settings"""
    
    def __init__(self,
                 chunk_size: int = 4096,
                 async_sleep: float = 0,
                 default_pipe_capacity: int = 2**20,
                 max_write_retries: int = 10,
                 cache_ttl: float = 0.001,
                 chunks_per_yield: int = 8):
        """Initialize PipeWriter configuration
        
        Args:
            chunk_size: Size in bytes for data chunking (default: 4096)
            async_sleep: Sleep time in seconds during async operations (default: 0)
                        0 = pure yielding without delay (recommended for performance)
                        >0 = intentional delay for rate limiting or resource sharing
            default_pipe_capacity: Default pipe capacity in bytes (default: 1MiB)
            max_write_retries: Maximum retry attempts for blocked writes (default: 10)
            cache_ttl: Cache TTL in seconds for pipe byte count (default: 0.001)
            chunks_per_yield: Number of chunks to process before yielding (default: 8)
        """
        # Validate configuration parameters
        if chunk_size <= 0:
            raise PipeConfigurationError(f"chunk_size must be positive, got {chunk_size}")
        if async_sleep < 0:
            raise PipeConfigurationError(f"async_sleep must be non-negative, got {async_sleep}")
        if default_pipe_capacity <= 0:
            raise PipeConfigurationError(f"default_pipe_capacity must be positive, got {default_pipe_capacity}")
        if max_write_retries < 0:
            raise PipeConfigurationError(f"max_write_retries must be non-negative, got {max_write_retries}")
        if cache_ttl < 0:
            raise PipeConfigurationError(f"cache_ttl must be non-negative, got {cache_ttl}")
        if chunks_per_yield <= 0:
            raise PipeConfigurationError(f"chunks_per_yield must be positive, got {chunks_per_yield}")
            
        self.chunk_size = chunk_size
        self.async_sleep = async_sleep
        self.default_pipe_capacity = default_pipe_capacity
        self.max_write_retries = max_write_retries
        self.cache_ttl = cache_ttl
        self.chunks_per_yield = chunks_per_yield
        
        # fcntl constants (these don't change)
        self.F_GETPIPE_SZ = 1032
        self.F_SETPIPE_SZ = 1031
    
    @classmethod
    def default(cls) -> 'PipeWriterConfig':
        """Create a default configuration"""
        return cls()
    
    @classmethod  
    def high_performance(cls) -> 'PipeWriterConfig':
        """Create a high-performance configuration"""
        return cls(
            chunk_size=8192,      # Larger chunks
            async_sleep=0,        # No artificial delays
            cache_ttl=0.002,      # Longer cache TTL
            chunks_per_yield=16   # More chunks per yield
        )
    
    @classmethod
    def low_latency(cls) -> 'PipeWriterConfig':
        """Create a low-latency configuration"""
        return cls(
            chunk_size=1024,      # Smaller chunks for responsiveness
            async_sleep=0,        # No artificial delays
            cache_ttl=0.0005,     # Shorter cache TTL
            chunks_per_yield=4    # Fewer chunks per yield
        )
    
    @classmethod
    def rate_limited(cls, delay_seconds: float = 0.01) -> 'PipeWriterConfig':
        """Create a rate-limited configuration with intentional delays
        
        Args:
            delay_seconds: Intentional delay between chunk batches for rate limiting
        """
        return cls(
            async_sleep=delay_seconds,  # Intentional delay for rate limiting
            chunks_per_yield=4          # Smaller batches with delays
        )
    
    def __repr__(self) -> str:
        return (f"PipeWriterConfig(chunk_size={self.chunk_size}, "
                f"async_sleep={self.async_sleep}, "
                f"default_pipe_capacity={self.default_pipe_capacity}, "
                f"max_write_retries={self.max_write_retries}, "
                f"cache_ttl={self.cache_ttl}, "
                f"chunks_per_yield={self.chunks_per_yield})")


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

    def __init__(self) -> None:
        super().__init__()
        # Instance variable - each MyBytesDeque has its own running total
        self._runningTotal: int = 0

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

    def __init__(self, 
                 namedPipeFilePathString: str = "/tmp/pilferedbits",
                 config: Optional[PipeWriterConfig] = None) -> None:
        """initializes and sets the pipe size to the system's maximum pipe size"""
        _logger.debug("PipeWriter initializing")
        
        # Initialize configuration
        self.config = config if config is not None else PipeWriterConfig.default()
        _logger.debug(f"Using configuration: {self.config}")
        
        # Basic input validation - but don't be too strict
        if not namedPipeFilePathString:
            _logger.warning("Empty pipe path provided, using default")
            namedPipeFilePathString = "/tmp/pilferedbits"
        
        # Initialize instance variables (these should NOT be shared between instances)
        self._byteQ: MyBytesDeque = MyBytesDeque()
        self._fdPipe: Optional[int] = None
        
        # Performance optimization: cache expensive system calls
        self._cached_pipe_capacity: Optional[int] = None
        self._cached_bytes_in_pipe: Optional[int] = None
        self._cache_timestamp: float = 0.0
        
        self._kNamedPipeFilePathString: str = str(namedPipeFilePathString).strip()
        _logger.debug(f"Using pipe path: {self._kNamedPipeFilePathString}")
        
        try:
            with open("/proc/sys/fs/pipe-max-size", "r") as f:
                self._desired_pipe_capacity: int = int(f.read().strip())
                _logger.debug(f"Read system pipe max size: {self._desired_pipe_capacity}")
        except (FileNotFoundError, PermissionError, ValueError) as e:
            self._desired_pipe_capacity = self.config.default_pipe_capacity
            _logger.warning(f"Could not read system pipe max size ({e}), using config default of {self.config.default_pipe_capacity}")
        
        # Don't try to open pipe during initialization - let it happen on first write
        _logger.debug("Initialization complete, pipe will be opened on first write")

    @property
    def named_pipe_system_capacity(self) -> int:
        """Return the current system capacity of the named pipe (via F_GETPIPE_SZ)."""
        if not self._fdPipe:
            return 0
            
        # Use cached value if available (pipe capacity rarely changes)
        if self._cached_pipe_capacity is not None:
            return self._cached_pipe_capacity
            
        try:
            self._cached_pipe_capacity = fcntl.fcntl(self._fdPipe, self.config.F_GETPIPE_SZ)
            return self._cached_pipe_capacity
        except (OSError, IOError) as e:
            _logger.debug(f"Failed to read pipe capacity: {e}")
            return 0

    def _invalidate_cache(self) -> None:
        """Invalidate cached values when pipe state changes"""
        self._cached_pipe_capacity = None
        self._cached_bytes_in_pipe = None
        self._cache_timestamp = 0.0

    def _open_pipe(self) -> None:
        """assigns the pipe to an internal file descriptor if not already set, and sets its size"""
        if self._fdPipe is not None:
            # Pipe is already open, don't open again
            _logger.debug(f"Pipe already open with fd: {self._fdPipe}")
            return
            
        try:
            _logger.debug(f"Attempting to open pipe: {self._kNamedPipeFilePathString}")
            fd = os.open(
                self._kNamedPipeFilePathString, os.O_WRONLY | os.O_NONBLOCK
            )
            _logger.debug(f"Successfully opened pipe fd: {fd}")
            
            try:
                # Set the pipe size to the desired value
                try:
                    fcntl.fcntl(fd, self.config.F_SETPIPE_SZ, self._desired_pipe_capacity)
                    _logger.debug(f"Set pipe size to: {self._desired_pipe_capacity}")
                except (OSError, IOError) as e:
                    _logger.warning(f"Failed to set pipe size to {self._desired_pipe_capacity}: {e}")
                    # Continue anyway - pipe size setting is not critical
                
                # Log the actual pipe size
                try:
                    actual_size = fcntl.fcntl(fd, self.config.F_GETPIPE_SZ)
                    _logger.info(f"Named pipe opened with system capacity: {actual_size} bytes")
                except (OSError, IOError) as e:
                    _logger.warning(f"Could not read pipe capacity: {e}")
                
                # Only assign to self._fdPipe after all operations succeed
                self._fdPipe = fd
                # Invalidate cache when pipe opens successfully
                self._invalidate_cache()
                # Cache the capacity if we successfully read it
                if 'actual_size' in locals():
                    self._cached_pipe_capacity = actual_size
                    
            except Exception as setup_error:
                # If setup fails after opening, clean up the file descriptor
                try:
                    os.close(fd)
                    _logger.debug(f"Cleaned up fd {fd} after setup failure")
                except OSError as close_error:
                    _logger.warning(f"Failed to close fd {fd} during cleanup: {close_error}")
                raise setup_error
                
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

        # Validate file descriptor before using it
        if not self.is_fd_valid():
            _logger.debug("Invalid file descriptor detected, marking pipe as broken")
            return 0

        # Use cached value if within TTL (avoid redundant expensive ioctl calls)
        current_time = time.time()
        if (self._cached_bytes_in_pipe is not None and 
            current_time - self._cache_timestamp < self.config.cache_ttl):
            return self._cached_bytes_in_pipe

        bytes_in_pipe = 0
        try:
            buf = bytearray(4)
            fcntl.ioctl(self._fdPipe, termios.FIONREAD, buf, 1)
            bytes_in_pipe = int.from_bytes(buf, "little")
            
            # Cache the result
            self._cached_bytes_in_pipe = bytes_in_pipe
            self._cache_timestamp = current_time
            
        except OSError as e:
            _log_msg(f"Failed to read pipe byte count: {e}", 3)
            # Return 0 - if we can't read the count, assume empty
            bytes_in_pipe = 0
            # Invalidate cache and mark pipe as broken on error
            self._cached_bytes_in_pipe = None
            if e.errno == 9:  # EBADF - Bad file descriptor
                _logger.warning(f"Bad file descriptor {self._fdPipe}, marking as broken")
                self._fdPipe = None
                self._invalidate_cache()
        except Exception as e:
            _log_msg(f"Unexpected error reading pipe byte count: {type(e).__name__}: {e}", 1)
            bytes_in_pipe = 0
            # Invalidate cache on error
            self._cached_bytes_in_pipe = None

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
        
        # Optimized chunking: batch multiple chunks before yielding control
        # This reduces async overhead significantly
        chunks_created = 0
        chunks_per_yield = self.config.chunks_per_yield  # Use config value
        
        while True:
            chunk_batch = 0
            
            # Process a batch of chunks without yielding
            while chunk_batch < chunks_per_yield:
                chunk_of_bytes = bytestream.read(self.config.chunk_size)
                if len(chunk_of_bytes) == 0:
                    break  # End of data
                    
                self._byteQ.append(MyBytesIO(chunk_of_bytes))
                chunks_created += 1
                chunk_batch += 1
            
            # If we processed no chunks in this batch, we're done
            if chunk_batch == 0:
                break
                
            # Yield control to other async tasks
            if self.config.async_sleep > 0:
                # Intentional delay for rate limiting
                await asyncio.sleep(self.config.async_sleep)
            else:
                # Pure yielding without delay (cooperative multitasking)
                await asyncio.sleep(0)
            
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
                        written = _write_to_pipe(self._fdPipe, first.getbuffer(), self.config.max_write_retries)
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
                        self._invalidate_cache()  # Invalidate cache when pipe breaks
                        break
                    except Exception as e:
                        _log_msg(f"_flush_to_pipe: Unexpected error in write (full): {type(e).__name__}: {e}", 0)
                        self._byteQ.appendleft(first)
                        # Don't raise - log and continue
                        break
                else:  # len(first) > available_in_pipe
                    frame = first.read(available_in_pipe)
                    try:
                        written = _write_to_pipe(self._fdPipe, frame[:available_in_pipe], self.config.max_write_retries)
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
                        self._invalidate_cache()  # Invalidate cache when pipe breaks
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
                # Invalidate cache when pipe closes
                self._invalidate_cache()

    def __enter__(self) -> 'PipeWriter':
        """Context manager entry"""
        return self

    def __exit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[Any]) -> bool:
        """Context manager exit - close pipe to prevent leaks"""
        # Always close on context exit to prevent leaks
        self.close()
        return False  # Don't suppress exceptions
    
    @classmethod
    def get_open_fd_count(cls) -> int:
        """Get the current number of open file descriptors for this process (Linux only)"""
        try:
            import glob
            fd_count = len(glob.glob('/proc/self/fd/*'))
            return fd_count
        except Exception:
            return -1  # Unable to determine
    
    def is_fd_valid(self) -> bool:
        """Check if the current file descriptor is still valid"""
        if self._fdPipe is None:
            return False
        try:
            # Try to get file status - will fail if fd is invalid
            os.fstat(self._fdPipe)
            return True
        except (OSError, ValueError):
            # File descriptor is invalid
            self._fdPipe = None
            self._invalidate_cache()
            return False

    def __del__(self) -> None:
        """Automatic cleanup of file descriptors to prevent leaks"""
        if self._fdPipe is not None:
            try:
                os.close(self._fdPipe)
                _logger.debug(f"Auto-closed leaked fd {self._fdPipe} in __del__")
            except OSError:
                # File descriptor may already be closed
                pass
            except Exception as e:
                # Log but don't raise in destructor
                _logger.warning(f"Error in __del__ cleanup: {type(e).__name__}: {e}")
            finally:
                self._fdPipe = None

    def get_fd_info(self) -> dict:
        """Get diagnostic information about file descriptor usage"""
        info = {
            'current_fd': self._fdPipe,
            'fd_valid': self.is_fd_valid() if self._fdPipe is not None else False,
            'pipe_path': self._kNamedPipeFilePathString,
            'process_fd_count': self.get_open_fd_count(),
            'cache_valid': self._cached_bytes_in_pipe is not None,
            'cache_age': time.time() - self._cache_timestamp if self._cache_timestamp > 0 else -1
        }
        
        # Try to get system limits
        try:
            import resource
            soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
            info['fd_soft_limit'] = soft_limit
            info['fd_hard_limit'] = hard_limit
        except Exception:
            info['fd_soft_limit'] = -1
            info['fd_hard_limit'] = -1
            
        return info
