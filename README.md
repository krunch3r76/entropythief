# entropythief
**LINUX little endian (e.g. Intel chips/little endian i.e. not Raspberry Pi/ARM) only**
**A golem requestor installation is needed to run this app. Please visit https://www.golem.network for details**

get random entropy at a steal of a rate from multiple providers utilizing the linux entropy source or Intel's RDRAND cpu instruction (default). requests are sent whenever the named pipe falls below a half the set threshold. 

usage:
```
git clone https://github.com/krunch3r76/entropythief.git
cd entropythief
git checkout alpha-v7.10 # note, the (multiple) named pipe model is being revised as too many causes problems
python3 -m venv entropythief-venv
source entropythief-venv/bin/activate
pip install -r requirements.txt
./entropythief.py # --help # to change the network from the default rinkeby and the subnet-tag from the default devnet-beta.2

# in a separate window
cd readers/print_nonce
python3 print_nonce.py # watch how the status line changes!
# optional: tail yapapi log and/or stderr file
```

this requestor runs to pilfer as many bytes of random 1's and 0's from up to as many providers as the user specifies. these parameter(s) can be adjusted on the fly by the user with the following commands:
```
set buflim=<num>      # the minimum threshold that entropythief should do its best to stay above (refills when it falls beneath half this value)
set maxworkers=<num>  # the most workers Golem executor can provision  # the more the more exotic!
set budget=<float>    # the budget above which work should cease (unless this is used to increase the budget)
restart               # after so many payment failures or after budget is exceeded, budget is implied to be over the limit. after setting run this.
stop                  # stop/exit
```

try:
`set buflim=1000*2**20` for 1 gigabyte of random data

and `set maxworkers=13` across 13 workers

__Usage/API__:
once entropythief runs, it displays the random bytes produced from workers as they arrive and are fed to a named pipe, topping it off. the named pipe can accessed via any programming language and a sample Python API is provided at `readers/pipe_reader.py`, and an example script is in `readers/print_nonce`. The script retrieves 8 bytes from the pool of /tmp/pilferedbits and prints the corresponding 64bit nonce value. 


__comments/reflections__:

this project was inspired by gandom. however, gandom does not draw upon the underlying system's entropy source (kernel/cpu), which Docker reportedly guarantees is attached to every image. furthermore, gandom mixes bytes to produce a single value whereas entropy thief provides a stream of values, which incidentally can be mixed, or played with in a myriad of ways. additionally, entropythief stores bits in raw format while presenting to the user a bird's eye view of them in the intelligible base 16 (cf. base64).


__UI components__:
```
w:<number of workers started but unfinished>/maximum>
cost:<total cost aggregated from paid invoices>/<budget>
buf:<number of random bits in units of bytes>/<maximum number of bytes "buflim">
```
on the same line that the UI accepts input, status messages are presented.
the fields are as described above.



__other components__: note, some of these components are upstream of alpha-v6
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
./rdrand.c                # for vm, python c extension to access rdrand (utilized upon construction of image)
./build.sh                # for vm, utilized by Docker image to create a c based python extension module (from  rdrand.c)
```

__applications__:
have fun with a unpredictable and exotic stream of 1's and 0's!



this application exposes undocumented parts of the Python API to handle specific events in a novel way and to filter providers. see the code for details (elaboration to follow).

```
TO DO: UI view of log messages or other interesting network activity
TO DO: a discussion of randomness and the difference between random bits vs random number generators.
TO DO: further modularize/abstract view to facilitate porting and daemonization
TO DO: windows compatible routines for named pipes (and UI)
TO DO: detail design e.g. my original, self developed mvc model, etc
TO DO: develop a market strategy for better rates
TO DO: video demonstration
TO DO: improve comments
TO DO: document flow
```

CREDITS TO ADD TO SOURCE: Intel provided the inline assembly to obtain random int64's from the processor.

Reflections:
Randomness (exotic) is expensive. To get enough of it I think you literally have to steal it! This is a problem entropy thief is working on but as of yet it serves as a POC with components that can be implemented in other apps where randomness or other features need to be leveraged.
