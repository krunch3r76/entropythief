# entropythief

**A golem requestor installation is needed to run this app. Please visit https://www.golem.network for details**

get random entropy at a steal of a rate from multiple providers utilizing the linux entropy source or Intel's RDRAND cpu instruction (default). requests are sent whenever the named pipe falls below half the set threshold. 

# video demo
https://krunch3r76.github.io/entropythief

# non technical description
computers can provide random numbers; however, hardware designs make such number sequences somewhat predictable. entropythief has several computers produce random numbers and chops and mixes them to make an unpredictable sequence of never before seen random numbers, like snowflakes. randomness in computers has many scientific and practical applications and may have applications in art. entropythief makes no claims on the quality of randomness but does facilitate reprogramming to refine or improve the results. at any rate, entropythief may be summed up as a faucet of random 1's and 0's.

# usage:
```
git clone https://github.com/krunch3r76/entropythief.git
cd entropythief
git checkout v1.0.0
python3 -m venv entropythief-venv
source entropythief-venv/bin/activate
pip install -r requirements.txt
./entropythief.py # --help # to change the network from the default rinkeby and the subnet-tag from the default devnet-beta.2

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
# API:
once entropythief runs, it displays the random bytes produced from workers as they arrive and are fed to a named pipe, topping it off. the named pipe can accessed via any programming language and a sample Python API is provided at `readers/pipe_reader.py`, and an example script is in `readers/print_nonce`. The script retrieves 8 bytes from the pool of /tmp/pilferedbits and prints the corresponding 64bit nonce value. 


# comments/reflections:

this project was inspired by gandom. however, gandom does not draw upon the underlying system's entropy source (kernel/cpu), which Docker reportedly guarantees is attached to every image. furthermore, gandom mixes bytes to produce a single value whereas entropy thief provides a stream of values, which incidentally are mixed by default, and can be played with in a myriad of ways. additionally, entropythief stores bits in raw format while presenting to the user a bird's eye view of them in the intelligible base 16 (cf. base64).


# UI components:
```
w:<number of workers started but unfinished>/maximum>
cost:<total cost aggregated from paid invoices>/<budget>
buf:<number of random bits in units of bytes>/<maximum number of bytes "buflim">
```
on the same line that the UI accepts input, status messages are presented.
the fields are as described above.



# other components:
```
./stderr                  # messages and optionally yapapi logger info messages are written to this file in place of stderr
./main.log                # development messages that come from the controller are written to this file
./entropythief-yapapi.log # INFO and DEBUG messages from yapapi
./entropythief.py         # controller-view runnable script that daemonizes the model (Golem executor) and coordinates with the view
./model.py                # the Golem specific code (daemonized by controller.py)
./worker_public.py        # public namespace for variables etc needed by requestor to interact with the provider/vm
./TaskResultWriter.py	  # base and derived TaskResultWriter (including Interleaver)
./pipe_writer.py          # buffered named pipe writer
./readers/pipe_reader.py  # API to named pipe
/tmp/pilferedbits         # named pipe to which the buffered writes continually occur as needed to top off
./Dockerfile              # for vm creation
./worker.py               # for vm creation
./randwriter.c            # for vm, compiled into worker executable
```

# applications:
have fun with a unpredictable and exotic stream of 1's and 0's!



this application exposes undocumented parts of the Python API to handle specific events in a novel way and to filter providers. see the code for details (elaboration to follow).

```
TO DO: video demonstration
TO DO: UI view of log messages or other interesting network activity
TO DO: a discussion of randomness and the difference between random bits vs random number generators.
TO DO: windows compatible routines for named pipes (and UI)
TO DO: develop an improved market strategy for better rates
```

## CREDITS
Intel provided the inline assembly to obtain random int64's from the processor. entropythief was inspired by its predecessor golem app: https://github.com/reza-hackathons/gandom. the splash screen ascii art was obtained from: https://asciiart.website/index.php?art=logos%20and%20insignias/smiley

## Reflections:
Randomness (exotic) is expensive. To get enough of it I think you literally have to steal it! This is a problem entropy thief is working on but as of yet it serves as a POC with components that can be implemented in other apps where randomness or other features need to be leveraged.
