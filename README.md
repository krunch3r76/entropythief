# entropythief

get entropy from multiple providers at a "steal" of a rate and send to a named pipe. requests are sent whenever the named pipe falls below a set threshold.

usage:
```
git clone https://github.com/krunch3r76/entropythief.git
cd entropythief
git checkout alpha
python3 -m venv entropythief-venv
source entropythief-venv/bin/activate
pip install -r requirements.txt
./controller.py
# in a separate window
cd readers/print_nonce
python3 print_nonce.py # watch how the status line changes!
# optionall tail yapapi log and/or stderr file
```

this requestor runs to pilfer as many bytes of random 1's and 0's from as many providers as the user specifies. these parameters can be adjusted on the fly by the user with the following commands:
```
set buflim=<num>	# the minimum threshold that entropythief should do its best to stay above
set maxworkers=<num>	# the most workers Golem executor can provision
stop			# stop/exit
```


UI components:

```
w:<number of workers started but unfinished "maxworkers">/maximum>
cost:<total cost aggregated from paid invoices>/<budget>
buf:<number of random bits in units of bytes>/<maximum number of bytes "buflim">
```
on the same line that the UI accepts input, status messages are presented.
the fields are as described above.

once entropythief runs, it displays the random bytes produced from workers as they arrive and are fed to the named pipe. the named pipe can be accessed via any progamming language or shell language capable of reading it. a simple python API has been included in the readers directory, _pipe, and an example script is in readers/print_nonce. The script retrieves 8 bytes from the pool of /tmp/pilferedbits and prints the corresponding 64bit nonce value. If the script is run repeatedly as a loop, it demonstrates how entropythief provisions workers on demand.


components:
```
/tmp/pilferedbits		# named pipe accessible to anyone on the system with a ski mask recommended
./stderr			# messages and optionally yapapi logger info messages are written to this file in place of stderr
./main.log			# development messages that come from the controller are written to this file
./entropythief-yapapi.log	# INFO and DEBUG messages from yapapi
./controller.py			# controller-view runnable script that daemonizes the model (Golem executor) and coordinates with the view
./model.py			# the Golem specific code (daemonized by controller.py)
```




```
TO DO: a discussion of randomness and the difference between random bits vs random number generators.
TO DO: windows compatible routines for named pipes and UI
TO DO: adjust budget on the fly
TO DO: detail design, original, self developed mvc model, etc
```
applications:
have fun with a unpredictable and exotic stream of 1's and 0's!

comments:
entropy is scarce. i will develop a discussion file to elaborate on that later. that said, it is so rare, that even a high rate might be considered a steal. or, you might consider it the other way around!

this project was inspired by gandombits. however, gandom does not draw upon the underlying system's entropy source, which Docker reportedly guarantees is attached to every image. furthermore, gandom mixes bytes to produce a single value whereas entropy thief provides a stream of values, which incidentally can be mixed, or played with in a myriad of ways. additionally, entropythief stores bits in raw format while presenting to the user a bird's eye view of them in the intelligible base 16 (cf. base64).

known (fixable someday) issues:
you might have some issues with tearing of the command/status line when resizing the window.
