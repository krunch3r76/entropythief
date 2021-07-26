import fcntl
import os,sys
import asyncio
import termios
import json
import io
from functools import singledispatchmethod
import select

  #-------------------------------------------------#
 #           write_to_pipe                         #
#-------------------------------------------------#
# required by: entropythief()
# nonblocking io!
def write_to_pipe(fifoWriteEnd, thebytes, POOL_LIMIT):
    """
    fifoWriteEnd:
    thebytes:
    POOL_LIMIT:
    """
    WRITTEN = 0
    try:

        buf = bytearray(4)
        fcntl.ioctl(fifoWriteEnd, termios.FIONREAD, buf, 1)
        bytesInPipe = int.from_bytes(buf, "little")
        bytesNeeded = POOL_LIMIT - bytesInPipe

        count_to_write = 0
        if bytesNeeded > 0:
            count_to_write = len(thebytes)
            if count_to_write + bytesInPipe > POOL_LIMIT:
                count_to_write = POOL_LIMIT - bytesInPipe 
            if count_to_write > len(thebytes): #review
                count_to_write = len(thebytes)
            count_remaining = count_to_write
            WRITTEN = os.write(fifoWriteEnd, thebytes[:count_remaining])
        return WRITTEN
    except BlockingIOError:
        print(f"write_to_pipe: COULD NOT WRITE. count_remaining = {count_remaining}. bytes in pipe = {bytesInPipe}", file=sys.stderr)
        WRITTEN=0
        pass
    except BrokenPipeError:
        WRITTEN=0
        print("BROKEN PIPE--------------------------------------", file=sys.stderr)
        raise
    except Exception as exception:
        print("write_to_pipe: UNHANDLED EXCEPTION", file=sys.stderr)
        print(type(exception).__name__, file=sys.stderr)
        print(exception, file=sys.stderr)
        raise asyncio.CancelledError #review
    finally:
        return WRITTEN



def get_bytes_in_pipe(fd):
    buf = bytearray(4)
    fcntl.ioctl(fd, termios.FIONREAD, buf, 1)
    bytesInPipe = int.from_bytes(buf, "little")
    return bytesInPipe






class PipeWriter:
    _pipes = { } # { name: INT }
    _F_SETPIPE_SZ=1031
    _PIPECAPACITY=2**20 - 4096
    _datfile = None

    def __init__(self):
        # create initial pipe
        self._datfile = open("/tmp/pilferedbits.dat", "w")
        self._add_pipe()

    @singledispatchmethod
    def _report_free(self, fd: int) -> int:
        bytesInPipe = get_bytes_in_pipe(fd)
        # print(f"KDEBUG: bytesInPipe: {bytesInPipe}, returning {self._PIPECAPACITY - bytesInPipe}", file=sys.stderr)
        return self._PIPECAPACITY - bytesInPipe


    @_report_free.register
    def _(self, name: str):
        fd = self._pipes[name]
        return self._report_free(fd)


    def _report_total_free(self):
        total_free=0
        for fd in self._pipes.values():
            total_free += self._report_free(fd)
        return total_free


    def len(self):
        bytesInPipes=0
        for fd in self._pipes.values():
            bytesInPipes += get_bytes_in_pipe(fd)
        return bytesInPipes

    def _resolve_name(self, name):
        return f"/tmp/{name}"

    def _add_pipe(self):
        # search for highest numbered suffix in pipe_name or use 1
        # try to create as candidate, increment until successful
        max = 0
        for key in self._pipes.keys():
            index = int(key.split("_")[1])
            if index > max:
                max = index
        max+=1
        while os.path.exists("/tmp/pilferedbits_" + str(max)):
            max+=1
        name = "pilferedbits_" + str(max)
        os.mkfifo(self._resolve_name(name))
        fd = os.open(self._resolve_name(name), os.O_RDWR | os.O_NONBLOCK)
        try:
            fcntl.fcntl(fd, self._F_SETPIPE_SZ, 2**20)
        except OSError:
            # could not for whatever reason adjust up the pipe size
            # nothing to do but accept the system imposed limit
            pass

        self._pipes[name] = fd

        # update dat file
        namedList = []
        for key in self._pipes.keys():
            namedList.append(key)
        jsonarray = json.dumps(namedList)
        self._datfile.truncate(0)
        self._datfile.seek(0)
        self._datfile.write(jsonarray)
        self._datfile.flush()
        print(f"PipeWriter: {jsonarray}", file=sys.stderr)


    def _filter_ready_fds(self):
        candidate_fds = []
        writable_fds = []
        for fd in self._pipes.values():
            candidate_fds.append(fd)
        s = select.select([], candidate_fds, candidate_fds, 0)
        wlist = s[1]
        for wfd in wlist:
            writable_fds.append(wfd)
        for efd in s[2]:
            if efd in writable_fds:
                writable_fds.remove(efd)
        return writable_fds

    def _query_pipe_len(self, name) -> int:
        pass

    def write(self, bytes):
        print(f"KDEBUG: received request to write {len(bytes)} bytes", file=sys.stderr)
        # pre, bytes len > 0
        # iterate to next pipe with available capacity
        # [ available capacity > bytes ]  write bytes
        # [!] write available capacity, move offset, continue

        offset = 0
        bytes_end = len(bytes)
        while offset < bytes_end:
            # here we need to filter the fds that are ready for writing (and maybe
            # not in an exception state)

#            for fd in self._pipes.values():
            for fd in self._filter_ready_fds():
                avail = self._report_free(fd)
                # write to pipe if not full
                if avail > 0:
                    if avail > bytes_end - offset:
                        write_to_pipe(fd, bytes[offset:bytes_end], self._PIPECAPACITY)

#                        write_to_pipe(fd, bytes[offset:bytes_end], self._PIPECAPACITY)
                        offset=bytes_end
                    else:
                        write_to_pipe(fd, bytes[offset:(offset+avail)], self._PIPECAPACITY)
                        offset+=avail
            # current pipes have been filled, any remaining bytes will be added to new pipes
            if offset < bytes_end:
                # determine how many more pipes of size _PIPECAPACITY needed to fulfill write request
                bytes_to_go = bytes_end - offset
                if bytes_to_go <= self._PIPECAPACITY:
                    count = 1
                else:
                    count = int(bytes_to_go/self._PIPECAPACITY)
                    if bytes_to_go % self._PIPECAPACITY != 0:
                        count+=1
                for _ in range(count):
                    self._add_pipe()
            # continue until everything has been written
        print(f"KDEBUG: WRITTEN, REMAINING {bytes_end}", file=sys.stderr)
        return bytes_end # for compatibility, but it is guaranteed to write as much as there is

    def __del__(self):
        print("PipeWriter: DELETING SELF", file=sys.stderr)
        for key, val in self._pipes.items():
            try:
                os.close(val)
            except:
                pass
            try:
                print(f"PipeWriter: unlinking /tmp/{key}", file=sys.stderr)
                os.unlink(f"/tmp/{key}")
            except:
                pass
        try:
            print(f"PipeWriter: unlinking {self._datfile}", file=sys.stderr)
            os.unlink(self._datfile)
        except:
            pass

