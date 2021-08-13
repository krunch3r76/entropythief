# view
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)
import os,sys,subprocess #testing

import curses
import curses.ascii
import curses.panel
import sys
import fcntl
import termios
import string
import time # debug
import io
from queue import SimpleQueue




##############################################
# partition                            #
##############################################
def partition(total_length, first_length, lengthmax):
    parts = [first_length]
    # how much of the length remains beyond first length
    remaining = total_length - first_length
    if remaining > 0:
        # how many times does lengthmax measure remaining
        measures = int(remaining/lengthmax)
    if measures == 0:
        parts.append(remaining)
    else:
        for _ in range(measures):
            parts.append(lengthmax)
    # how much remains after remaining is measured by lengthmax
    mod = remaining % lengthmax
    if mod != 0:
        parts.append(mod)

    return parts





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
            height3rd = int( (Ymax-yBegParent)/2.5)
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


            self._txt = txt
            txtLines = self._txt.split('\n')
            txtLines_len = len(txtLines) + 1 # include horizontal bar

            if curses.LINES > 3:
                coords = self._refresh_coords()
                heightSplash = coords[4]-coords[2] # height of splash
                widthSplash = coords[5]-coords[3] # width of splash

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
    def __init__(self, background):
        self.background=background
        self._widget = curses.newwin(curses.LINES-1, curses.COLS, 0, 0)
        self._load_background()
        self._widget.idlok(True);
        self._widget.scrollok(True)
        self._widget.syncok(False) # testing for UI improvement
        self._widget.leaveok(True)
        self._splash = self.Splash(self)
        txt=\
"""EntropyThief >cmd reference
>set buflim=<NUM>
>set maxworkers=<NUM>
>set budget=<FLOAT>
>stop
>restart    # after pause due to budget limit
<ESC> toggle this menu
"""
        self._splash.text(txt)

        # debug
        # curses.endwin()     
        # /debug


    def _load_background(self):
        y=0; x=0
        h, w= self._widget.getmaxyx()
        inner_height, inner_width = self.background.inner_height, self.background.inner_width

        if inner_height < h:
            margin = int((h - inner_height)/2)
            y+=margin

       
        if inner_width < w:
            margin = int((w - inner_width)/2)
            x+=margin

        if inner_height < h and inner_width < w:
            for line in self.background.lines:
                self._widget.addstr(y, x, line.rstrip())               
                y+=1



    #....Display....................#
    #.          refresh            .#
    #...............................#
    def refresh(self):
        if self.ENABLE_SPLASH:
            if not self.ENABLE_SPLASH_1:
                # self._splash.text(self._splash._txt)
                self.ENABLE_SPLASH_1 = True 
            self._splash.refresh()
        else:
            if self.ENABLE_SPLASH_1 == True:
                self._widget.redrawwin()
                self.ENABLE_SPLASH_1 = False
            pass

        self._widget.refresh()





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
def view__create_windows(view, background):
    win = Display(background)

    winbox = curses.newwin(1, curses.COLS, curses.LINES-1, 0)
    winbox.addstr(0, 0, ">")
    winbox.nodelay(True)

    return { 'outputfield': win, 'inputfield': winbox }














class Background:
    # inner_height
    # inner_width
    def __init__(self):
        with open("dontpanic.txt") as f:
            self.lines = f.readlines()
                        
        self.inner_height = len(self.lines)
        self.inner_width = 0
        for line in self.lines:
            if len(line) > self.inner_width:
                self.inner_width = len(line)
        # post: inner_height, inner_width, lines


  ###################################
 #          View{}                 #
###################################
class View:
    winbox = None
    win = None
    linebuf = []







    #..View............................#
    #.          _init_screen          .#
    #..................................#
    def _init_screen(self):
        try:
            # subprocess.run(['resize', 100, 100])
            # sys.stdout.write("\e[8;50;100t")
            self.screen = curses.initscr() 
            curses.start_color()
            curses.noecho()
            curses.cbreak()

            
            windir = view__create_windows(self, self.background)
            self.win = windir['outputfield']
            self.winbox = windir['inputfield']

            curses.use_default_colors()
            curses.init_pair(3, curses.COLOR_YELLOW, -1)


        except Exception as e:
            curses.nocbreak()
            curses.echo()
            curses.curs_set(1)
            curses.endwin()
            raise




    #..View.........................#
    #.          __init__           .#
    #...............................#
    def __init__(self):
        self.background = Background()
        self._init_screen()











    #..View.......................................#
    #.          coro_update_mainwindow           .#
    #.............................................#
    def coro_update_mainwindow(self):


        def whether_stream_is_at_end(stream):
            rv = True
            if not stream.closed:
                current_pos = stream.tell()
                stream.seek(0, io.SEEK_END)
                end_pos = stream.tell()
                stream.seek(current_pos, io.SEEK_SET)
                rv = (current_pos == end_pos)
            return rv

        # here we keep a concatenated string from which we remove portions from the front to fill a line on each call
        # low values make messageBuffered super heavy, next revision will use a memory stream
        q = SimpleQueue()
        offset=0
        messageBuffered = io.StringIO()
        try:
            while True:
                msg_in = yield True # whatever is sent to this generator is assigned to msg here and loop starts
                                    # True is returned to inform caller to manually refresh
                if msg_in:
                    q.put( io.StringIO(msg_in) )

                if whether_stream_is_at_end(messageBuffered):
                    messageBuffered.close()
                    if not q.empty():
                        messageBuffered = q.get()
                        offset=0

                if not messageBuffered.closed:
                    messageBuffered.seek(offset, io.SEEK_SET)
                    lines = messageBuffered.read(4096)
                    offset+=len(lines)
                    if len(lines) > 0:
                        curses.curs_set(0)
                        self.win._widget.addstr(lines)
                        self.win.refresh()
                else:
                    curses.curs_set(1)
        except GeneratorExit: # this generator is infinite and may want to be closed as some point?
            pass





    #..View.........................#
    #.          refresh            .#
    #...............................#
    def refresh(self):
        self.win.refresh()
        self.winbox.refresh()






    #..View.........................#
    #.          getinput           .#
    #...............................#
    def getinput(self, current_total, MINPOOLSIZE, BUDGET, MAXWORKERS, count_workers, bytesInPipe, whether_paused):
        # update status line

        Y, X = self.winbox.getyx()
        yMax, xMax = self.winbox.getmaxyx()
        current_total_str = "cost:{:.5f}".format(current_total)
        current_budget_str = "{:.5f}".format(BUDGET)
        maxworkers_str = "{:02d}".format(MAXWORKERS)
        countworkers_str = "{:02d}".format(count_workers)

        self.winbox.move(Y, len(self.linebuf)+1)
        self.winbox.clrtoeol()
        ADJUST=15
        if xMax-53-ADJUST > 0:
            if whether_paused:
                self.winbox.addstr(Y, xMax-60-ADJUST, "PAUSED", curses.color_pair(3) | curses.A_BLINK)
            if xMax-53-ADJUST + 3 > 0:
                self.winbox.addstr(Y, xMax-53-ADJUST, "ESC", curses.A_ITALIC | curses.A_STANDOUT)
            if xMax-46-ADJUST + 2 + len(countworkers_str) + 1 + len(maxworkers_str) > 0:
                self.winbox.addstr(Y, xMax-46-ADJUST, "w")
                self.winbox.addstr(Y, xMax-46+1-ADJUST, ":" + countworkers_str + "/" + maxworkers_str)
            if xMax-37-ADJUST + len(current_total_str) + 1 + len(current_budget_str)  > 0:
                self.winbox.addstr(Y, xMax-37-ADJUST, current_total_str)
                self.winbox.addstr(Y, xMax-37-ADJUST+len(current_total_str), "/"+current_budget_str)
            if xMax-15-ADJUST + 14 > 0:
                self.winbox.addstr(Y, xMax-15-ADJUST, "%.30s" % f"buf:{bytesInPipe}/{str(MINPOOLSIZE)}")
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
        elif result == curses.KEY_RESIZE:
            curses.update_lines_cols()
            self.winbox.move(0,0)
            self.winbox.addstr('>')
            self.winbox.addnstr(0, 1, "".join(self.linebuf), len(self.linebuf))

            self.win._widget.resize(curses.LINES-1,curses.COLS)
            self.win._widget.redrawwin()

            # if curses.LINES > 3: 
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
        curses.curs_set(1)
        curses.endwin()
