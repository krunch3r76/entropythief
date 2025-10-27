# entropythief
> **⚠️ Prerequisite** – A Golem requestor must be installed to run this project.  
> See the [Golem handbook](https://handbook.golem.network/requestor-tutorials/flash-tutorial-of-requestor-development) for details.

`entropythief` pulls high‑quality random bits from multiple remote providers that expose Intel’s **RDSEED** instruction.  When the local buffer falls below half of a user‑defined threshold, new requests are sent automatically.

---

## Table of Contents
1. [Quick Start](#quick-start)
2. [Requirements](#requirements)
3. [Video Demo](#video-demo)
4. [What It Does (Non‑technical)](#what-it-does-non-technical)
5. [Usage](#usage)
6. [API & Examples](#api--examples)
7. [UI Components](#ui-components)
8. [Project Structure](#project-structure)
9. [Applications & Memory Management](#applications--memory-management)
10. [Discussion & Background](#discussion--background)
11. [TL;DR](#tldr)
12. [Credits & References](#credits--references)

---

## Quick Start
```bash
# Clone the repo
git clone https://github.com/krunch3r76/entropythief.git
cd entropythief
# Checkout a stable tag (optional)
git checkout v1.3.2
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate
# Install Python dependencies
pip install -r entropythief/requirements.txt   # includes yapapi==0.13.1
# Initialise Golem payment (you’ll be prompted for your wallet)
yagna payment init --sender
# Run the controller – use `--help` to see options
./entropythief.py          # defaults to testnet
```
While `entropythief.py` is running, open a second terminal and try one of the demo readers:
```bash
cd readers/print_nonce
python3 print_nonce.py      # prints 64‑bit nonces from /tmp/pilferedbits
python3 burn.sh             # continuously drains the pipe (interactive demo)
```
You can also tail the log files to watch progress:
```bash
tail -f stderr          # or `entropythief-yapapi.log`
```

---

## Requirements
- **Golem requestor** – Install the Golem client (see the [handbook tutorial](https://handbook.golem.network/requestor-tutorials/flash-tutorial-of-requestor-development)).
- **yapapi 0.13.1** – The Python wrapper for Golem’s API; this version is required and will be installed automatically when you follow the usage instructions below.

---

## Video Demo  
All demo videos are hosted at <https://krunch3r76.github.io/entropythief>.  
Your browser needs Ogg support to view the first video; the second is an MP4 fallback.
| Demo | Description | Link |
|------|-------------|------|
| **Golem‑stream (OGG)** | Shows how `entropythief` pulls entropy from multiple providers in real time. | <https://krunch3r76.github.io/entropythief/video2.ogg> |
| **Inline readers API demo (MP4)** | Demonstrates the `_readers_` API: random dice rolls, bit streams, etc., using the pre‑recorded video. | <https://user-images.githubusercontent.com/46289600/148718743-b365840e-86c3-436e-91b6-4852615bbe66.mp4> |
### Quick‑look thumbnail  
[![Watch the MP4 demo](https://krunch3r76.github.io/entropythief/thumbnail2.png)](https://user-images.githubusercontent.com/46289600/148718743-b365840e-86c3-436e-91b6-4852615bbe66.mp4)
Feel free to click the thumbnail or open each link directly to view the corresponding demo.

---

## What It Does (Non‑technical)
Computers can provide random numbers; however, hardware designs make such number sequences somewhat predictable. In computers, numbers are made up of sequences of 1s and 0's stored as bytes. `entropythief` has several computers produce random sequences of bytes and chops and mixes them to make an unpredictable sequence of never‑before‑seen random bit stream, like snowflakes, and without any intrinsic periodicity. Randomness in computers has many scientific and practical applications and may have applications in art. At the moment `entropythief` makes no guarantees on the quality of randomness but does facilitate reprogramming to refine or improve the results. At any rate, `entropythief` may be summed up as a faucet of random 1's and 0's (from which a true random number generator may be built).

---

## Usage
### Runtime Commands
While `entropythief.py` is running you can adjust parameters on the fly:
| Command | Description |
|---------|-------------|
| `set buflim=<num>` | Minimum buffer size (bytes).  Refills when below half this value. |
| `set maxworkers=<num>` | Max number of Golem workers to provision. |
| `set budget=<float>` | Stop requesting once the total cost exceeds this amount. |
| `restart` | Restart after a payment failure or budget exhaustion. |
| `stop` | Gracefully exit. |

**Example session**
```bash
pause
set maxworkers=13
set buflim=$((250*2**20))   # 250 MiB
set budget=5                # $5 USD
start
```
> **Tip:** Use `tail -f stderr` to watch the buffer fill in real time.

---

## API & Examples
The controller writes random bytes to `/tmp/pilferedbits`.  
You can read from this pipe with any language.  A Python helper is provided:
```python
# readers/pipe_reader.py
from pathlib import Path
PIPE = Path("/tmp/pilferedbits")
def read_bytes(n: int) -> bytes:
    with PIPE.open("rb") as f:
        return f.read(n)
```
### Quick examples
* **Print a 64‑bit nonce**
```bash
python3 readers/print_nonce.py
```
* **Generate a random bit**
```python
from readers.entropybitreader import EntropyBitReader
for bit in EntropyBitReader():
    print(bit)   # 0 or 1
```
* **Roll a die (1‑6)**
```python
from readers.roll_die.diceroller import DiceRoller
roller = DiceRoller()
print(roller.roll())   # random integer 1–6
```

---

## UI Components
While running, the controller prints a status line that accepts user input:
```
w:<started>/<max>  cost:<spent>/<budget>  buf:<bytes_in_buffer>/<buflim>
```
- **`w`** – Workers started vs. maximum.
- **`cost`** – Total spent so far vs. budget.
- **`buf`** – Current buffer size in bytes.

---

## Project Structure
```text
entropythief/
├── entropythief.py          # controller (daemonizes the Golem executor)
├── application.py           # main routine
├── model.py                # Golem‑specific logic
├── TaskResultWriter.py     # base & derived writers
├── pipe_writer.py          # buffered named‑pipe writer
├── stderr                  # redirected stderr / log file
├── main.log                # controller debug output
├── entropythief-yapapi.log  # yapapi INFO/DEBUG logs
└── readers/
    ├── pipe_reader.py      # API to read from the pipe
    ├── entropybitreader.py # generator for random bits
    └── roll_die/diceroller.py
├── worker/
    ├── worker_public.py   # public namespace for provider interaction
    ├── Dockerfile         # VM image build
    ├── worker.py          # VM creation logic
    └── randwriter.c       # compiled worker executable
└── /tmp/pilferedbits        # named pipe (created at runtime)
```

---

## Applications & Memory Management
- **Applications** – Use the raw bit stream for cryptography, simulations, or artistic projects.
- **Memory** – Start with `--conceal-view` to suppress stdout buffering when streaming large amounts of data.
```bash
./entropythief.py --conceal-view
```

---

## Discussion & Background
Randomness in software is often *pseudo* (deterministic) rather than truly random.  
Intel’s **RDSEED** provides a hardware‑generated, statistically uniform 256‑bit block per call.  By aggregating RDSEED outputs from many independent providers, `entropythief` increases confidence that the resulting stream remains unbiased and unpredictable—even if one source fails or becomes biased.
> *“Randomness is not perfect; it’s an approximation of unpredictability.”* – John Venn (1834‑1923)

---

## TL;DR
`entropythief` pulls large volumes of raw entropy from remote Golem providers, mixes them, and exposes the result as a continuous stream of random bits via `/tmp/pilferedbits`.  It’s a proof‑of‑concept for building high‑quality TRNGs in distributed environments.

---

## Credits & References
- Inspired by [gandom](https://github.com/reza-hackathons/gandom).
- Splash screen ASCII art from <https://asciiart.website/index.php?art=logos%20and%20insignias/smiley>.
- RDSEED documentation:
  - Intel: <https://software.intel.com/content/www/us/en/develop/articles/intel-digital-random-number-generator-drng-software-implementation-guide.html>
  - Wikipedia: <https://en.wikipedia.org/wiki/RDSEED>

---

Happy hacking! 🎲
