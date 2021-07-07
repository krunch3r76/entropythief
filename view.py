import curses
import curses.ascii
import sys
import fcntl
import termios
import string














   ###################################
  # view__init_curses()             #
 ###################################
 # required by View::_init_screen
def view__create_windows(view):
    win = curses.newwin(curses.LINES-1, curses.COLS, 0,0)
    win.idlok(True)
    win.scrollok(True)

    popupwin = win.subwin(int(curses.LINES/5), int(curses.COLS/4), int(curses.LINES/2), int(curses.COLS/4))
    """
    popupwin.box()
    Y, X = popupwin.getmaxyx()
    msg = "what's up doc?"
    print(Y,X,len(msg) + 3, file=sys.stderr)
    popupwin.addstr(int(Y/2), 3, msg)
    popupwin.refresh()
    """

    winbox = curses.newwin(1, curses.COLS, curses.LINES-1, 0)
    winbox.addstr(0, 0, ">")
    winbox.nodelay(True)

    return { 'outputfield': win, 'inputfield': winbox, 'popup': popupwin }











def _count_bytes_in_pipe(fifoWriteEnd, endianness="little"):
    buf = bytearray(4)
    fcntl.ioctl(fifoWriteEnd, termios.FIONREAD, buf, 1)
    bytesInPipe = int.from_bytes(buf, endianness)
    return bytesInPipe







class View:
    winbox = None
    win = None
    linebuf = []
    fifoWriteEnd = None





    def _init_screen(self):
        try:
            self.screen = curses.initscr() 
            curses.noecho()
            curses.cbreak()

            windir = view__create_windows(self)
            self.win = windir['outputfield']
            self.winbox = windir['inputfield']

            # self.win, self.winbox, self.popupwin = view__create_windows(self)
        except Exception as e:
            curses.nocbreak()
            curses.echo()
            curses.curs_set(True)
            curses.endwin()
            raise







    def __init__(self, fifoWriteEnd):
        self._init_screen()
        self.fifoWriteEnd = fifoWriteEnd






    def addline(self, msg):
        Y, X = self.win.getyx()
        self.win.addstr(Y, X, msg)






    def coro_update_mainwindow(self):
        try:
            while True:
                msg = yield
                self.addline(msg)
        except GeneratorExit:
            pass





    def refresh(self):
        self.win.refresh()
        self.winbox.refresh()






    def getinput(self, current_total, MINPOOLSIZE, BUDGET, MAXWORKERS, count_workers):
        # update status line
        Y, X = self.winbox.getyx()
        yMax, xMax = self.winbox.getmaxyx()
        current_total_str = "cost:{:.5f}".format(current_total)
        current_budget_str = "{:.5f}".format(BUDGET)
        maxworkers_str = "{:02d}".format(MAXWORKERS)
        countworkers_str = "{:02d}".format(count_workers)
        bytesInPipe = _count_bytes_in_pipe(self.fifoWriteEnd)

        self.winbox.move(Y, len(self.linebuf)+1)
        self.winbox.clrtoeol()
        self.winbox.addstr(Y, xMax-46, "w")
        self.winbox.addstr(Y, xMax-46+1, ":" + countworkers_str + "/" + maxworkers_str)
        self.winbox.addstr(Y, xMax-37, current_total_str)
        self.winbox.addstr(Y, xMax-37+len(current_total_str), "/"+current_budget_str)
        self.winbox.addstr(Y, xMax-15, f"buf:{bytesInPipe}/{str(MINPOOLSIZE)}")
        self.winbox.move(Y, X)

        ucmd = ""
        result = self.winbox.getch()
        if curses.ascii.isascii(result):
            if result == 127:
                if len(self.linebuf) > 0:
                    # [backspace]
                    self.linebuf.pop()
                    Y, X = self.winbox.getyx()
                    self.winbox.move(0, X-1)
            elif result == ord('\n'):
                if len(self.linebuf) > 0:
                    ucmd = "".join(self.linebuf).strip()
                    self.linebuf.clear()
                    self.winbox.erase()
                    self.winbox.addstr('>')
            elif chr(result) in string.printable:
                # [char]
                self.linebuf.append(chr(result))
                if len(self.linebuf) > 0:
                    self.winbox.addstr(0, len(self.linebuf), self.linebuf[-1]) # append last character from linebuf
                else:
                    self.winbox.addstr(0, 1, "")
        elif result == curses.KEY_RESIZE:
            self.winbox.move(0,0)
            self.winbox.addstr('>')
            self.winbox.addnstr(0, 1, "".join(self.linebuf), len(self.linebuf))
            curses.update_lines_cols()
            self.win.resize(curses.LINES-1,curses.COLS)
            self.win.redrawwin()
            self.winbox.mvwin(curses.LINES-1, 0)
            self.winbox.redrawwin()
        # /if
        return ucmd










    def destroy(self):
        curses.nocbreak()
        curses.echo()
        curses.curs_set(True)
        curses.endwin()
