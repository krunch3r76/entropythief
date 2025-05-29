#!/usr/bin/env python3
"""
Test script to compare different chunk sizes with multiple readers active.
This will prove whether chunk size affects pipe writing under contention.
"""

import asyncio
import threading
import time
import sys
import os

# Add the current directory to Python path
sys.path.append('.')

from entropythief.pipe_writer import PipeWriter

# Test configuration
TEST_DURATION = 30  # seconds
DATA_SIZE = 2 * 1024 * 1024  # 2MB per write
WRITE_INTERVAL = 0.1  # 100ms between writes

class WriterThread(threading.Thread):
    """Thread that continuously writes data using specified chunk size"""
    
    def __init__(self, thread_id, chunk_size):
        super().__init__()
        self.thread_id = thread_id
        self.chunk_size = chunk_size
        self.bytes_written = 0
        self.write_attempts = 0
        self.successful_writes = 0
        self.zero_writes = 0
        self.running = True
        self.chunk_size_str = f"{chunk_size // 1024}KB" if chunk_size < 1024*1024 else f"{chunk_size // (1024*1024)}MB"
        
    def run(self):
        """Run the async event loop in this thread"""
        asyncio.run(self._async_run())
        
    async def _async_run(self):
        """Async worker that writes data to pipe"""
        print(f"Thread {self.thread_id} starting with chunk_size={self.chunk_size_str}")
        
        # Create PipeWriter with specific chunk size
        writer = PipeWriter(chunk_size=self.chunk_size)
        
        # Generate test data (random bytes)
        test_data = os.urandom(DATA_SIZE)
        
        start_time = time.time()
        
        while self.running and (time.time() - start_time) < TEST_DURATION:
            try:
                self.write_attempts += 1
                
                # Try to write data
                written = await writer.write(test_data)
                
                if written > 0:
                    self.bytes_written += written
                    self.successful_writes += 1
                else:
                    self.zero_writes += 1
                
                # Periodic refresh
                await writer.refresh()
                
                # Small delay between writes
                await asyncio.sleep(WRITE_INTERVAL)
                
            except Exception as e:
                print(f"Thread {self.thread_id} error: {e}")
                
        print(f"\nThread {self.thread_id} ({self.chunk_size_str}) finished:")
        print(f"  Total bytes written: {self.bytes_written:,}")
        print(f"  Write attempts: {self.write_attempts}")
        print(f"  Successful writes: {self.successful_writes}")
        print(f"  Zero-byte writes: {self.zero_writes}")
        print(f"  Success rate: {(self.successful_writes/self.write_attempts*100):.1f}%")
        print(f"  Avg bytes/write: {self.bytes_written/max(1,self.successful_writes):,.0f}")
        
        # Check internal buffer state
        print(f"  Final buffer state: {writer._count_bytes_in_internal_buffers():,} bytes buffered")
        print(f"  Final pipe state: {writer.len():,} total bytes in pipeline")


def main():
    """Run the test with different chunk sizes"""
    print("=== Chunk Size Comparison Test ===")
    print(f"Test duration: {TEST_DURATION} seconds")
    print(f"Data size per write: {DATA_SIZE:,} bytes")
    print("\nStarting writers with different chunk sizes...\n")
    
    # Check if mega.py readers are running
    mega_check = os.popen("pgrep -f 'mega.py' | wc -l").read().strip()
    print(f"Active mega.py processes: {mega_check}")
    
    # Create threads with different chunk sizes
    threads = []
    
    # 2 threads with 256KB chunks
    for i in range(2):
        t = WriterThread(f"256KB-{i+1}", 256 * 1024)
        threads.append(t)
    
    # 2 threads with 2MB chunks  
    for i in range(2):
        t = WriterThread(f"2MB-{i+1}", 2 * 1024 * 1024)
        threads.append(t)
    
    # Start all threads
    for t in threads:
        t.start()
    
    # Wait for test duration
    print(f"\nRunning test for {TEST_DURATION} seconds...")
    time.sleep(TEST_DURATION)
    
    # Stop all threads
    for t in threads:
        t.running = False
    
    # Wait for threads to finish
    for t in threads:
        t.join()
    
    # Summary
    print("\n=== SUMMARY ===")
    
    # Calculate totals for each chunk size
    kb256_total = sum(t.bytes_written for t in threads if "256KB" in t.thread_id)
    mb2_total = sum(t.bytes_written for t in threads if "2MB" in t.thread_id)
    
    kb256_success = sum(t.successful_writes for t in threads if "256KB" in t.thread_id)
    mb2_success = sum(t.successful_writes for t in threads if "2MB" in t.thread_id)
    
    print(f"\n256KB chunk threads:")
    print(f"  Total bytes written: {kb256_total:,}")
    print(f"  Total successful writes: {kb256_success}")
    
    print(f"\n2MB chunk threads:")
    print(f"  Total bytes written: {mb2_total:,}")
    print(f"  Total successful writes: {mb2_success}")
    
    if kb256_total > 0 or mb2_total > 0:
        if kb256_total > mb2_total:
            print(f"\n✓ 256KB chunks wrote {kb256_total/max(1,mb2_total):.1f}x more data")
        elif mb2_total > kb256_total:
            print(f"\n✓ 2MB chunks wrote {mb2_total/max(1,kb256_total):.1f}x more data")
        else:
            print(f"\n✓ Both chunk sizes wrote the same amount")
    else:
        print(f"\n✗ No data was written by any thread!")


if __name__ == "__main__":
    main() 