#!/usr/bin/env python3
"""
Optimized PipeWriter - Based on the old working implementation

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

class OptimizedBytesIO(io.BytesIO):
    """Optimized BytesIO wrapper for efficient streaming"""
    
    def __init__(self, initial_value):
        if not isinstance(initial_value, (bytes, bytearray, memoryview)):
            raise TypeError(f"Expected bytes-like object, got {type(initial_value).__name__}")
        
        super().__init__(initial_value)
        self.seek(0, io.SEEK_END)
        self.__end = self.tell()
        self.seek(0, io.SEEK_SET)
    
    @property
    def end(self):
        return self.__end
    
    def len(self):
        return self.__end - self.tell()
    
    def __len__(self):
        return self.len()
    
    def putback(self, count):
        """Move read position back by count bytes"""
        self.seek(-count, io.SEEK_CUR)


class OptimizedBytesDeque(collections.deque):
    """Deque with running total tracking for efficient length calculation"""
    
    def __init__(self):
        super().__init__()
        self._running_total = 0
    
    def append(self, bytes_io):
        if not isinstance(bytes_io, OptimizedBytesIO):
            raise TypeError("Expected OptimizedBytesIO object")
        self._running_total += len(bytes_io)
        super().append(bytes_io)
    
    def appendleft(self, bytes_io):
        if not isinstance(bytes_io, OptimizedBytesIO):
            raise TypeError("Expected OptimizedBytesIO object")
        self._running_total += len(bytes_io)
        super().appendleft(bytes_io)
    
    def popleft(self):
        rv = super().popleft()
        self._running_total -= len(rv)
        return rv
    
    def len(self):
        return max(0, self._running_total)
    
    def __len__(self):
        return self.len()


class OptimizedPipeWriter:
    """High-performance pipe writer using vectored I/O and intelligent buffering"""
    
    def __init__(self, pipe_path="/tmp/pilferedbits", chunk_size=4096):
        self.pipe_path = pipe_path
        self.chunk_size = chunk_size
        self._fd_pipe = None
        self._byte_queue = OptimizedBytesDeque()
        
        # Get system's maximum pipe size
        try:
            with open("/proc/sys/fs/pipe-max-size", "r") as f:
                self._desired_pipe_capacity = int(f.read().strip())
        except (FileNotFoundError, PermissionError, ValueError):
            self._desired_pipe_capacity = 2**20  # 1MB default
        
        self._open_pipe()
    
    def _open_pipe(self):
        """Open pipe for writing with optimal size"""
        if not self._fd_pipe:
            try:
                self._fd_pipe = os.open(self.pipe_path, os.O_WRONLY | os.O_NONBLOCK)
                
                # Set pipe to maximum size
                try:
                    fcntl.fcntl(self._fd_pipe, 1031, self._desired_pipe_capacity)  # F_SETPIPE_SZ
                except Exception:
                    pass  # Not critical if this fails
                
                # Log actual pipe size
                try:
                    actual_size = fcntl.fcntl(self._fd_pipe, 1032)  # F_GETPIPE_SZ
                    print(f"Pipe opened with capacity: {actual_size} bytes")
                except Exception:
                    pass
                    
            except OSError:
                self._fd_pipe = None
    
    def _pipe_is_broken(self):
        """Check if pipe is still writable"""
        return self._fd_pipe is None
    
    def _count_bytes_in_pipe(self):
        """Get current bytes in pipe using FIONREAD"""
        if self._pipe_is_broken():
            return 0
        
        try:
            buf = bytearray(4)
            fcntl.ioctl(self._fd_pipe, termios.FIONREAD, buf, 1)
            return int.from_bytes(buf, "little")
        except:
            return 0
    
    @property
    def pipe_capacity(self):
        """Get pipe's system capacity"""
        if self._fd_pipe:
            try:
                return fcntl.fcntl(self._fd_pipe, 1032)  # F_GETPIPE_SZ
            except:
                pass
        return self._desired_pipe_capacity
    
    def get_available_space(self):
        """Calculate available space in pipe"""
        return max(0, self.pipe_capacity - self._count_bytes_in_pipe())
    
    async def write(self, data):
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
                
                self._byte_queue.append(OptimizedBytesIO(chunk))
                chunk_count += 1
                
                # Yield periodically to prevent blocking event loop
                if chunk_count % 4 == 0:
                    await asyncio.sleep(0)
            
            bytes_written = len(data)
        
        # PHASE 2: Write buffered data using vectored I/O
        await self._flush_buffers()
        
        return bytes_written
    
    async def _flush_buffers(self):
        """Flush internal buffers to pipe using vectored I/O"""
        if self._pipe_is_broken():
            self._open_pipe()
        
        if self._pipe_is_broken() or len(self._byte_queue) == 0:
            return 0
        
        available_space = self.get_available_space()
        if available_space <= 0:
            return 0
        
        # Prepare vectored write buffers
        chunks_to_write = []
        buffers_used = []
        bytes_prepared = 0
        
        # Collect buffers that fit in available space
        while bytes_prepared < available_space and len(self._byte_queue) > 0:
            try:
                next_buffer = self._byte_queue[0]
                buffer_size = next_buffer.len()
                
                if bytes_prepared + buffer_size <= available_space:
                    # Entire buffer fits
                    buffer_obj = self._byte_queue.popleft()
                    chunks_to_write.append(buffer_obj.getbuffer())
                    buffers_used.append((buffer_obj, buffer_size, True))  # complete
                    bytes_prepared += buffer_size
                else:
                    # Only partial buffer fits
                    buffer_obj = self._byte_queue.popleft()
                    usable_size = available_space - bytes_prepared
                    buffer_data = buffer_obj.read(usable_size)
                    chunks_to_write.append(buffer_data)
                    buffers_used.append((buffer_obj, usable_size, False))  # partial
                    self._byte_queue.appendleft(buffer_obj)  # Put back remainder
                    bytes_prepared += usable_size
                    break
            except IndexError:
                break
        
        # Write using vectored I/O (KEY OPTIMIZATION!)
        total_written = 0
        if chunks_to_write:
            try:
                total_written = os.writev(self._fd_pipe, chunks_to_write)
                
                # Handle partial writes
                if total_written < bytes_prepared:
                    self._restore_partial_write(buffers_used, total_written)
                    
            except BlockingIOError:
                # Restore all buffers if write blocked
                self._restore_all_buffers(buffers_used)
            except BrokenPipeError:
                # Pipe broken - mark as such and restore buffers
                self._fd_pipe = None
                self._restore_all_buffers(buffers_used)
        
        return total_written
    
    def _restore_partial_write(self, buffers_used, bytes_written):
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
                self._byte_queue.appendleft(buffer_obj)
                
                # Restore all remaining buffers
                for j in range(i + 1, len(buffers_used)):
                    remaining_buffer, remaining_size, remaining_complete = buffers_used[j]
                    if not remaining_complete:
                        remaining_buffer.putback(remaining_size)
                    self._byte_queue.appendleft(remaining_buffer)
                break
            
            # This buffer was partially written
            partial_bytes = bytes_written - bytes_accounted
            remaining_bytes = size - partial_bytes
            buffer_obj.putback(remaining_bytes)
            self._byte_queue.appendleft(buffer_obj)
            
            # Restore remaining buffers
            for j in range(i + 1, len(buffers_used)):
                remaining_buffer, remaining_size, remaining_complete = buffers_used[j]
                if not remaining_complete:
                    remaining_buffer.putback(remaining_size)
                self._byte_queue.appendleft(remaining_buffer)
            break
    
    def _restore_all_buffers(self, buffers_used):
        """Restore all buffers in case of write failure"""
        for buffer_obj, size, complete in reversed(buffers_used):
            if not complete:
                buffer_obj.putback(size)
            self._byte_queue.appendleft(buffer_obj)
    
    async def refresh(self):
        """Periodic refresh to flush buffers"""
        try:
            self._open_pipe()
            await self._flush_buffers()
        except Exception as e:
            print(f"Error in refresh: {e}")
            # Try to recover
            if self._fd_pipe:
                try:
                    os.close(self._fd_pipe)
                except:
                    pass
                self._fd_pipe = None
    
    def len(self):
        """Total bytes in pipeline (pipe + buffers)"""
        return self._count_bytes_in_pipe() + self._byte_queue.len()
    
    def __len__(self):
        return self.len()
    
    def __del__(self):
        """Cleanup resources"""
        try:
            if self._fd_pipe:
                os.close(self._fd_pipe)
        except:
            pass


# Example usage showing performance improvement
async def performance_test():
    """Test to demonstrate performance improvement"""
    writer = OptimizedPipeWriter()
    
    # Test with large data chunks
    test_data = b"x" * (1024 * 1024)  # 1MB test data
    
    start_time = time.time()
    
    # Write 100MB total in 1MB chunks
    for i in range(100):
        await writer.write(test_data)
        if i % 10 == 0:
            elapsed = time.time() - start_time
            throughput = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"Written {i+1}MB in {elapsed:.2f}s ({throughput:.1f} MB/s)")
    
    total_time = time.time() - start_time
    total_throughput = 100 / total_time if total_time > 0 else 0
    print(f"Total: 100MB in {total_time:.2f}s ({total_throughput:.1f} MB/s)")
    print(f"Buffered: {writer.len()} bytes")


if __name__ == "__main__":
    asyncio.run(performance_test()) 