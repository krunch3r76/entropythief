import os
import json
import fcntl
import termios
import time

#pipe_reader

def count_bytes_in_pipe(fd):
    buf = bytearray(4)
    fcntl.ioctl(fd, termios.FIONREAD, buf, 1)
    bytesInPipe = int.from_bytes(buf, "little")
    return bytesInPipe


class PipeReader:
    _pipes = { } # { name: INT }
    _mtimeDat = 0.0 # last recorded modification time
    _datfile = None
    _filepathDatFile = "/tmp/pilferedbits.dat"
    def __init__(self):
        pass

    def _resolve_name(self, name):
        return f"/tmp/{name}"

    def _add_name(self, name):
        # open the named pipe and store name:descriptor in _pipes
        fd = os.open(self._resolve_name(name), os.O_RDONLY | os.O_NONBLOCK)
        self._pipes[name]=fd

    def _update_names(self):
        with open(self._filepathDatFile) as fpDatFile:
            names = json.load(fpDatFile)
            if names not None: # testing
                for name in names:
                    if name not in self._pipes:
                        self._add_name(name)
                for name in self._pipes.keys():
                    if name not in names:
                        del self._pipes[name]

    # continuously read pipes until read count satisfied
    def read(self, count) -> bytearray:
        # TODO, check for exceptions and reopen pipes if necessary
        # this is needed when the pipes have been closed and reopened under the same name
        # or different names. try different approaches, examine exceptions on failed read?

        rv = bytearray()
        if not os.path.exists(self._filepathDatFile):
            return 0
        # [ datfile exists ]

        mtimeDat = os.path.getmtime(self._filepathDatFile)
        if mtimeDat > self._mtimeDat:
            self._mtimeDat = mtimeDat
            self._update_names()
        # [ _pipes up to date ]

        
        remainingCount = count
        while remainingCount > 0:
            for fd in self._pipes.values():
                bytesInCurrentPipe = count_bytes_in_pipe(fd)
                if bytesInCurrentPipe >= remainingCount:
                    ba = os.read(fd, remainingCount)
                    remainingCount = 0
                else:
                    ba = os.read(fd, bytesInCurrentPipe)
                    remainingCount -= bytesInCurrentPipe
                rv.extend(ba)
            time.sleep(0.01)

        return rv


