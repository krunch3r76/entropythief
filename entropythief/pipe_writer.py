# pipe_writer
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)

"""
Optimized PipeWriter with vectored I/O and intelligent buffering.

Key optimizations:
1. Vectored I/O (os.writev) for efficient writing
2. Intelligent pipe capacity management
3. 4KB chunking with deque buffering
4. Async yielding to prevent blocking
5. Proper partial write recovery
"""

import os
import fcntl
import asyncio
import termios
import io
import collections
import time
import logging
from typing import Optional, Union
import multiprocessing
import queue
import sys


_DEBUGLEVEL = (
    int(os.environ["PYTHONDEBUGLEVEL"]) if "PYTHONDEBUGLEVEL" in os.environ else 0
)


# Configure file-based logging for pipe_writer (NO stderr output)
def _setup_pipe_writer_logging():
    """Set up file-based logging for pipe_writer module"""
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
    
    # Create file handler - write to .logs/pipewriter.log
    log_dir = ".logs"
    log_file = os.path.join(log_dir, "pipewriter.log")
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_file, mode='w')  # Clear file on each run
    except Exception:
        # Fallback to /tmp if main log directory fails
        fallback_log = f"/tmp/pipe_writer_fallback_{os.getpid()}.log"
        file_handler = logging.FileHandler(fallback_log, mode='w')  # Clear file on each run
    
    # Create formatter with thread information
    formatter = logging.Formatter(
        '[%(asctime)s] [Thread-%(thread)d] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(file_handler)
    
    # Prevent propagation to root logger (avoid any stderr output)
    logger.propagate = False
    
    # Log session start
    logger.info("=== PipeWriter Session Started ===")
    
    return logger


# Initialize the logger
_logger = _setup_pipe_writer_logging()


def _log_msg(msg: str, debug_level: int = 0) -> None:
    """File-based logging function - NO stderr output"""
    # Map debug levels to logging levels
    if debug_level <= 0:
        _logger.error(msg)
    elif debug_level == 1:
        _logger.warning(msg)
    elif debug_level == 2:
        _logger.info(msg)
    else:  # debug_level >= 3
        _logger.debug(msg)


def log_exception(e: Exception, location: str) -> None:
    """Log exception details to file with context"""
    _logger.error(f"Exception in {location}: {type(e).__name__}: {e}")


class OptimizedBytesIO(io.BytesIO):
    """Optimized BytesIO wrapper for efficient streaming"""
    
    def __init__(self, initial_value: Union[bytes, bytearray, memoryview]):
        if not isinstance(initial_value, (bytes, bytearray, memoryview)):
            raise TypeError(f"Expected bytes-like object, got {type(initial_value).__name__}")
        
        super().__init__(initial_value)
        self.seek(0, io.SEEK_END)
        self.__end = self.tell()
        self.seek(0, io.SEEK_SET)
    
    @property
    def end(self) -> int:
        return self.__end
    
    def len(self) -> int:
        return self.__end - self.tell()
    
    def __len__(self) -> int:
        return self.len()
    
    def putback(self, count: int) -> None:
        """Move read position back by count bytes"""
        self.seek(-count, io.SEEK_CUR)


class OptimizedBytesDeque(collections.deque):
    """Deque with running total tracking for efficient length calculation"""
    
    def __init__(self):
        super().__init__()
        self._running_total = 0
    
    def append(self, bytes_io: OptimizedBytesIO) -> None:
        if not isinstance(bytes_io, OptimizedBytesIO):
            raise TypeError("Expected OptimizedBytesIO object")
        self._running_total += len(bytes_io)
        super().append(bytes_io)
    
    def appendleft(self, bytes_io: OptimizedBytesIO) -> None:
        if not isinstance(bytes_io, OptimizedBytesIO):
            raise TypeError("Expected OptimizedBytesIO object")
        self._running_total += len(bytes_io)
        super().appendleft(bytes_io)
    
    def popleft(self) -> OptimizedBytesIO:
        rv = super().popleft()
        self._running_total -= len(rv)
        return rv
    
    def clear(self) -> None:
        """Clear all items and reset running total"""
        super().clear()
        self._running_total = 0
    
    def len(self) -> int:
        return max(0, self._running_total)
    
    def __len__(self) -> int:
        return self.len()


class PipeWriter:
    """High-performance pipe writer using vectored I/O and intelligent buffering"""
    
    def __init__(self, namedPipeFilePathString: str = "/tmp/pilferedbits", 
                 chunk_size: int = 2097152, target_capacity: int = None):
        """Initialize PipeWriter with optimized settings
        
        Args:
            namedPipeFilePathString: Path to the named pipe
            chunk_size: Size of chunks for buffering (default 2MB for optimal pipe writing)
            target_capacity: Target capacity limit for total buffered data (pipe + internal)
                           If None, no capacity enforcement is applied
        """
        self._kNamedPipeFilePathString = namedPipeFilePathString
        self.chunk_size = chunk_size
        self._fdPipe: Optional[int] = None
        self._byteQ = OptimizedBytesDeque()
        
        # CAPACITY ENFORCEMENT: Add target capacity tracking
        self._target_capacity = target_capacity
        self._enforce_capacity = target_capacity is not None
        
        # BUFFER MANAGEMENT: Disable stale data cleanup to allow buffer accumulation
        self._buffer_timeout = float('inf')  # Never clear stale data - let it accumulate
        self._last_write_time = time.time()
        
        # DATA FLOW TRACKING: Track bytes received vs bytes processed
        self._total_bytes_received = 0
        self._total_bytes_buffered = 0  
        self._total_bytes_rejected = 0
        self._total_bytes_to_pipe = 0
        
        # Get system's pipe capacity - let the system determine this, not external config
        try:
            with open("/proc/sys/fs/pipe-max-size", "r") as f:
                self._desired_pipe_capacity = int(f.read().strip())
        except (FileNotFoundError, PermissionError, ValueError):
            self._desired_pipe_capacity = 2**20  # 1MB fallback
        
        # fcntl constants
        self._F_GETPIPE_SZ = 1032
        self._F_SETPIPE_SZ = 1031
        
        self._open_pipe()
    
    def _open_pipe(self) -> None:
        """Open pipe for writing with better error handling"""
        if not self._fdPipe:
            try:
                # Try to open pipe for writing (requires a reader to be connected)
                self._fdPipe = os.open(self._kNamedPipeFilePathString, os.O_WRONLY | os.O_NONBLOCK)
                
                # Set pipe to maximum size
                try:
                    fcntl.fcntl(self._fdPipe, self._F_SETPIPE_SZ, self._desired_pipe_capacity)
                except Exception as e:
                    _log_msg(f"Failed to set pipe size: {e}", 1)
                
                # Log successful connection
                try:
                    actual_size = fcntl.fcntl(self._fdPipe, self._F_GETPIPE_SZ)
                    _log_msg(f"Named pipe connected with capacity: {actual_size} bytes", 1)
                except Exception:
                    pass
                    
            except OSError as e:
                self._fdPipe = None
                # Log the specific reason for connection failure
                if e.errno == 6:  # ENXIO - No such device or address
                    _log_msg("Cannot connect to pipe: No reader connected - start external reader first", 1)
                else:
                    _log_msg(f"Cannot connect to pipe: {e}", 2)
    
    def _whether_pipe_is_broken(self) -> bool:
        """Check if pipe is still writable"""
        return self._fdPipe is None
    
    def _count_bytes_in_pipe(self) -> int:
        """Get current bytes in pipe using FIONREAD"""
        if self._whether_pipe_is_broken():
            return 0
        
        try:
            buf = bytearray(4)
            fcntl.ioctl(self._fdPipe, termios.FIONREAD, buf, 1)
            return int.from_bytes(buf, "little")
        except:
            return 0
    
    @property
    def named_pipe_system_capacity(self) -> int:
        """Get pipe's system capacity"""
        if self._fdPipe:
            try:
                return fcntl.fcntl(self._fdPipe, self._F_GETPIPE_SZ)
            except:
                pass
        return self._desired_pipe_capacity
    
    def get_available_space(self) -> int:
        """Calculate available space in pipe"""
        return max(0, self.named_pipe_system_capacity - self._count_bytes_in_pipe())
    
    def _clear_stale_buffers(self) -> int:
        """Clear stale internal buffers if they've been sitting too long without writes"""
        if not self._byteQ or not hasattr(self, '_last_write_time'):
            return 0
            
        current_time = time.time()
        time_since_write = current_time - self._last_write_time
        
        if time_since_write > self._buffer_timeout and len(self._byteQ) > 0:
            cleared_bytes = self._byteQ.len()
            _log_msg(f"Clearing {cleared_bytes:,} bytes of stale buffer data (idle for {time_since_write:.1f}s)", 1)
            self._byteQ.clear()
            return cleared_bytes
        
        return 0
    
    def _check_capacity_limit(self, additional_bytes: int) -> bool:
        """Check if adding additional_bytes would exceed target capacity"""
        if not self._enforce_capacity:
            return True  # No limit enforced
            
        current_total = self.len_total_buffered()
        would_exceed = (current_total + additional_bytes) > self._target_capacity
        
        if would_exceed:
            excess = (current_total + additional_bytes) - self._target_capacity
            _log_msg(f"Capacity limit check: Would exceed target by {excess:,} bytes", 2)
            
        return not would_exceed
    
    def _enforce_capacity_limit(self, data_size: int) -> int:
        """Enforce capacity limit using high/low water mark system for proper refill behavior"""
        if not self._enforce_capacity:
            return data_size  # No limit enforced
            
        current_total = self.len_total_buffered()
        
        # WATER MARK SYSTEM: Allow refills when buffer is low
        # Low water mark: 50% of target capacity
        # High water mark: 100% of target capacity (strict limit)
        low_water_mark = self._target_capacity * 0.5
        high_water_mark = self._target_capacity
        
        # If we're below low water mark, allow writes freely to encourage refill
        if current_total < low_water_mark:
            # Still cap at high water mark to prevent extreme overflow
            available_capacity = high_water_mark - current_total
            accepted_size = min(data_size, available_capacity)
            
            if accepted_size < data_size:
                _log_msg(f"Refill mode: Accepting {accepted_size:,} of {data_size:,} bytes (buffer at {current_total:,}/{self._target_capacity:,})", 2)
            else:
                _log_msg(f"Refill mode: Accepting all {data_size:,} bytes (buffer at {current_total:,}/{self._target_capacity:,})", 3)
            
            return accepted_size
        
        # If we're between low and high water marks, apply gradual restriction
        elif current_total < high_water_mark:
            available_capacity = high_water_mark - current_total
            accepted_size = min(data_size, available_capacity)
            
            if accepted_size < data_size:
                _log_msg(f"Capacity enforcement: Accepting {accepted_size:,} of {data_size:,} bytes (buffer at {current_total:,}/{self._target_capacity:,})", 2)
            
            return accepted_size
        
        # If we're at or above high water mark, reject writes
        else:
            _log_msg(f"Capacity limit reached: Rejecting {data_size:,} bytes (buffer at {current_total:,}/{self._target_capacity:,})", 1)
            return 0

    async def write(self, data: Union[bytes, bytearray, memoryview]) -> int:
        """Write data using optimized chunking and vectored I/O with capacity enforcement"""
        if not data:
            # Empty write - just flush existing buffers and clear stale data
            self._clear_stale_buffers()
            return await self._flush_buffers()
        
        # DATA FLOW TRACKING: Record bytes received
        original_size = len(data)
        self._total_bytes_received += original_size
        _log_msg(f"PipeWriter.write: Received {original_size:,} bytes (total received: {self._total_bytes_received:,})", 2)
        
        # CAPACITY ENFORCEMENT: Check and limit data size based on target capacity
        if self._enforce_capacity:
            # Clear any stale buffers first to free up space
            self._clear_stale_buffers()
            
            # Determine how much data we can actually accept
            accepted_size = self._enforce_capacity_limit(original_size)
            
            if accepted_size == 0:
                self._total_bytes_rejected += original_size
                _log_msg(f"DATA LOSS: Rejected {original_size:,} bytes (total rejected: {self._total_bytes_rejected:,})", 1)
                return 0
            elif accepted_size < original_size:
                rejected_bytes = original_size - accepted_size
                self._total_bytes_rejected += rejected_bytes
                _log_msg(f"DATA LOSS: Partial reject - accepting {accepted_size:,}, rejecting {rejected_bytes:,} (total rejected: {self._total_bytes_rejected:,})", 1)
                data = data[:accepted_size]
        
        bytes_written = 0
        
        # PHASE 1: Chunk incoming data into buffer queue
        if isinstance(data, (bytes, bytearray, memoryview)) and len(data) > 0:
            actual_buffered = len(data)
            self._total_bytes_buffered += actual_buffered
            _log_msg(f"PipeWriter.write: Buffered {actual_buffered:,} bytes (total buffered: {self._total_bytes_buffered:,})", 3)
            
            bytestream = io.BytesIO(data)
            chunk_count = 0
            
            while True:
                chunk = bytestream.read(self.chunk_size)
                if not chunk:
                    break
                
                self._byteQ.append(OptimizedBytesIO(chunk))
                chunk_count += 1
                
                # Yield periodically to prevent blocking event loop
                if chunk_count % 4 == 0:
                    await asyncio.sleep(0)
            
            bytes_written = len(data)
            # Update last write time for stale buffer tracking
            self._last_write_time = time.time()
        
        # PHASE 2: Write buffered data using vectored I/O
        flushed_bytes = await self._flush_buffers()
        if flushed_bytes > 0:
            self._total_bytes_to_pipe += flushed_bytes
            _log_msg(f"PipeWriter.write: Flushed {flushed_bytes:,} bytes to pipe (total to pipe: {self._total_bytes_to_pipe:,})", 3)
        
        return bytes_written
    
    async def _flush_buffers(self) -> int:
        """Flush internal buffers to pipe using vectored I/O"""
        if self._whether_pipe_is_broken():
            self._open_pipe()
        
        if self._whether_pipe_is_broken() or len(self._byteQ) == 0:
            return 0
        
        available_space = self.get_available_space()
        if available_space <= 0:
            # Pipe is full - data stays in internal buffers until space is available
            return 0
        
        # Prepare vectored write buffers
        chunks_to_write = []
        buffers_used = []
        bytes_prepared = 0
        
        # Collect buffers that fit in available space
        while bytes_prepared < available_space and len(self._byteQ) > 0:
            try:
                next_buffer = self._byteQ[0]
                buffer_size = next_buffer.len()
                
                if bytes_prepared + buffer_size <= available_space:
                    # Entire buffer fits
                    buffer_obj = self._byteQ.popleft()
                    chunks_to_write.append(buffer_obj.getbuffer())
                    buffers_used.append((buffer_obj, buffer_size, True))  # complete
                    bytes_prepared += buffer_size
                else:
                    # Only partial buffer fits
                    buffer_obj = self._byteQ.popleft()
                    usable_size = available_space - bytes_prepared
                    buffer_data = buffer_obj.read(usable_size)
                    chunks_to_write.append(buffer_data)
                    buffers_used.append((buffer_obj, usable_size, False))  # partial
                    self._byteQ.appendleft(buffer_obj)  # Put back remainder
                    bytes_prepared += usable_size
                    break
            except IndexError:
                break
        
        # Write using vectored I/O (KEY OPTIMIZATION!)
        total_written = 0
        if chunks_to_write:
            try:
                total_written = os.writev(self._fdPipe, chunks_to_write)
                
                # Handle partial writes
                if total_written < bytes_prepared:
                    self._restore_partial_write(buffers_used, total_written)
                    
            except BlockingIOError:
                _log_msg("BlockingIOError during vectored write", 2)
                # Restore all buffers if write blocked
                self._restore_all_buffers(buffers_used)
            except BrokenPipeError:
                _log_msg("BrokenPipeError during vectored write", 2)
                # Pipe broken - mark as such and restore buffers
                self._fdPipe = None
                self._restore_all_buffers(buffers_used)
        
        return total_written
    
    def _restore_partial_write(self, buffers_used, bytes_written: int) -> None:
        """Handle partial write by restoring unwritten portions"""
        bytes_accounted = 0
        
        for i, (buffer_obj, size, complete) in enumerate(buffers_used):
            if bytes_accounted + size <= bytes_written:
                # This buffer was completely written
                bytes_accounted += size
                continue
            
            if bytes_accounted >= bytes_written:
                # This buffer wasn't written at all
                if not complete:
                    buffer_obj.putback(size)
                self._byteQ.appendleft(buffer_obj)
                
                # Restore all remaining buffers
                for j in range(i + 1, len(buffers_used)):
                    remaining_buffer, remaining_size, remaining_complete = buffers_used[j]
                    if not remaining_complete:
                        remaining_buffer.putback(remaining_size)
                    self._byteQ.appendleft(remaining_buffer)
                break
            
            # This buffer was partially written
            partial_bytes = bytes_written - bytes_accounted
            remaining_bytes = size - partial_bytes
            buffer_obj.putback(remaining_bytes)
            self._byteQ.appendleft(buffer_obj)
            
            # Restore remaining buffers
            for j in range(i + 1, len(buffers_used)):
                remaining_buffer, remaining_size, remaining_complete = buffers_used[j]
                if not remaining_complete:
                    remaining_buffer.putback(remaining_size)
                self._byteQ.appendleft(remaining_buffer)
            break
    
    def _restore_all_buffers(self, buffers_used) -> None:
        """Restore all buffers in case of write failure"""
        for buffer_obj, size, complete in reversed(buffers_used):
            if not complete:
                buffer_obj.putback(size)
            self._byteQ.appendleft(buffer_obj)
    
    async def refresh(self) -> None:
        """Periodic refresh with stuck buffer monitoring and stale data cleanup"""
        try:
            # Clear stale buffers first
            self._clear_stale_buffers()
            
            self._open_pipe()
            flushed = await self._flush_buffers()
            
            # Monitor for stuck buffers
            if self.is_buffer_stuck():
                _log_msg(f"WARNING: {self._byteQ.len()} bytes stuck in internal buffers", 1)
                _log_msg(f"Available pipe space: {self.get_available_space()}", 2)

            # DATA FLOW REPORTING: Periodic statistics (every ~30 calls to refresh)
            if not hasattr(self, '_refresh_counter'):
                self._refresh_counter = 0
            self._refresh_counter += 1
            
            if self._refresh_counter % 30 == 0:  # Report every 30 refresh cycles
                stats = self.get_data_flow_stats()
                _log_msg(f"DATA FLOW STATS: Received={stats['total_received']:,}, "
                        f"Buffered={stats['total_buffered']:,}, "
                        f"Rejected={stats['total_rejected']:,}, "
                        f"ToPipe={stats['total_to_pipe']:,}, "
                        f"Loss={stats['loss_percentage']:.1f}%", 1)
                
        except Exception as e:
            log_exception(e, "PipeWriter.refresh")
            _log_msg(f"Error in refresh: {e}", 0)
            # Try to recover
            if self._fdPipe:
                try:
                    os.close(self._fdPipe)
                except:
                    pass
                self._fdPipe = None
    
    def len_accessible(self) -> int:
        """Bytes accessible to readers (only what's actually in the pipe)"""
        return self._count_bytes_in_pipe()
    
    def len_total_buffered(self) -> int:
        """Total bytes in pipeline (pipe + internal buffers) - for internal use"""
        return self._count_bytes_in_pipe() + self._byteQ.len()
    
    def is_buffer_stuck(self) -> bool:
        """Check if internal buffers have data that can't be flushed to pipe"""
        return self._byteQ.len() > 0 and self.get_available_space() > 0
    
    def get_buffer_health(self) -> dict:
        """Return detailed buffer status for diagnostics"""
        current_total = self.len_total_buffered()
        
        # Calculate water marks if capacity enforcement is enabled
        water_marks = {}
        if self._enforce_capacity:
            low_water_mark = self._target_capacity * 0.5
            high_water_mark = self._target_capacity
            
            water_marks = {
                "low_water_mark": low_water_mark,
                "high_water_mark": high_water_mark,
                "below_low_water": current_total < low_water_mark,
                "above_high_water": current_total >= high_water_mark,
                "refill_zone": current_total < low_water_mark,
                "normal_zone": low_water_mark <= current_total < high_water_mark,
                "limit_zone": current_total >= high_water_mark
            }
        
        return {
            "accessible_bytes": self.len_accessible(),
            "buffered_bytes": self._byteQ.len(), 
            "total_bytes": current_total,
            "available_space": self.get_available_space(),
            "pipe_writable": not self._whether_pipe_is_broken(),
            "buffers_stuck": self.is_buffer_stuck(),
            "target_capacity": self._target_capacity,
            "capacity_enforced": self._enforce_capacity,
            "capacity_utilization": (current_total / self._target_capacity * 100) if self._target_capacity else 0,
            "last_write_age": time.time() - self._last_write_time if hasattr(self, '_last_write_time') else 0,
            **water_marks  # Include water mark information
        }

    def get_data_flow_stats(self) -> dict:
        """Return comprehensive data flow statistics for debugging"""
        return {
            "total_received": getattr(self, '_total_bytes_received', 0),
            "total_buffered": getattr(self, '_total_bytes_buffered', 0),
            "total_rejected": getattr(self, '_total_bytes_rejected', 0),
            "total_to_pipe": getattr(self, '_total_bytes_to_pipe', 0),
            "current_internal_buffer": self._byteQ.len(),
            "current_pipe_buffer": self.len_accessible(),
            "efficiency_buffered": (getattr(self, '_total_bytes_buffered', 0) / max(1, getattr(self, '_total_bytes_received', 1))) * 100,
            "efficiency_to_pipe": (getattr(self, '_total_bytes_to_pipe', 0) / max(1, getattr(self, '_total_bytes_buffered', 1))) * 100,
            "loss_percentage": (getattr(self, '_total_bytes_rejected', 0) / max(1, getattr(self, '_total_bytes_received', 1))) * 100
        }

    def len(self) -> int:
        """Total entropy bytes available in the system (for UI display purposes)
        
        NOTE: This method includes automatic stale buffer cleanup
        """
        # Clear stale buffers before reporting length
        # self._clear_stale_buffers()
        return self.len_total_buffered()

    def __len__(self) -> int:
        return self.len()
    
    def get_bytes_in_pipeline(self) -> int:
        """Return the total number of bytes currently stored in both the pipe and internal buffer"""
        # Keep this method for backward compatibility, but note it returns total buffered
        return self.len_total_buffered()
    
    def _count_bytes_in_internal_buffers(self) -> int:
        """Return the total bytes in internal buffers"""
        return self._byteQ.len()
    
    def __repr__(self) -> str:
        output = f"""
max capacity: {self.named_pipe_system_capacity}
bytes in pipe: {self._count_bytes_in_pipe()}
bytes in internal buffers: {self._count_bytes_in_internal_buffers()}
total bytes: {self._count_bytes_in_internal_buffers() + self._count_bytes_in_pipe()}
"""
        return output
    
    def __del__(self) -> None:
        """Cleanup resources"""
        try:
            if self._fdPipe:
                os.close(self._fdPipe)
        except:
            pass


# ==============================================================================
# OPTIMIZED PROCESS-BASED PIPEWRITER (from isolated_pipe_writer.py)
# ==============================================================================

class IsolatedPipeWriter:
    """PipeWriter that runs in a separate process to avoid event loop starvation"""
    
    def __init__(self, namedPipeFilePathString: str = "/tmp/pilferedbits"):
        self.namedPipeFilePathString = namedPipeFilePathString
        # Remove arbitrary queue size limit - data should never be dropped
        self.data_queue = multiprocessing.Queue()  # Unlimited queue to prevent data loss
        self.control_queue = multiprocessing.Queue()
        self.stats_queue = multiprocessing.Queue()
        self.process = None
        self._shutdown = False
        
    def start(self):
        """Start the isolated PipeWriter process"""
        if self.process and self.process.is_alive():
            return
            
        self.process = multiprocessing.Process(
            target=self._worker_process,
            args=(self.data_queue, self.control_queue, self.stats_queue, self.namedPipeFilePathString)
        )
        self.process.daemon = True  # Clean shutdown with parent
        self.process.start()
        
    async def write(self, data):
        """Write data to the isolated pipe (blocking to ensure no data loss)"""
        if not self.process or not self.process.is_alive():
            self.start()
            
        if data:
            # Block until data is queued - never drop data
            self.data_queue.put(data)
            return len(data)
        return 0
    
    def get_stats(self):
        """Get statistics from the isolated writer"""
        try:
            self.control_queue.put("stats", timeout=0.1)
            return self.stats_queue.get(timeout=0.1)
        except (queue.Empty, queue.Full):
            return {"error": "stats unavailable"}
    
    def len(self):
        """Get current bytes in pipeline for TaskResultWriter compatibility"""
        stats = self.get_stats()
        return stats.get('pipe_bytes', 0)
    
    def __len__(self):
        """Python len() support"""
        return self.len()
    
    async def refresh(self):
        """No-op refresh since isolated process handles its own refreshing"""
        # The isolated worker process continuously refreshes on its own
        # No action needed here
        pass
    
    def stop(self):
        """Stop the isolated PipeWriter process"""
        if self.process and self.process.is_alive():
            try:
                self.control_queue.put("shutdown", timeout=1.0)
                self.process.join(timeout=2.0)
            except:
                pass
            finally:
                if self.process.is_alive():
                    self.process.terminate()
                    self.process.join(timeout=1.0)
                    
    def __del__(self):
        """Cleanup on destruction"""
        self.stop()
    
    @staticmethod
    def _worker_process(data_queue, control_queue, stats_queue, pipe_path):
        """Worker process that handles all pipe writing"""
        import asyncio
        import signal
        import sys
        
        # Set up signal handling for clean shutdown
        def signal_handler(signum, frame):
            sys.exit(0)
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        # Create new event loop for this process
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def worker_main():
            writer = PipeWriter(namedPipeFilePathString=pipe_path)
            bytes_written = 0
            items_processed = 0
            
            try:
                while True:
                    # Handle control commands
                    try:
                        cmd = control_queue.get_nowait()
                        if cmd == "shutdown":
                            break
                        elif cmd == "stats":
                            stats = {
                                "bytes_written": bytes_written,
                                "items_processed": items_processed,
                                "queue_size": data_queue.qsize(),
                                "pipe_bytes": len(writer)
                            }
                            try:
                                stats_queue.put_nowait(stats)
                            except queue.Full:
                                pass  # Drop stats if queue full
                    except queue.Empty:
                        pass
                    
                    # Process data queue
                    try:
                        data = data_queue.get_nowait()
                        if data:
                            written = await writer.write(data)
                            bytes_written += written
                            items_processed += 1
                    except queue.Empty:
                        pass
                    
                    # Refresh the writer
                    await writer.refresh()
                    await asyncio.sleep(0.01)  # Prevent busy waiting
                    
            except Exception as e:
                print(f"PipeWriter worker error: {e}", file=sys.stderr)
            finally:
                # Final flush
                try:
                    await writer.refresh()
                except:
                    pass
        
        try:
            loop.run_until_complete(worker_main())
        except KeyboardInterrupt:
            pass
        finally:
            loop.close()


# ==============================================================================
# CONVENIENCE FACTORY FUNCTIONS
# ==============================================================================

def create_standard_writer(namedPipeFilePathString: str = "/tmp/pilferedbits", 
                          chunk_size: int = 4096) -> PipeWriter:
    """Create a standard PipeWriter instance
    
    Args:
        namedPipeFilePathString: Path to named pipe
        chunk_size: Buffer chunk size (default 4KiB for optimal pipe writing)
    """
    return PipeWriter(namedPipeFilePathString, chunk_size)


def create_isolated_writer(namedPipeFilePathString: str = "/tmp/pilferedbits") -> IsolatedPipeWriter:
    """Create an isolated process-based PipeWriter instance for maximum reliability"""
    return IsolatedPipeWriter(namedPipeFilePathString)


def create_optimal_writer(namedPipeFilePathString: str = "/tmp/pilferedbits", 
                         use_process_isolation: bool = False) -> Union[PipeWriter, IsolatedPipeWriter]:
    """Create the optimal PipeWriter based on use case
    
    Args:
        namedPipeFilePathString: Path to named pipe
        use_process_isolation: True for maximum reliability during intensive operations
    
    Returns:
        PipeWriter or IsolatedPipeWriter instance
    """
    if use_process_isolation:
        return create_isolated_writer(namedPipeFilePathString)
    else:
        # Use 2MiB chunks - optimal for vectored I/O (os.writev) performance
        return create_standard_writer(namedPipeFilePathString, chunk_size=2097152)  # 2MiB chunks
