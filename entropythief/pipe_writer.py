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
from typing import Optional, Union


_DEBUGLEVEL = (
    int(os.environ["PYTHONDEBUGLEVEL"]) if "PYTHONDEBUGLEVEL" in os.environ else 0
)


def _log_msg(msg: str, debug_level: int = 0) -> None:
    """Simple logging function"""
    if debug_level <= _DEBUGLEVEL:
        print(f"[pipe_writer] {msg}")


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
    
    def len(self) -> int:
        return max(0, self._running_total)
    
    def __len__(self) -> int:
        return self.len()


class PipeWriter:
    """High-performance pipe writer using vectored I/O and intelligent buffering"""
    
    def __init__(self, namedPipeFilePathString: str = "/tmp/pilferedbits", 
                 chunk_size: int = 4096):
        """Initialize PipeWriter with optimized settings"""
        self._kNamedPipeFilePathString = namedPipeFilePathString
        self.chunk_size = chunk_size
        self._fdPipe: Optional[int] = None
        self._byteQ = OptimizedBytesDeque()
        
        # Get system's maximum pipe size
        try:
            with open("/proc/sys/fs/pipe-max-size", "r") as f:
                self._desired_pipe_capacity = int(f.read().strip())
        except (FileNotFoundError, PermissionError, ValueError):
            self._desired_pipe_capacity = 2**20  # 1MB default
        
        # fcntl constants
        self._F_GETPIPE_SZ = 1032
        self._F_SETPIPE_SZ = 1031
        
        self._open_pipe()
    
    def _open_pipe(self) -> None:
        """Open pipe for writing with optimal size"""
        if not self._fdPipe:
            try:
                self._fdPipe = os.open(self._kNamedPipeFilePathString, os.O_WRONLY | os.O_NONBLOCK)
                
                # Set pipe to maximum size
                try:
                    fcntl.fcntl(self._fdPipe, self._F_SETPIPE_SZ, self._desired_pipe_capacity)
                except Exception:
                    pass  # Not critical if this fails
                
                # Log actual pipe size
                try:
                    actual_size = fcntl.fcntl(self._fdPipe, self._F_GETPIPE_SZ)
                    _log_msg(f"Pipe opened with capacity: {actual_size} bytes", 1)
                except Exception:
                    pass
                    
            except OSError:
                self._fdPipe = None
    
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
    
    async def write(self, data: Union[bytes, bytearray, memoryview]) -> int:
        """Write data using optimized chunking and vectored I/O"""
        if not data:
            # Empty write - just flush existing buffers
            return await self._flush_buffers()
        
        bytes_written = 0
        
        # PHASE 1: Chunk incoming data into buffer queue
        if isinstance(data, (bytes, bytearray, memoryview)) and len(data) > 0:
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
        
        # PHASE 2: Write buffered data using vectored I/O
        await self._flush_buffers()
        
        return bytes_written
    
    async def _flush_buffers(self) -> int:
        """Flush internal buffers to pipe using vectored I/O"""
        if self._whether_pipe_is_broken():
            self._open_pipe()
        
        if self._whether_pipe_is_broken() or len(self._byteQ) == 0:
            return 0
        
        available_space = self.get_available_space()
        if available_space <= 0:
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
                # Restore all buffers if write blocked
                self._restore_all_buffers(buffers_used)
            except BrokenPipeError:
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
        """Periodic refresh to flush buffers"""
        try:
            self._open_pipe()
            await self._flush_buffers()
        except Exception as e:
            _log_msg(f"Error in refresh: {e}", 0)
            # Try to recover
            if self._fdPipe:
                try:
                    os.close(self._fdPipe)
                except:
                    pass
                self._fdPipe = None
    
    def len(self) -> int:
        """Total bytes in pipeline (pipe + buffers)"""
        return self._count_bytes_in_pipe() + self._byteQ.len()
    
    def __len__(self) -> int:
        return self.len()
    
    def get_bytes_in_pipeline(self) -> int:
        """Return the total number of bytes currently stored in both the pipe and internal buffer"""
        return self.len()
    
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
