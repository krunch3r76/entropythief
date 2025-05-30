#!/usr/bin/env python3
"""
Shared DiceRoller Implementation - Eliminates stalls by using one shared PipeReader

This demonstrates the proper way to use DiceRoller with multiple threads
to avoid file descriptor contention and stalls.
"""

import threading
import time
import sys
from pathlib import Path

# Add readers path
PATH_TO_READERS = Path(__file__).resolve().parent / "readers"
sys.path.append(str(PATH_TO_READERS))

from pipe_reader import PipeReader
from roll_die.diceroller import DiceRoller

class SharedDiceRollerManager:
    """Manager for creating DiceRollers that share a single PipeReader"""
    
    def __init__(self, buffer_size=None):
        """Initialize with a large shared buffer
        
        Args:
            buffer_size: Size of shared buffer (default: 100MB, can be up to GB)
        """
        # Default to 100MB buffer, but allow customization up to GB sizes
        if buffer_size is None:
            buffer_size = 100 * 1024 * 1024  # 100MB
        
        print(f"Creating shared PipeReader with {buffer_size // (1024*1024)}MB buffer...")
        self.shared_reader = PipeReader(buffer_size=buffer_size)
        self._creation_count = 0
        self._lock = threading.Lock()
        
    def create_dice_roller(self, **kwargs):
        """Create a DiceRoller that uses the shared PipeReader
        
        Args:
            **kwargs: All the normal DiceRoller arguments (high_face, number_of_dice, etc.)
            
        Returns:
            DiceRoller: A new DiceRoller instance using the shared pipe reader
        """
        with self._lock:
            self._creation_count += 1
            roller_id = self._creation_count
        
        # Force the DiceRoller to use our shared reader
        kwargs['pipe_reader'] = self.shared_reader
        
        dice_roller = DiceRoller(**kwargs)
        print(f"Created DiceRoller #{roller_id} using shared PipeReader")
        return dice_roller
    
    def get_stats(self):
        """Get statistics about the shared reader"""
        try:
            stats = self.shared_reader.get_buffer_stats()
            stats['dice_rollers_created'] = self._creation_count
            return stats
        except:
            return {'dice_rollers_created': self._creation_count, 'error': 'stats unavailable'}


def example_multi_threaded_usage():
    """Example showing how to use SharedDiceRollerManager"""
    print("=== Shared DiceRoller Multi-threaded Example ===")
    
    # Create the shared manager with 50MB buffer
    manager = SharedDiceRollerManager(buffer_size=50*1024*1024)
    
    # Results collection
    results = {}
    results_lock = threading.Lock()
    
    def worker_thread(worker_id, num_rolls=100):
        """Worker thread that performs dice rolls"""
        start_time = time.time()
        
        # Create DiceRoller using shared reader
        dice_roller = manager.create_dice_roller(
            high_face=6, 
            number_of_dice=2, 
            as_sorted=True
        )
        
        worker_results = []
        for i in range(num_rolls):
            roll = dice_roller()  # Roll 2d6
            worker_results.append(roll)
            
            # Progress update every 20 rolls
            if (i + 1) % 20 == 0:
                elapsed = time.time() - start_time
                print(f"Worker {worker_id}: {i+1}/{num_rolls} rolls in {elapsed:.2f}s")
        
        total_time = time.time() - start_time
        
        # Store results thread-safely
        with results_lock:
            results[worker_id] = {
                'rolls': worker_results,
                'time': total_time,
                'rolls_per_second': num_rolls / total_time
            }
        
        print(f"Worker {worker_id}: COMPLETED {num_rolls} rolls in {total_time:.2f}s ({num_rolls/total_time:.1f} rolls/sec)")
    
    # Start multiple worker threads
    num_workers = 10
    rolls_per_worker = 50
    
    print(f"\nStarting {num_workers} worker threads, each doing {rolls_per_worker} rolls...")
    threads = []
    overall_start = time.time()
    
    for i in range(num_workers):
        t = threading.Thread(target=worker_thread, args=(i, rolls_per_worker))
        threads.append(t)
        t.start()
    
    # Wait for all threads to complete
    for t in threads:
        t.join()
    
    overall_time = time.time() - overall_start
    
    # Analyze results
    print(f"\n=== RESULTS ===")
    print(f"Overall completion time: {overall_time:.2f}s")
    
    total_rolls = num_workers * rolls_per_worker
    overall_rate = total_rolls / overall_time
    print(f"Total rolls: {total_rolls}")
    print(f"Overall rate: {overall_rate:.1f} rolls/second")
    
    # Individual worker performance
    worker_times = [results[i]['time'] for i in range(num_workers)]
    avg_worker_time = sum(worker_times) / len(worker_times)
    fastest_worker = min(worker_times)
    slowest_worker = max(worker_times)
    
    print(f"\nWorker performance:")
    print(f"  Average time per worker: {avg_worker_time:.2f}s")
    print(f"  Fastest worker: {fastest_worker:.2f}s")
    print(f"  Slowest worker: {slowest_worker:.2f}s")
    print(f"  Time variance: {slowest_worker - fastest_worker:.2f}s")
    
    if slowest_worker - fastest_worker < 1.0:
        print("✅ Low variance - no significant stalls detected!")
    else:
        print("❌ High variance - some workers may have stalled")
    
    # Show some sample rolls
    print(f"\nSample rolls from worker 0: {results[0]['rolls'][:10]}")
    
    # Buffer stats
    try:
        stats = manager.get_stats()
        print(f"\nShared buffer stats: {stats}")
    except:
        print("Buffer stats unavailable")


def performance_comparison():
    """Compare shared vs individual PipeReader performance"""
    print("\n" + "="*60)
    print("=== Performance Comparison: Shared vs Individual ===")
    
    def test_approach(approach_name, use_shared=True, num_threads=5, rolls_per_thread=30):
        print(f"\nTesting {approach_name} approach...")
        
        if use_shared:
            manager = SharedDiceRollerManager(buffer_size=20*1024*1024)
        
        completion_times = []
        
        def worker(worker_id):
            start_time = time.time()
            
            if use_shared:
                dice_roller = manager.create_dice_roller(high_face=6, number_of_dice=1)
            else:
                dice_roller = DiceRoller(high_face=6, number_of_dice=1)  # Creates own reader
            
            for _ in range(rolls_per_thread):
                dice_roller()
            
            completion_time = time.time() - start_time
            completion_times.append(completion_time)
            print(f"  {approach_name} worker {worker_id}: {completion_time:.2f}s")
        
        # Run threads
        threads = []
        start_time = time.time()
        
        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        total_time = time.time() - start_time
        avg_worker_time = sum(completion_times) / len(completion_times)
        max_worker_time = max(completion_times)
        
        print(f"  {approach_name} total time: {total_time:.2f}s")
        print(f"  {approach_name} avg worker time: {avg_worker_time:.2f}s")
        print(f"  {approach_name} slowest worker: {max_worker_time:.2f}s")
        
        return total_time, avg_worker_time, max_worker_time
    
    # Test both approaches
    shared_total, shared_avg, shared_max = test_approach("SHARED", use_shared=True)
    individual_total, individual_avg, individual_max = test_approach("INDIVIDUAL", use_shared=False)
    
    # Compare results
    print(f"\n=== COMPARISON RESULTS ===")
    print(f"Total time - Shared: {shared_total:.2f}s, Individual: {individual_total:.2f}s")
    print(f"Avg worker - Shared: {shared_avg:.2f}s, Individual: {individual_avg:.2f}s")
    print(f"Slowest worker - Shared: {shared_max:.2f}s, Individual: {individual_max:.2f}s")
    
    if shared_total < individual_total:
        improvement = ((individual_total - shared_total) / individual_total) * 100
        print(f"✅ Shared approach is {improvement:.1f}% faster overall!")
    
    if shared_max < individual_max:
        stall_reduction = ((individual_max - shared_max) / individual_max) * 100
        print(f"✅ Shared approach reduces worst-case stalls by {stall_reduction:.1f}%!")


if __name__ == "__main__":
    print("Shared DiceRoller Performance Test")
    print("=" * 50)
    
    # Run the main example
    example_multi_threaded_usage()
    
    # Run performance comparison
    performance_comparison()
    
    print(f"\n{'='*50}")
    print("Test completed! Use SharedDiceRollerManager in your code to eliminate stalls.") 