import sys
import fcntl
import termios
from functools import wraps


def cache_byteorder(func):
    """prevent uncessary calls to sys.byteorder"""
    byteorder = sys.byteorder

    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs, byteorder=byteorder)

    return wrapper


@cache_byteorder
def count_bytes_in_pipe(fd, byteorder=None) -> int:
    """
    check how many bytes are stored in the named pipe for reading at the moment

    pre:
        - named pipe size is 1 megabyte (1,048,576) or less in length
    in:
        fd: file descriptor to pipe
        byteorder: stub to wrapped sys call cached by decorator

    out: the number of bytes currently available to be read from the pipe
    """

    buf = bytearray(4)
    fcntl.ioctl(fd, termios.FIONREAD, buf, 1)
    bytesInPipe = int.from_bytes(buf, byteorder)
    return bytesInPipe
