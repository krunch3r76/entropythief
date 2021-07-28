import os
import json
import fcntl
import termios
import time
import select
import sys

#pipe_reader




try:
    _DEBUGLEVEL = int(os.environ['PYTHONDEBUGLEVEL'])
except:
    _DEBUGLEVEL = None

if not _DEBUGLEVEL:
    _DEBUGLEVEL=0


def _log_msg(msg, debug_level=0, file=sys.stderr):
    pass
    if debug_level <= _DEBUGLEVEL:
        print(msg, file=file)






#****************************************
def count_bytes_in_pipe(fd):
#****************************************
    buf = bytearray(4)
    fcntl.ioctl(fd, termios.FIONREAD, buf, 1)
    bytesInPipe = int.from_bytes(buf, "little")
    return bytesInPipe





#******************{}********************
class PipeReader:
#******************{}********************
    _kNamedPipeFilePathString = '/tmp/pilferedbits'
    _fdPipe = None
    _fdPoll = select.poll()
    _F_SETPIPE_SZ = 1031


    

    # --------------------------------------
    def __init__(self):
    # --------------------------------------
        self._open_pipe()

    # .......................
    def _open_pipe(self):
    # .......................
        if not os.path.exists(self._kNamedPipeFilePathString):
            os.mkfifo(self._kNamedPipeFilePathString)
        self._fdPipe = os.open(self._kNamedPipeFilePathString, os.O_RDONLY | os.O_NONBLOCK)
        fcntl.fcntl(self._fdPipe, self._F_SETPIPE_SZ, 2**20)
        self._fdPoll.register(self._fdPipe)

    """
    def _reopen_pipe(self):
        try:
            os.close(self._fdPipe)
        except OSError:
            pass
        self._fdPoll.unregister(self._fdPipe)
        self._fdPipe=None
    """

    # ........................................
    def _whether_pipe_is_readable(self):
    # ........................................
        answer = False
        pl = self._fdPoll.poll(0)
        if len(pl) == 1:
            if pl[0][1] & 1:
                answer=True
        return answer




    # continuously read pipes until read count satisfied
    # -------------------------------------------
    def read(self, count) -> bytearray:
    # -------------------------------------------
        rv = bytearray()
        remainingCount = count
        while remainingCount > 0:
            if self._whether_pipe_is_readable():
                bytesInCurrentPipe = count_bytes_in_pipe(self._fdPipe)
                ba = None
                if bytesInCurrentPipe >= remainingCount:
                    while ba is None:
                        try:
                            ba = os.read(self._fdPipe, remainingCount)
                                # _log_msg("read", 1)
                        except BlockingIOError:
                            _log_msg("error")
                            pass
                        else:
                            remainingCount = 0
                else:
                    while ba is None:
                        try:
                            ba = os.read(self._fdPipe, bytesInCurrentPipe)
                        except BlockingIOError:
                            # _log_msg("error")
                            pass
                        else:
                            remainingCount -= bytesInCurrentPipe
                """
                if len(ba) == 0: # implies write end has been closed
                    self._reopen_pipe()
                """
                rv.extend(ba)
            time.sleep(0.001)

        return rv






    # -------------------------------------------
    def __del__(self):
    # -------------------------------------------
    # for now, the reader will destroy anything remaining in the pipe
        os.close(self._fdPipe)
        os.unlink(self._kNamedPipeFilePathString)




