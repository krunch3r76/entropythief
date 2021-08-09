#pipe_reader
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)

import os
import json
import fcntl
import termios
import time
import select
import sys
import io



_DEBUGLEVEL = int(os.environ['PYTHONDEBUGLEVEL']) if 'PYTHONDEBUGLEVEL' in os.environ else None
"""
try:
    _DEBUGLEVEL = int(os.environ['PYTHONDEBUGLEVEL'])
except:
    _DEBUGLEVEL = None

if not _DEBUGLEVEL:
    _DEBUGLEVEL=0
"""

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
        _log_msg("opening pipe", 5)
        if not os.path.exists(self._kNamedPipeFilePathString):
            os.mkfifo(self._kNamedPipeFilePathString)
        self._fdPipe = os.open(self._kNamedPipeFilePathString, os.O_RDONLY | os.O_NONBLOCK)
        fcntl.fcntl(self._fdPipe, self._F_SETPIPE_SZ, 2**20)
        self._fdPoll.register(self._fdPipe)
        _log_msg("opened pipe", 5)



    # ........................................
    def _reopen_pipe(self):
    # ........................................
        if self._fdPipe:
            try:
                os.close(self._fdPipe)
            except OSError:
                pass
            self._fdPoll.unregister(self._fdPipe)
            self._fdPipe=None
        self._open_pipe()


    # ........................................
    def _whether_pipe_is_readable(self):
    # ........................................
        answer = False
        if not self._fdPipe:
            answer = False
        else:
            pl = self._fdPoll.poll(0)
            if len(pl) == 1:
                if pl[0][1] & 1:
                    answer=True
        return answer
    """
    def _whether_pipe_is_open(self):
        answer = True
        if not self._fdPipe:
            answer=False
        else:
            pl = self._fdPoll.poll(0)
            if len(pl) == 1:
                if pl[0][1] & 64:
                    answer = False
        return answer
    """

    # continuously read pipes until read count satisfied
    # -------------------------------------------
    def read(self, count) -> bytearray:
    # -------------------------------------------
        byte_stream = io.BytesIO()
        remainingCount = count
        while remainingCount > 0:
            """
            while not self._whether_pipe_is_open():
                self._reopen_pipe()
                time.sleep(0.01)
            """
            bytesInCurrentPipe = count_bytes_in_pipe(self._fdPipe)
            if bytesInCurrentPipe >= remainingCount:
                try:
                    _ba = os.read(self._fdPipe, remainingCount)
                except BlockingIOError:
                    _log_msg("pipe reader: BLOCKING ERROR", 5)
                    pass
                except Exception as e:
                    _log_msg(f"Other exception: {e}", 5)
                else:
                    remainingCount -= len(_ba)
                    byte_stream.write(_ba)
            elif bytesInCurrentPipe > 0:
                try:
                    _ba = os.read(self._fdPipe, bytesInCurrentPipe)
                except BlockingIOError:
                    _log_msg("blocking io error", 5)
                    pass
                except Exception as e:
                    _log_msg(f"Other exception: {e}", 5)
                    # self._reopen_pipe()
                else:
                    remainingCount -= len(_ba)
                    byte_stream.write(_ba)

                """
                if len(ba) == 0: # implies write end has been closed
                    self._reopen_pipe()
                """
            time.sleep(0.01)
        return byte_stream.getvalue()






    # -------------------------------------------
    def __del__(self):
    # -------------------------------------------
    # for now, the reader will destroy anything remaining in the pipe
        os.close(self._fdPipe)
        os.unlink(self._kNamedPipeFilePathString)



# potential issues
# undefined behavior if named pipe is deleted elsewhere

