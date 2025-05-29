# How to Use Shared PipeReader to Eliminate DiceRoller Stalls

## ❌ OLD WAY (Causes Stalls)

```python
import threading
from roll_die.diceroller import DiceRoller

def worker_thread():
    # BAD: Each thread creates its own PipeReader
    dice_roller = DiceRoller(high_face=6, number_of_dice=2)
    
    for _ in range(100):
        roll = dice_roller()  # This can stall!
        print(roll)

# 10 threads = 10 PipeReaders = 10 file descriptors = STALLS
threads = []
for i in range(10):
    t = threading.Thread(target=worker_thread)
    threads.append(t)
    t.start()
```

## ✅ NEW WAY (No Stalls)

```python
import threading
from pipe_reader import PipeReader
from roll_die.diceroller import DiceRoller

# Create ONE shared PipeReader with large buffer
shared_reader = PipeReader(buffer_size=100*1024*1024)  # 100MB

def worker_thread():
    # GOOD: All threads share the same PipeReader
    dice_roller = DiceRoller(
        high_face=6, 
        number_of_dice=2, 
        pipe_reader=shared_reader  # ← KEY: Use shared reader
    )
    
    for _ in range(100):
        roll = dice_roller()  # No stalls!
        print(roll)

# 10 threads = 1 PipeReader = 1 file descriptor = NO STALLS
threads = []
for i in range(10):
    t = threading.Thread(target=worker_thread)
    threads.append(t)
    t.start()
```

## 🚀 EVEN BETTER: Use the Manager Pattern

```python
from shared_dice_roller import SharedDiceRollerManager

# Create the manager once
manager = SharedDiceRollerManager(buffer_size=500*1024*1024)  # 500MB buffer

def worker_thread():
    # Create DiceRoller through the manager
    dice_roller = manager.create_dice_roller(high_face=6, number_of_dice=2)
    
    for _ in range(100):
        roll = dice_roller()  # Blazing fast!
        print(roll)

# All threads automatically use the shared reader
threads = []
for i in range(10):
    t = threading.Thread(target=worker_thread)
    threads.append(t)
    t.start()
```

## 📊 Test It!

Run these commands to see the difference:

```bash
# Test the shared reader implementation
python3 shared_dice_roller.py

# Test uniqueness (proves rolls are different)
python3 test_unique_rolls.py

# Test your specific use case
python3 test_shared_reader.py
```

## 🎯 Key Points

1. **One PipeReader per application** (not per thread)
2. **Large buffer size** (100MB-1GB) to store lots of entropy  
3. **Each dice roll gets unique data** (threads don't interfere)
4. **Massive performance improvement** (no file descriptor contention)

## 🔧 Quick Fix for Existing Code

If you have existing code that creates DiceRollers, just add these 3 lines:

```python
# Add at the top of your file
shared_reader = PipeReader(buffer_size=200*1024*1024)  # 200MB

# Change this:
dice_roller = DiceRoller(high_face=6)

# To this:
dice_roller = DiceRoller(high_face=6, pipe_reader=shared_reader)
```

That's it! Your stalls should disappear! 🎲⚡ 