# entropythief

**A golem requestor installation is needed to run this app. Please visit https://www.golem.network for details**
get high quality entropy (randomness) at a steal of a rate from multiple providers utilizing Intel's RDSEED cpu instruction. Requests are sent whenever the pipe falls below half the set threshold. 

# requirements
a requestor installation of golem (see https://handbook.golem.network/requestor-tutorials/flash-tutorial-of-requestor-development)
yapapi module version 0.10.0 (satisfied by following usage directions below)

# Video Demo
See all videos at [https://krunch3r76.github.io/entropythief](https://krunch3r76.github.io/entropythief). Note: your browser must support the ogg codec to view most of these videos as of this writing.

[![Watch the video]()](https://krunch3r76.github.io/entropythief/video2.ogg)

[![Watch the video](https://krunch3r76.github.io/entropythief/thumbnail2.png)](https://user-images.githubusercontent.com/46289600/148718743-b365840e-86c3-436e-91b6-4852615bbe66.mp4)

The inline video here demonstrates the readers API (see API section) by running the included example scripts: these leverage the entropy to get random results such as dice throws or 1's and 0's.

# non technical description
computers can provide random numbers; however, hardware designs make such number sequences somewhat predictable. in computers, numbers are made up of sequences of 1s and 0's stored as bytes. entropythief has several computers produce random sequences of bytes and chops and mixes them to make an unpredictable sequence of never before seen random bit stream, like snowflakes, and without any intrinsic periodicity. randomness in computers has many scientific and practical applications and may have applications in art. atm entropythief makes no guarantees on the quality of randomness but does facilitate reprogramming to refine or improve the results. at any rate, entropythief may be summed up as a faucet of random 1's and 0's (from which a true random number generator may be built).

# usage
```
# Linux or WSL
git clone https://github.com/krunch3r76/entropythief.git
cd entropythief
git checkout v1.2.0
python3 -m venv entropythief-venv
source entropythief-venv/bin/activate
pip install -r entropythief/requirements.txt
yagna payment init --sender
./entropythief.py # --help # to change the network from the default testnet
```

```
# in a separate window while entropythief is running
cd readers/print_nonce
python3 print_nonce.py # to read some nonces

python3 burn.sh # simple interactive script to read continuously from the pipe to demonstrate pipe refills


# optional: 
tail -f stderr # or the entropythief yapapi log file
```

this requestor runs to pilfer as many bytes of random 1's and 0's from as many providers as the user specifies. these parameter(s) can be adjusted on the fly by the user with the following commands:
```
set buflim=<num>      # the minimum threshold that entropythief should do its best to stay above (refills when it falls beneath half this value)
set maxworkers=<num>  # the most workers Golem executor can provision  # the more the more exotic!
set budget=<float>    # the budget above which work should cease (unless this is used to increase the budget)
restart               # after so many payment failures or after budget is exceeded, budget is implied to be over the limit. after setting run this.
stop                  # stop/exit
```

try: **note the following could take awhile to complete depending on network conditions but bytes are asynchronously chunked so it is not a hard wait; remember, you may want to follow along by invoking tail -f stderr.**
```
pause
set maxworkers=13 #across 13 workers
set buflim=250*2**20 #for 1/4 gigabyte of random bytes
set budget=5
start
```
# API
once entropythief runs, it displays the random bytes produced from workers as they arrive and are fed to a named pipe, topping it off. the named pipe can be accessed via any programming language and a sample Python API is provided at `readers/pipe_reader.py`, and an example script is in `readers/print_nonce`. The script retrieves 8 bytes from the pool of /tmp/pilferedbits and prints the corresponding 64bit nonce value. 

additionally, to generate a random 1 or 0, developers can import EntropyBitReader from readers/entropybitreader.py

and to get a truly random number, developers can import DiceRoller from readers/roll_die/diceroller.py

this application may expose sparsely undocumented parts of Golem's Python API, yapapi, to handle specific events in a novel way and to filter providers. see the code for details.

# UI components
```
w:<number of workers started but unfinished>/<maximum>
cost:<total cost aggregated from paid invoices>/<budget>
buf:<number of random bits in units of bytes>/<maximum number of bytes "buflim">
```
on the same line that the UI accepts input, status messages are presented.
the fields are as described above.



# other components
```
./stderr                  # messages and optionally yapapi logger info messages are written to this file in place of stderr
./main.log                # development messages that come from the controller are written to this file
./entropythief-yapapi.log # INFO and DEBUG messages from yapapi
./entropythief.py         # controller-view runnable script that daemonizes the model (Golem executor) and coordinates with the view
application.py            # main routine
model.py                  # the Golem specific code (daemonized by controller.py)
TaskResultWriter.py       # base and derived TaskResultWriter (including Interleaver)
pipe_writer.py            # buffered named pipe writer
readers/pipe_reader.py        # API to named pipe
readers/entropybitreader.py   # provides a EntropyBitReader generator class to generate random bits
readers/roll_die/diceroller.py        # provides the DiceRoller class to function as a TRNG
/tmp/pilferedbits             # named pipe to which the buffered writes continually occur as needed to top off
worker/worker_public.py       # public namespace for variables etc needed by requestor to interact with the provider/vm
worker/Dockerfile             # for vm creation
worker/worker.py              # for vm creation
worker/randwriter.c           # for vm, compiled into worker executable
```

# applications
have fun with a unpredictable and exotic stream of 1's and 0's!

# memory management
start entropythief with the argument option --conceal-view which will prevent bytes from backlogging in stdout. this can be a considerable backlog while streaming gigabytes of random bits.

# discussion
randomness is different things to different people. John Venn described it as raindrops falling on a surface touching different spots until the surface has been completely, or uniformly, saturated [0]. but the randomness here is not so "perfect," as randomness commonly connotes otherwise! randomness with any uniformity and (potential) periodicity similar to what Venn described is considered pseudo randomness, and in the context of using computers for research purposes this is often desired. however, some endeavor to obtain true randomness (say for cryptography, monte carlo simulations...). one obstacle to such however is the intrinsic determinism in any algorithm tied to the computer generating the numbers. the linux kernel offers "true" random power of 2 ranged numbers by altering random numbers according to "random" inputs, such as mouse movements. the amount of randomness thus generated is called entropy. however, there can only be so much user interaction before such randomness is exhausted. to solve this problem, Intel added a feature and corresponding instruction to its 64 bit processors called RDSEED [1], [2]. it is regarded as a hardware true random number generator (base-2 ranged e.g. 16-bit, 32-bit, or 64-bit ranges). however, some have raised concerns about its black-box nature. While RDSEED does not expand a seed deterministically like -- say, RDRAND or /dev/urandom -- it still relies on Intel’s proprietary hardware conditioner. thus, although its output should be truly random, its quality ultimately depends on the trustworthiness of Intel’s design.

entropythief solves the scarcity problem of high quality entropy by procuring randomly generated bits (decomposed from random numbers) in considerable quantities from independent sources, i.e. provider computers on the Golem network, and mixing them together to effectively capture entropy from _movements_ of providers, i.e. random sampling, instead of _movements_ of mice. this input is inherently random because no one provider is necessarily available at any given time on the Golem network. furthermore, its modular nature allows for increased refinement depending on the quality and or quantity desired. for additional details, please refer to the cited sources [1,2] and to the source code of entropythief itself.

[0] __The Logic of Chance__, 3rd Edition, John Venn, Chapter V: "The conception of Randomness and its scientific treatment". 1834-1923. https://www.gutenberg.org/ebooks/57359

[1] https://software.intel.com/content/www/us/en/develop/articles/intel-digital-random-number-generator-drng-software-implementation-guide.html

[2]	https://en.wikipedia.org/wiki/RDSEED


# comments/reflections

this project was inspired by gandom. however, gandom draws upon the system's standard conditioned entropy source (kernel/cpu). furthermore, gandom mixes bytes (stream cipher) to produce a _single_ value whereas entropythief provides a stream of values, which incidentally are mixed by default, and can be played with in a myriad of ways, including passing thru a stream cipher (XOR'ing). additionally, entropythief stores bits in raw format while presenting to the user a bird's eye view of them in the intelligible base 16 (cf. base64).

RDSEED samples the chip’s analog noise source, runs those raw bits through an on-die AES-based ‘whitener’ to remove bias, and returns the resulting 256-bit block directly—no deterministic expansion, just fresh hardware entropy every call (though it’s slower and may ask you to retry when the noise FIFO is empty).

scalability of TRNGs remains an issue but that is a component problem. entropythief primarily addresses the scarcity of true "randomness," indirectly addressing scalability. it is noteworthy that entropythief randomness does not attempt to fit the traditional modern definition of randomness, which is expected to have "statistical independence, uniform distribution, and unpredictability" [1], i.e. no sequence bias, no overall bias, no pattern. entropythief does not attempt to fit the definition but rather the connotation. it is therefore not necessary, for example, to prove uniformity, but all these qualities may reasonably be assumed to be met if run indefinitely. however, the proof, imho, would negate the reality of true randomness. if the reader is interested in traditonal randomness, the reader is referred to Intel's RDSEED in combination with software CSPRNGs.

## credits
Intel provided the inline assembly to obtain random int64's from the processor [1]. entropythief was inspired by its predecessor golem app: https://github.com/reza-hackathons/gandom. the splash screen ascii art was obtained from: https://asciiart.website/index.php?art=logos%20and%20insignias/smiley

## closing thoughts
Randomness (exotic) is expensive. To get enough of it I think you literally have to steal it! This is a problem entropythief is working on but as of yet it serves as a POC with components that can be implemented in other apps where randomness or other features need to be leveraged.
