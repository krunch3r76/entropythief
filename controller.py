#!/usr/bin/env python3
# controller.py
# author: krunch3r (KJM)
# license: poetic/GPL 3

"""
    coordinate activites between the view and the model
    where the model is where Golem task execution occurs
    for more information, see README.md
"""

import model
import os
import sys
import multiprocessing
import curses
import fcntl
import termios
import select
import time
import utils
import argparse
import signal


IMAGE_HASH = "bf630610f23b1b8523d624c71e8b3f60c8fad1932ea174e00d7bc9c7"
MAXWORKERS = 6
MINPOOLSIZE = 3192
BUDGET = 0.1
kIPC_FIFO_FP = "/tmp/pilferedbits"



###############################################
#        view__getinput()                     #
#   get input and display status updates      #
###############################################
def view__getinput(winbox, linebuf, current_total, fifoWriteEnd, MINPOOLSIZE, BUDGET, MAXWORKERS, count_workers):

    # update status line
    # winbox.leaveok(True)
    Y, X = winbox.getyx()
    yMax, xMax = winbox.getmaxyx()
    current_total_str = "cost:{:.5f}".format(current_total)
    current_budget_str = "{:.5f}".format(BUDGET)
    winbox.move(Y, len(linebuf)+1)
    winbox.clrtoeol()

    winbox.addstr(Y, xMax-46, "w")
    maxworkers_str = "{:02d}".format(MAXWORKERS)
    countworkers_str = "{:02d}".format(count_workers)
    # print("{:02d}".format(1))
    winbox.addstr(Y, xMax-46+1, ":" + countworkers_str + "/" + maxworkers_str)
    winbox.addstr(Y, xMax-37, current_total_str)
    winbox.addstr(Y, xMax-37+len(current_total_str), "/"+current_budget_str)
    buf = bytearray(4)
    fcntl.ioctl(fifoWriteEnd, termios.FIONREAD, buf, 1)
    bytesInPipe = int.from_bytes(buf, "little")
    fmt = f"buf:{bytesInPipe}/{str(MINPOOLSIZE)}"
    winbox.addstr(Y, xMax-15, fmt)
    winbox.move(Y, X)
    # winbox.leaveok(False)

    ucmd = ""
    # check for new input
    s_list = select.select([sys.stdin],[],[],0)[0] # only need read set i.e. first member
    if len(s_list) > 0:
        result = s_list[0].read(1) # r[0] is <_io.TextIOWrapper name='<stdin>' mode='r' encoding='utf-8'>
        
        if ord(result) == 127:
            if len(linebuf) > 0:
                # [backspace]
                linebuf.pop()
                Y, X = winbox.getyx()
                winbox.move(0, X-1)
        elif result == '\r':
            if len(linebuf) > 0:
                ucmd = "".join(linebuf).strip()
                linebuf.clear()
                winbox.erase()
                winbox.addstr('>')
        else:
            # [char]
            linebuf.append(result[0])
            if len(linebuf) > 0:
                winbox.addstr(0, len(linebuf), linebuf[-1]) # append last character from linebuf
            else:
                winbox.addstr(0, 1, "")


    return ucmd








#---------------------------------------------#
#       view__addline()
#---------------------------------------------#
# required by view__coro_update_mainwindow()
def view__addline(win, last_col, msg):
    #    epoch = time.time()
    #    line = str(epoch)
    line = msg
    rowEnd = win.getmaxyx()[0]
    if last_col + 1 == rowEnd:
        win.scroll(1)
        last_col = last_col-1

    win.addstr(last_col, 0, line)

    return last_col+1






#####################################################
#           view__coro_update_mainwindow()                #
#####################################################
def view__coro_update_mainwindow(win, last_col):
    try:
        while True:
            msg = yield
            last_col = view__addline(win, last_col, msg)
    except GeneratorExit:
        pass








###############################################
#        view__init_curses()                        #
###############################################
# https://bytes.com/topic/python/answers/609520-curses-resizing-windows
def sigwinch_handler(n, frame):
    curses.resizeterm(curses.LINES, curses.COLS)



def view__init_curses():
    win = curses.newwin(curses.LINES-1, curses.COLS, 0,0)
    win.idlok(True)
    win.scrollok(True)
    win.leaveok(True)

    winbox = curses.newwin(1, curses.COLS, curses.LINES-1, 0)
    winbox.addstr(0, 0, ">")
    signal.signal(signal.SIGWINCH, sigwinch_handler)

    return win, winbox








###############################################
#        create_fifo_for_writing()            #
###############################################
def create_fifo_for_writing(IPC_FIFO_FP):
    # -overwrite existing
    if os.path.exists(IPC_FIFO_FP):
        os.unlink(IPC_FIFO_FP)
    os.mkfifo(IPC_FIFO_FP)
    # -/overwrite existing

    # -open
    fifo_for_writing = os.open(IPC_FIFO_FP, os.O_RDWR | os.O_NONBLOCK)
    # -/open
    return fifo_for_writing







##########################################################
#                      __main__                          #
##########################################################
if __name__ == "__main__":
    # parse cli arguments
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--subnet", type=str, default="devnet-beta.2")
    arg_parser.add_argument("--network", type=str, default=None)
    args = argparse.Namespace()
    parser = utils.build_parser("pipe entropy to the named pipe /tmp/pilferedbits")
    parser.set_defaults(log_file=f"entropythief-yapapi.log")
    args = parser.parse_args()


    maindebuglog = open("main.log", "w", buffering=1)
    stderr2file = open("stderr", "w", buffering=1)
    sys.stderr = stderr2file

    # set up {to_,from_}_model_queue
    to_model_q = multiprocessing.Queue()  # message queue TO golem executor process
    from_model_q = multiprocessing.Queue()  # message queue FROM golem executor process

    # setup fifo
    fifoWriteEnd = create_fifo_for_writing(kIPC_FIFO_FP)

    # initialize ncurses interface
    screen = curses.initscr()
    curses.cbreak()
    linebuf = []
    try:
        win, winbox = view__init_curses()
        # start view process
        p1 = multiprocessing.Process(target=model.model__main, daemon=True, args=[args, to_model_q, fifoWriteEnd, from_model_q, MINPOOLSIZE, MAXWORKERS, BUDGET, IMAGE_HASH])
        p1.start()
        last_col = 0
        u = view__coro_update_mainwindow(win, last_col)
        next(u)
        current_total = 0.0
        count_workers=0
        SIGNAL_workerstarted = False
        while True:
            ucmd = view__getinput(
                winbox, linebuf, current_total, fifoWriteEnd, MINPOOLSIZE, BUDGET, MAXWORKERS, count_workers)
        #    SIGNAL_workerstarted = False   # regardless of last state, reset
            msg_to_model = None
            if ucmd == "stop":
                raise KeyboardInterrupt
            elif 'set buflim=' in ucmd:
                tokens = ucmd.split("=")
                MINPOOLSIZE = int(tokens[-1])
                msg_to_model = {'cmd': 'set buflim', 'limit': MINPOOLSIZE}
                to_model_q.put_nowait(msg_to_model)
            elif 'set maxworkers=' in ucmd:
                tokens = ucmd.split("=")
                MAXWORKERS = int(tokens[-1])
                msg_to_model = {'cmd': 'set maxworkers', 'count': MAXWORKERS}
                to_model_q.put_nowait(msg_to_model)
            elif ucmd=='restart':
                msg_to_model = {'cmd': 'restart' }
                to_model_q.put_nowait(msg_to_model)
            if msg_to_model:
                print(msg_to_model, file=maindebuglog)
            #/if
            if not from_model_q.empty():
                msg_from_model = from_model_q.get_nowait()
                print(msg_from_model, file=maindebuglog)
                if 'cmd' in msg_from_model and msg_from_model['cmd'] == 'add_bytes':
                    msg = msg_from_model['hexstring']
                    result = u.send(msg)
                elif 'cmd' in msg_from_model and msg_from_model['cmd'] == 'update_total_cost':
                    current_total = msg_from_model['amount']
                elif 'exception' in msg_from_model:
                    raise Exception(msg_from_model['exception'])
                elif 'info' in msg_from_model and msg_from_model['info'] == 'worker started':
                    count_workers+=1
                elif 'info' in msg_from_model and msg_from_model['info'] == 'worker finished':
                    count_workers-=1
                elif 'info' in msg_from_model and msg_from_model['info'] == "payment failed":
                    msg_to_model = {'cmd': 'pause execution'}
                    print(msg_to_model, file=maindebuglog)
                    to_model_q.put_nowait(msg_to_model)

            #/if
            win.refresh()
            winbox.refresh()
            time.sleep(0.005)
        #/while
    except Exception as e:
        curses.endwin()
        print(e)
    except KeyboardInterrupt:
        curses.endwin()
        print("+=+=+=+=+=+=+=stopping=+=+=+=+=+=+=")
    finally:
        curses.nocbreak()
        curses.echo()
        curses.curs_set(True)
        curses.endwin()
        cmd = {'cmd': 'stop'}
        to_model_q.put_nowait(cmd)
        p1.join()
        while not from_model_q.empty():
            msg_from_model = from_model_q.get_nowait()
            print(msg_from_model, file=maindebuglog)
            if 'cmd' in msg_from_model and msg_from_model['cmd'] == 'update_total_cost':
                current_total = msg_from_model['amount']
            elif 'exception' in msg_from_model:
                raise Exception(msg_from_model['exception'])
        print("Costs incurred were: " + str(current_total) + ".\nOn behalf of the Golem Community, thank you for your participation.")
        maindebuglog.close()
        stderr2file.close()
        # instead of closing the write end, leave it open for any pending bits that may be needed by a reader
        os.close(fifoWriteEnd)
        os.unlink(kIPC_FIFO_FP)
