# view
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)

import curses
import curses.ascii
import curses.panel
import sys
import fcntl
import termios
import string



# define the main text window
class Display:
    ENABLE_SPLASH = False
    ENABLE_SPLASH_1 = False
    _widget = None
    _splash = None

    # define the _splash window
    class Splash:
        _txt = ""                   # retains the last contents written to the _splash window
        _parent_display = None      # retains a reference to the window _splashed i.e. Display
            
        #^^^^Splash^^^^^^^^^^^^^^^^^^^^^^#
        #^     _refresh_coords          ^#
        #^ make *args for pad refresh   ^#
        #^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^#
        def _refresh_coords(self):
            # makes Splash 1/3 the height of subwindow
            yBegParent, xBegParent = self._parent_display._widget.getbegyx()
            Ymax, Xmax = self._parent_display._widget.getmaxyx()
            height3rd = int( (Ymax-yBegParent)/3)
            width3rd = int( (Xmax-xBegParent)/3)

            yBeg = yBegParent + height3rd
            xBeg = xBegParent + height3rd
            nlines = height3rd
            ncols = width3rd
            return 0, 0, yBeg, xBeg, yBeg+nlines, xBeg+ncols


        #^^^^Splash^^^^^^^^^^^^^^^^^^^^^^#
        #^           refresh            ^#
        #^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^#
        def refresh(self):
            # refresh & resize display with coords from _refresh_coords
            if self._parent_display:
                self._widget.refresh(*self._refresh_coords())
            
        """
        def refresh0(self):
            if self._parent_display:
                self._widget.refresh(0, 0, 0, 0, 0, 0)

        def noutrefresh(self):
            self._widget.noutrefresh(*self._refresh_coords())
        """


        #^^^^Splash^^^^^^^^^^^^^^^^^^^^^^#
        #^         __init__             ^#
        #^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^#
        def __init__(self, display):
            self._parent_display = display
            coords = self._refresh_coords()
            nlines = coords[4]-coords[2]; ncols = coords[5]-coords[3]
            self._widget = curses.newpad(nlines, ncols)
            self._widget.box()
            self._widget.syncok(True)
            # self._widget.immedok(True)



        #^^^^Splash^^^^^^^^^^^^^^^^^^^^^^#
        #^      replace contents        ^#
        #^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^#
        def text(self, txt):
            coords = self._refresh_coords()
            heightSplash = coords[4]-coords[2] # height of splash
            widthSplash = coords[5]-coords[3] # width of splash

            self._txt = txt
            txtLines = self._txt.split('\n')
            txtLines_len = len(txtLines) + 1 # include horizontal bar

            # resize overfit on height to fit
            # account for 1: top bar, 2 separator, 3 bottom bar
            if heightSplash > txtLines_len + 3:
                heightSplash = txtLines_len + 3
            self._widget.resize(heightSplash, widthSplash)
            self._widget.clear()
            self._widget.box()

            yBeg, xBeg = self._widget.getbegyx()
            height = heightSplash
            width = widthSplash
            # height, width = self._widget.getmaxyx()
            y=1; x=1
            if txtLines_len > 0 and height > 3:
                # draw first line
                self._widget.addstr(y, x, f"%.{width-2}s" % txtLines[0])
                y=y+1
                # draw separator
                self._widget.hline(y,0, curses.ACS_LTEE, 1)
                self._widget.hline(y,1, curses.ACS_HLINE, width-2)
                self._widget.hline(y,width-1, curses.ACS_RTEE, 1)

                # how many of the remaining lines can fit
                rangeMax = height - 3 - 1
                # 1: topbar, 2:sep, 3:bot bar, 1: first line
                # write text
                for i in range(1, rangeMax):
                    self._widget.addstr(y+i, x, f"%.{width-2}s" % txtLines[i])



    #....Display....................#
    #.          __init__           .#
    #...............................#
    def __init__(self):
        self._widget = curses.newwin(curses.LINES-1, curses.COLS, 0, 0)
        self._widget.idlok(True); self._widget.scrollok(True)
        self._splash = self.Splash(self)
        txt=\
"""EntropyThief >cmd reference
>set buflim=<NUM>
>set maxworkers=<NUM>
>stop
<ESC> toggle this menu
"""
        self._splash.text(txt)
        self._widget.leaveok(True)




    #....Display....................#
    #.          appendtxt          .#
    #. append to end of last       .#
    #...............................#
    def appendtxt(self, line):
        Y, X = self._widget.getyx()
        self._widget.addstr(Y, X, line)

    
    #....Display....................#
    #.          refresh            .#
    #...............................#
    def refresh(self):
        if self.ENABLE_SPLASH:
            if not self.ENABLE_SPLASH_1:
                pass
                self._splash.text(self._splash._txt)
                self.ENABLE_SPLASH_1 = True 
                # ENABLE_SPLASH_1 indicates that the text has been rewritten at least once
                # to avoid unncessarily rewriting the whole text and prevent flickering
            self._widget.refresh()
            self._splash.refresh()
        else:
            if self.ENABLE_SPLASH_1 == True:
                self._widget.overwrite(self._splash._widget)
                self._widget.redrawwin()
                self.ENABLE_SPLASH_1 = False
                # prevents flickering by only filling in the blank when needed

            self._widget.refresh()
            pass



    #....Display....................#
    #.    toggle__splash           .#
    #...............................#
    def toggle__splash(self):
        self.ENABLE_SPLASH_1 = self.ENABLE_SPLASH
        self.ENABLE_SPLASH = not self.ENABLE_SPLASH







  ###################################
 # view__init_curses()             #
###################################
# required by View::_init_screen
def view__create_windows(view):
    win = Display()
    _splash = win._widget.subwin(int(curses.LINES/5), int(curses.COLS/4), int(curses.LINES/2), int(curses.COLS/4))
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

    return { 'outputfield': win, 'inputfield': winbox, 'popup': _splash }











  ###################################
 # _count_bytes_in_pipe            #
###################################
# required by View::getinput
def _count_bytes_in_pipe(fifoWriteEnd, endianness="little"):
    buf = bytearray(4)
    fcntl.ioctl(fifoWriteEnd, termios.FIONREAD, buf, 1)
    bytesInPipe = int.from_bytes(buf, endianness)
    return bytesInPipe







  ###################################
 #          View{}                 #
###################################
class View:
    winbox = None
    win = None
    linebuf = []
    fifoWriteEnd = None





    #..View............................#
    #.          _init_screen          .#
    #..................................#
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






    #..View.........................#
    #.          __init__           .#
    #...............................#
    def __init__(self, fifoWriteEnd):
        self._init_screen()
        self.fifoWriteEnd = fifoWriteEnd











    #..View.......................................#
    #.          coro_update_mainwindow           .#
    #.............................................#
    def coro_update_mainwindow(self):
        try:
            while True:
                msg = yield
                self.win.appendtxt(msg)
                self.win.refresh()
        except GeneratorExit:
            pass





    #..View.........................#
    #.          refresh            .#
    #...............................#
    def refresh(self):
        self.win.refresh()
        # self.win._widget.refresh()
        self.winbox.refresh()






    #..View.........................#
    #.          getinput           .#
    #...............................#
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
        if xMax-53 > 0:
            if xMax-53 + 3 > 0:
                self.winbox.addstr(Y, xMax-53, "ESC", curses.A_ITALIC | curses.A_STANDOUT)
            if xMax-46 + 2 + len(countworkers_str) + 1 + len(maxworkers_str) > 0:
                self.winbox.addstr(Y, xMax-46, "w")
                self.winbox.addstr(Y, xMax-46+1, ":" + countworkers_str + "/" + maxworkers_str)
            if xMax-37 + len(current_total_str) + 1 + len(current_budget_str)  > 0:
                self.winbox.addstr(Y, xMax-37, current_total_str)
                self.winbox.addstr(Y, xMax-37+len(current_total_str), "/"+current_budget_str)
            if xMax-15 + 14 > 0:
                self.winbox.addstr(Y, xMax-15, "%.14s" % f"buf:{bytesInPipe}/{str(MINPOOLSIZE)}")

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
            elif result == curses.ascii.ESC:
                self.win.toggle__splash()
                # self.win.ENABLE_SPLASH = not self.win.ENABLE_SPLASH
        elif result == curses.KEY_RESIZE:
            self.winbox.move(0,0)
            self.winbox.addstr('>')
            self.winbox.addnstr(0, 1, "".join(self.linebuf), len(self.linebuf))

            curses.update_lines_cols()
            self.win._widget.resize(curses.LINES-1,curses.COLS)
            self.win._widget.redrawwin()
            self.win._splash.text(self.win._splash._txt)
            self.winbox.mvwin(curses.LINES-1, 0)
            self.winbox.redrawwin()
        # /if
        return ucmd









    #..View.........................#
    #.          destroy            .#
    #...............................#
    def destroy(self):
        curses.nocbreak()
        curses.echo()
        curses.curs_set(True)
        curses.endwin()
