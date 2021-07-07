
class View:
    def _init_curses(self):
        curses.noecho()
        win = curses.newwin(curses.LINES-1, curses.COLS, 0,0)
        win.idlok(True)
        win.scrollok(True)
        popupwin = win.subwin(int(curses.LINES/5), int(curses.COLS/4), int(curses.LINES/2), int(curses.COLS/4))
        popupwin.box()
        popupwin.addstr(5, 3, "what's up doc?")
        popupwin.refresh()
        winbox = curses.newwin(1, curses.COLS, curses.LINES-1, 0)
        winbox.addstr(0, 0, ">")
        winbox.nodelay(True)

        self.win = win
        self.winbox=winbox
        self.popupwin = popupwin


    def __init__(self):
        _init_curses(self)

        pass


