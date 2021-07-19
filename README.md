# entropythief
**LINUX little endian (e.g. Intel chips/little endian i.e. not Raspberry Pi/ARM) only**

UPDATE: the latest release of entropythief utilizes rdrand instead of the system's entropy pool. this appears to have been a failure as preliminary findings point to an emulated cpu instruction. the project is undergoing a simultaneous regression and overhaul as i take concepts learned and built upon and apply it to the previous model. thank youe.


get random bits (aka entropy) from multiple providers utilizing Intel's RDRAND cpu instruction and send to a named pipe. requests are sent whenever the named pipe falls below a set threshold.

usage:
```
git clone https://github.com/krunch3r76/entropythief.git
cd entropythief
git checkout alpha-v5
python3 -m venv entropythief-venv
source entropythief-venv/bin/activate
pip install -r requirements.txt
./controller.py # --help # to change the network from the default rinkeby and the subnet-tag from the default devnet-beta.2
# in a separate window
cd readers/print_nonce
python3 print_nonce.py # watch how the status line changes!
# optional: tail yapapi log and/or stderr file
```

this requestor runs to pilfer as many bytes of random 1's and 0's from up to as many providers as the user specifies. these parameter(s) can be adjusted on the fly by the user with the following commands:
```
set buflim=<num>	# the minimum threshold that entropythief should do its best to stay above <DEPRECATED>
set maxworkers=<num>	# the most workers Golem executor can provision  # the more the more exotic!
stop			# stop/exit
```
NOTE: to increase the budget, please set the script variable BUDGET at the head of controller.py

__Usage/API__:
once entropythief runs, it displays the random bytes produced from workers as they arrive and are fed to the named pipe. the named pipe can be accessed via any programming language or shell language capable of reading it. a simple python API module has been included at `readers/_pipe.py`, and an example script is in `readers/print_nonce`. The script retrieves 8 bytes from the pool of /tmp/pilferedbits and prints the corresponding 64bit nonce value. _If the script is run repeatedly as a loop, it demonstrates how entropythief provisions workers on demand._


__comments/reflections__:
entropy is extremely scarce and as of now extremely expensive. but some of the most useful things in life are not scarce, take air for one. entropy (i.e. from /dev/random), though potentially a diamond of randommness where there is sufficient user io with the computer, is being phased out in favor of air ie Intel's own on-die random number generator, which is a very close approximatation to entropy and even more so because of so many foreign cpu's utilized by way of golem. it may continue to be an optional component, otherwise i may need to change the name!

this project was inspired by gandom. however, gandom does not draw upon the underlying system's entropy source (kernel/cpu), which Docker reportedly guarantees is attached to every image. furthermore, gandom mixes bytes to produce a single value whereas entropy thief provides a stream of values, which incidentally can be mixed, or played with in a myriad of ways. additionally, entropythief stores bits in raw format while presenting to the user a bird's eye view of them in the intelligible base 16 (cf. base64).


__UI components__:
```
w:<number of workers started but unfinished>/maximum>
cost:<total cost aggregated from paid invoices>/<budget>
buf:<number of random bits in units of bytes>/<maximum number of bytes "buflim">
```
on the same line that the UI accepts input, status messages are presented.
the fields are as described above.



__other components__:
```
/tmp/pilferedbits		# named pipe accessible to anyone on the system with a ski mask
./stderr			# messages and optionally yapapi logger info messages are written to this file in place of stderr
./main.log			# development messages that come from the controller are written to this file
./entropythief-yapapi.log	# INFO and DEBUG messages from yapapi
./controller.py			# controller-view runnable script that daemonizes the model (Golem executor) and coordinates with the view
./model.py			# the Golem specific code (daemonized by controller.py)
```

__applications__:
have fun with a unpredictable and exotic stream of 1's and 0's!



this application exposes undocumented parts of the Python API to handle specific events in a novel way and to filter providers. see the code for details (elaboration to follow).

known (to be fixed) issues:
once the budget has been reached, no more work is provisioned and unfinished work will be processed to completion, after which it is necessary to restart by stopping and rerunning to obtain more bits if desired.

```
TO DO: a discussion of randomness and the difference between random bits vs random number generators.
TO DO: modularize view to facilitate porting and daemonization
TO DO: windows compatible routines for named pipes (and UI)
TO DO: adjust budget on the fly
TO DO: detail design e.g. my original, self developed mvc model, etc
TO DO: develop a market strategy for better rates
TO DO: video demonstration
TO DO: improve comments
TO DO: document flow
```
