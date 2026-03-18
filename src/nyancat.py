#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Terminal Nyancat - Python port of the C nyancat.
Renders the classic Nyan Cat (poptart cat) in the terminal.
Uses ANSI escape sequences for color; supports telnet server mode.
"""

from __future__ import print_function

import argparse
import os
import select
import signal
import struct
import sys
import time

# Telnet protocol constants (from telnet.h)
IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251
SE = 240
NOP = 241
SB = 250
ECHO = 1
SGA = 3
NAWS = 31
TTYPE = 24
LINEMODE = 34
NEW_ENVIRON = 39
SEND = 1

# Animation (from animation.c)
from animation import frames, FRAME_WIDTH, FRAME_HEIGHT

# Logo overlay (from nyancat.c logo_topright)
N_LOGO_LINES = 14
LOGO_COLS = 79
LOGO_TOPRIGHT = [
    "██╗  ██╗ ██████╗  ██╗    ███████╗  ██████╗ ██╗  ██╗  ██████╗   ██████╗  ██╗       ",
    "██║ ██╔╝ ██╔══██╗ ██║    ██╔════╝ ██╔════╝ ██║  ██║ ██╔═══██╗ ██╔═══██╗ ██║       ",
    "█████╔╝  ██║  ██║ ██║    ███████╗ ██║      ███████║ ██║   ██║ ██║   ██║ ██║       ",
    "██╔═██╗  ██║  ██║ ██║    ╚════██║ ██║      ██╔══██║ ██║   ██║ ██║   ██║ ██║       ",
    "██║  ██╗ ██████╔╝ ██║    ███████║ ╚██████╗ ██║  ██║ ╚██████╔╝ ╚██████╔╝ ███████╗  ",
    "╚═╝  ╚═╝ ╚═════╝  ╚═╝    ╚══════╝  ╚═════╝ ╚═╝  ╚═╝  ╚═════╝   ╚═════╝  ╚══════╝  ",
    "╔═══════════════════════════════════════════════════════════════════════════════════════╗",
    "║ ██████╗   █████╗  ████████╗  █████╗     ██╗  ██╗ ███╗   ██╗ ██╗ ████████╗    ██████╗  ║",
    "║ ██╔══██╗ ██╔══██╗ ╚══██╔══╝ ██╔══██╗    ██║  ██║ ████╗  ██║ ██║ ╚══██╔══╝    ╚════██╗ ║",
    "║ ██║  ██║ ███████║    ██║    ███████║    ██║  ██║ ██╔██╗ ██║ ██║    ██║        █████╔╝ ║",
    "║ ██║  ██║ ██╔══██║    ██║    ██╔══██║    ██║  ██║ ██║╚██╗██║ ██║    ██║       ██╔═══╝  ║",
    "║ ██████╔╝ ██║  ██║    ██║    ██║  ██║    ╚█████╔╝ ██║ ╚████║ ██║    ██║       ███████╗ ║",
    "║ ╚═════╝  ╚═╝  ╚═╝    ╚═╝    ╚═╝  ╚═╝     ╚════╝  ╚═╝  ╚═══╝ ╚═╝    ╚═╝       ╚══════╝ ║",
    "╚═══════════════════════════════════════════════════════════════════════════════════════╝",
]

# Global state (mirroring C globals)
colors = {}  # char -> escape string or text
output = "  "
telnet_mode = False
show_counter = True
frame_count = 0
clear_screen = True
set_title = True
min_row = -1
max_row = -1
min_col = -1
max_col = -1
terminal_width = 80
terminal_height = 24
using_automatic_width = False
using_automatic_height = False
telnet_options = [0] * 256
telnet_willack = [0] * 256
telnet_do_set = [0] * 256
telnet_will_set = [0] * 256
delay_ms = 90
always_escape = False


def digits(val):
    """Count digits in a number (C digits())."""
    d = 1
    if val >= 0:
        c = 10
        while c <= val:
            d += 1
            c *= 10
    else:
        c = -10
        while c >= val:
            d += 1
            c *= 10
    return d + 1 if c < 0 else d


def finish():
    """Restore cursor and exit."""
    if clear_screen:
        out("\033[?25h\033[0m\033[H\033[2J")
    else:
        out("\033[0m\n")
    flush()
    sys.exit(0)


def out(s):
    """Write string to stdout. In telnet mode, write as latin-1 bytes."""
    if telnet_mode and hasattr(sys.stdout, "buffer"):
        try:
            sys.stdout.buffer.write(s.encode("latin-1"))
        except UnicodeEncodeError:
            sys.stdout.buffer.write(s.encode("utf-8", errors="replace"))
    else:
        sys.stdout.write(s)


def flush():
    if telnet_mode and hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.flush()
    sys.stdout.flush()


def newline(n):
    """Send n newlines; telnet uses \\r\\0\\n."""
    for _ in range(n):
        if telnet_mode:
            out("\r\x00\n")
        else:
            out("\n")


def set_options():
    """Set default telnet server options."""
    telnet_options[ECHO] = WONT
    telnet_options[SGA] = WILL
    telnet_options[NEW_ENVIRON] = WONT
    telnet_willack[ECHO] = DO
    telnet_willack[SGA] = DO
    telnet_willack[NAWS] = DO
    telnet_willack[TTYPE] = DO
    telnet_willack[LINEMODE] = DONT
    telnet_willack[NEW_ENVIRON] = DO


def send_command(cmd, opt=0):
    """Send telnet command to client."""
    if cmd in (DO, DONT):
        if (cmd == DO and telnet_do_set[opt] != DO) or (cmd == DONT and telnet_do_set[opt] != DONT):
            telnet_do_set[opt] = cmd
            out("".join(chr(x) for x in [IAC, cmd, opt]))
    elif cmd in (WILL, WONT):
        if (cmd == WILL and telnet_will_set[opt] != WILL) or (cmd == WONT and telnet_will_set[opt] != WONT):
            telnet_will_set[opt] = cmd
            out("".join(chr(x) for x in [IAC, cmd, opt]))
    else:
        out("".join(chr(x) for x in [IAC, cmd]))


def get_terminal_size():
    """Get (cols, rows)."""
    try:
        try:
            import fcntl
            import termios
            buf = struct.pack("HHHH", 0, 0, 0, 0)
            buf = fcntl.ioctl(sys.stdin.fileno(), termios.TIOCGWINSZ, buf)
            rows, cols = struct.unpack("HHHH", buf)[:2]
            return cols, rows
        except (ImportError, OSError, AttributeError):
            pass
        sz = os.get_terminal_size()
        return sz.columns, sz.lines
    except Exception:
        return 80, 24


def detect_terminal_type(term_str, width, height):
    """Return ttype 1-8 (or 2 default) from TERM and size."""
    if not term_str:
        return 2
    term = term_str.lower()
    if "xterm" in term:
        return 1
    if "toaru" in term:
        return 1
    if "linux" in term:
        return 3
    if "vtnt" in term:
        return 5
    if "cygwin" in term:
        return 5
    if "vt220" in term:
        return 6
    if "fallback" in term:
        return 4
    if "rxvt-256color" in term:
        return 1
    if "rxvt" in term:
        return 3
    if "vt100" in term and width == 40:
        return 7
    if term.startswith("st"):
        return 1
    if term.startswith("truecolor"):
        return 8
    return 2


def setup_colors(ttype):
    """Set colors and output for terminal type (C switch(ttype))."""
    global output, always_escape, terminal_width
    # Clear previous
    colors.clear()
    output = "  "
    always_escape = False
    if ttype == 1:
        colors[","] = "\033[48;5;17m"
        colors["."] = "\033[48;5;231m"
        colors["'"] = "\033[48;5;16m"
        colors["@"] = "\033[48;5;230m"
        colors["$"] = "\033[48;5;175m"
        colors["-"] = "\033[48;5;162m"
        colors[">"] = "\033[48;5;196m"
        colors["&"] = "\033[48;5;214m"
        colors["+"] = "\033[48;5;226m"
        colors["#"] = "\033[48;5;118m"
        colors["="] = "\033[48;5;33m"
        colors[";"] = "\033[48;5;19m"
        colors["*"] = "\033[48;5;240m"
        colors["%"] = "\033[48;5;175m"
    elif ttype == 2:
        colors[","] = "\033[104m"
        colors["."] = "\033[107m"
        colors["'"] = "\033[40m"
        colors["@"] = "\033[47m"
        colors["$"] = "\033[105m"
        colors["-"] = "\033[101m"
        colors[">"] = "\033[101m"
        colors["&"] = "\033[43m"
        colors["+"] = "\033[103m"
        colors["#"] = "\033[102m"
        colors["="] = "\033[104m"
        colors[";"] = "\033[44m"
        colors["*"] = "\033[100m"
        colors["%"] = "\033[105m"
    elif ttype == 3:
        colors[","] = "\033[25;44m"
        colors["."] = "\033[5;47m"
        colors["'"] = "\033[25;40m"
        colors["@"] = "\033[5;47m"
        colors["$"] = "\033[5;45m"
        colors["-"] = "\033[5;41m"
        colors[">"] = "\033[5;41m"
        colors["&"] = "\033[25;43m"
        colors["+"] = "\033[5;43m"
        colors["#"] = "\033[5;42m"
        colors["="] = "\033[25;44m"
        colors[";"] = "\033[5;44m"
        colors["*"] = "\033[5;40m"
        colors["%"] = "\033[5;45m"
    elif ttype == 4:
        colors[","] = "\033[0;34;44m"
        colors["."] = "\033[1;37;47m"
        colors["'"] = "\033[0;30;40m"
        colors["@"] = "\033[1;37;47m"
        colors["$"] = "\033[1;35;45m"
        colors["-"] = "\033[1;31;41m"
        colors[">"] = "\033[1;31;41m"
        colors["&"] = "\033[0;33;43m"
        colors["+"] = "\033[1;33;43m"
        colors["#"] = "\033[1;32;42m"
        colors["="] = "\033[1;34;44m"
        colors[";"] = "\033[0;34;44m"
        colors["*"] = "\033[1;30;40m"
        colors["%"] = "\033[1;35;45m"
        output = "██"
    elif ttype == 5:
        colors[","] = "\033[0;34;44m"
        colors["."] = "\033[1;37;47m"
        colors["'"] = "\033[0;30;40m"
        colors["@"] = "\033[1;37;47m"
        colors["$"] = "\033[1;35;45m"
        colors["-"] = "\033[1;31;41m"
        colors[">"] = "\033[1;31;41m"
        colors["&"] = "\033[0;33;43m"
        colors["+"] = "\033[1;33;43m"
        colors["#"] = "\033[1;32;42m"
        colors["="] = "\033[1;34;44m"
        colors[";"] = "\033[0;34;44m"
        colors["*"] = "\033[1;30;40m"
        colors["%"] = "\033[1;35;45m"
        # C: \333\333 is octal 333 = 219 decimal (block character)
        output = chr(219) + chr(219)
    elif ttype == 6:
        colors[","] = "::"
        colors["."] = "@@"
        colors["'"] = "  "
        colors["@"] = "##"
        colors["$"] = "??"
        colors["-"] = "<>"
        colors[">"] = "##"
        colors["&"] = "=="
        colors["+"] = "--"
        colors["#"] = "++"
        colors["="] = "~~"
        colors[";"] = "$$"
        colors["*"] = ";;"
        colors["%"] = "()"
        always_escape = True
    elif ttype == 7:
        colors[","] = "."
        colors["."] = "@"
        colors["'"] = " "
        colors["@"] = "#"
        colors["$"] = "?"
        colors["-"] = "O"
        colors[">"] = "#"
        colors["&"] = "="
        colors["+"] = "-"
        colors["#"] = "+"
        colors["="] = "~"
        colors[";"] = "$"
        colors["*"] = ";"
        colors["%"] = "o"
        always_escape = True
        terminal_width = 40
    elif ttype == 8:
        colors[","] = "\033[48;2;0;49;105m"
        colors["."] = "\033[48;2;255;255;255m"
        colors["'"] = "\033[48;2;0;0;0m"
        colors["@"] = "\033[48;2;255;205;152m"
        colors["$"] = "\033[48;2;255;169;255m"
        colors["-"] = "\033[48;2;255;76;152m"
        colors[">"] = "\033[48;2;255;25;0m"
        colors["&"] = "\033[48;2;255;154;0m"
        colors["+"] = "\033[48;2;255;240;0m"
        colors["#"] = "\033[48;2;40;220;0m"
        colors["="] = "\033[48;2;0;144;255m"
        colors[";"] = "\033[48;2;104;68;255m"
        colors["*"] = "\033[48;2;153;153;153m"
        colors["%"] = "\033[48;2;255;163;152m"


def telnet_negotiate():
    """Run telnet option negotiation; return (term_str or None, done)."""
    global terminal_width, terminal_height
    sb = bytearray(1024)
    sb_len = 0
    sb_mode = False
    done = 0
    term = None
    set_options()
    for opt in range(256):
        if telnet_options[opt]:
            send_command(telnet_options[opt], opt)
            flush()
    for opt in range(256):
        if telnet_willack[opt]:
            send_command(telnet_willack[opt], opt)
            flush()
    try:
        rlist = [sys.stdin]
        while done < 2:
            try:
                ready, _, _ = select.select(rlist, [], [], 1.0)
            except (select.error, OSError, ValueError):
                break
            if not ready or not rlist:
                break
            try:
                b = sys.stdin.buffer.read(1)
            except (EOFError, OSError):
                break
            if not b:
                break
            i = b[0]
            if i == IAC:
                try:
                    b2 = sys.stdin.buffer.read(1)
                except (EOFError, OSError):
                    break
                if not b2:
                    break
                i = b2[0]
                if i == SE:
                    sb_mode = False
                    if sb_len >= 1 and sb[0] == TTYPE:
                        term = bytes(sb[2:sb_len]).decode("latin-1", errors="replace").strip("\x00")
                        done += 1
                    elif sb_len >= 5 and sb[0] == NAWS:
                        terminal_width = (sb[1] << 8) | sb[2]
                        terminal_height = (sb[3] << 8) | sb[4]
                        done += 1
                elif i == NOP:
                    send_command(NOP, 0)
                    flush()
                elif i in (WILL, WONT):
                    try:
                        b3 = sys.stdin.buffer.read(1)
                    except (EOFError, OSError):
                        break
                    if not b3:
                        break
                    opt = b3[0]
                    if not telnet_willack[opt]:
                        telnet_willack[opt] = WONT
                    send_command(telnet_willack[opt], opt)
                    flush()
                    if i == WILL and opt == TTYPE:
                        out("".join(chr(x) for x in [IAC, SB, TTYPE, SEND, IAC, SE]))
                        flush()
                elif i in (DO, DONT):
                    try:
                        b3 = sys.stdin.buffer.read(1)
                    except (EOFError, OSError):
                        break
                    if not b3:
                        break
                    opt = b3[0]
                    if not telnet_options[opt]:
                        telnet_options[opt] = DONT
                    send_command(telnet_options[opt], opt)
                    flush()
                elif i == SB:
                    sb_mode = True
                    sb_len = 0
                    sb[:] = bytes(1024)
                elif i == IAC:
                    done = 2
            elif sb_mode and sb_len < len(sb) - 1:
                sb[sb_len] = i
                sb_len += 1
    except (select.error, ValueError):
        pass
    return term, done


def run_animation(term_str, ttype, show_intro):
    """Main animation loop."""
    global min_row, max_row, min_col, max_col, using_automatic_width, using_automatic_height
    setup_colors(ttype)
    if min_col == max_col:
        min_col = (FRAME_WIDTH - terminal_width // 2) // 2
        max_col = (FRAME_WIDTH + terminal_width // 2) // 2
        using_automatic_width = True
    if min_row == max_row:
        min_row = (FRAME_HEIGHT - (terminal_height - 1)) // 2
        max_row = (FRAME_HEIGHT + (terminal_height - 1)) // 2
        using_automatic_height = True
    if set_title:
        out("\033kNyanyanyanyanyanyanya...\033\\")
        out("\033]1;Nyanyanyanyanyanyanya...\007")
        out("\033]2;Nyanyanyanyanyanyanya...\007")
    if clear_screen:
        out("\033[H\033[2J\033[?25l")
    else:
        out("\033[s")
    flush()
    if show_intro:
        for k in range(5):
            newline(3)
            out("                             \033[1mNyancat Telnet Server\033[0m")
            newline(2)
            out("                   written and run by \033[1;32mK. Lange\033[1;34m @_klange\033[0m")
            newline(2)
            out("        If things don't look right, try:")
            newline(1)
            out("                TERM=fallback telnet ...")
            newline(2)
            out("        Or on Windows:")
            newline(1)
            out("                telnet -t vtnt ...")
            newline(2)
            out("        Problems? Check the website:")
            newline(1)
            out("                \033[1;34mhttp://nyancat.dakko.us\033[0m")
            newline(2)
            out("        This is a telnet server, remember your escape keys!")
            newline(1)
            out("                \033[1;31m^]quit\033[0m to exit")
            newline(2)
            out("        Starting in %d...                \n" % (5 - k))
            flush()
            time.sleep(0.4)
            if clear_screen:
                out("\033[H")
            else:
                out("\033[u")
        if clear_screen:
            out("\033[H\033[2J\033[?25l")
        flush()
    start_time = time.time()
    i = 0
    f = 0
    last = ""
    rainbow = ",,>>&&&+++###==;;;,,"  # C: const char *rainbow = ...
    while True:
        if clear_screen:
            out("\033[H")
        else:
            out("\033[u")
        bg = ","
        row_chars = (max_col - min_col) * 2
        for k in range(4):
            for x in range(min_col, max_col):
                if always_escape:
                    out(colors.get(bg, output))
                elif colors.get(bg):
                    out(colors[bg] + output)
                else:
                    out(output)
            if row_chars < terminal_width and colors.get(bg):
                out(colors[bg])
                for _ in range(row_chars, terminal_width):
                    out(" ")
            newline(1)
        last = bg
        for y in range(min_row, max_row - 4):
            for x in range(min_col, max_col):
                if y > 23 and y < 43 and x < 0:
                    mod_x = ((-x + 2) % 16) // 8
                    if (i // 2) % 2:
                        mod_x = 1 - mod_x
                    idx = mod_x + y - 23
                    color = rainbow[idx] if idx < len(rainbow) else ","
                elif x < 0 or y < 0 or y >= FRAME_HEIGHT or x >= FRAME_WIDTH:
                    color = ","
                else:
                    color = frames[i][y][x]
                if always_escape:
                    out(colors.get(color, ""))
                else:
                    if color != last and colors.get(color):
                        last = color
                        out(colors[color] + output)
                    else:
                        out(output)
            if row_chars < terminal_width and colors.get(","):
                out(colors[","])
                for _ in range(row_chars, terminal_width):
                    out(" ")
            newline(1)
        total_rows = 4 + (max_row - 4 - min_row)
        for fill_r in range(total_rows, terminal_height):
            if colors.get(bg):
                out(colors[bg])
            for _ in range(terminal_width):
                out(" ")
            newline(1)
        if terminal_width >= LOGO_COLS and terminal_height >= N_LOGO_LINES + 2:
            logo_col = max(1, terminal_width - LOGO_COLS - 12)
            logo_row_start = 2
            logo_colors = [36, 37, 33, 35]
            c = logo_colors[(i // 2) % 4]
            out("\033[1;%dm" % c)
            for r in range(N_LOGO_LINES):
                out("\033[%d;%dH%s" % (logo_row_start + r, logo_col, LOGO_TOPRIGHT[r]))
            out("\033[0m")
            for tr in range(logo_row_start, logo_row_start + N_LOGO_LINES):
                ay = min_row + tr - 5
                for tc in range(logo_col, logo_col + LOGO_COLS, 2):
                    ax = min_col + (tc - 1) // 2
                    if ay > 23 and ay < 43 and ax < 0:
                        mod_x = ((-ax + 2) % 16) // 8
                        if (i // 2) % 2:
                            mod_x = 1 - mod_x
                        idx = mod_x + ay - 23
                        color = rainbow[idx] if idx < len(rainbow) else ","
                    elif ax < 0 or ay < 0 or ay >= FRAME_HEIGHT or ax >= FRAME_WIDTH:
                        color = ","
                    else:
                        color = frames[i][ay][ax]
                    if color != "," and colors.get(color):
                        out("\033[%d;%dH%s%s" % (tr, tc, colors[color], output))
            flush()
        if show_counter:
            diff = time.time() - start_time
            n_len = digits(int(diff))
            width = (terminal_width - 29 - n_len) // 2
            out(" " * max(0, width))
            out("\033[1;37mYou have nyaned for %0.0f seconds!\033[J\033[0m" % diff)
        last = ""
        f += 1
        if frame_count != 0 and f == frame_count:
            finish()
        i += 1
        if i >= len(frames):
            i = 0
        time.sleep(delay_ms / 1000.0)


def main():
    global telnet_mode, show_counter, frame_count, clear_screen, set_title
    global min_row, max_row, min_col, max_col, terminal_width, terminal_height, delay_ms
    parser = argparse.ArgumentParser(
        prog="nyancat",
        description="Terminal Nyancat",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-i", "--intro", action="store_true", help="Show introduction at startup.")
    parser.add_argument("-I", "--skip-intro", action="store_true", help="Skip intro in telnet mode.")
    parser.add_argument("-t", "--telnet", action="store_true", help="Telnet mode.")
    parser.add_argument("-n", "--no-counter", action="store_true", help="Do not display the timer.")
    parser.add_argument("-s", "--no-title", action="store_true", help="Do not set the titlebar text.")
    parser.add_argument("-e", "--no-clear", action="store_true", help="Do not clear the display between frames.")
    parser.add_argument("-d", "--delay", type=int, default=90, metavar="ms", help="Delay in ms (10-1000).")
    parser.add_argument("-f", "--frames", type=int, default=0, metavar="N", help="Display N frames then quit.")
    parser.add_argument("-r", "--min-rows", type=int, default=-1, help="Crop from top.")
    parser.add_argument("-R", "--max-rows", type=int, default=-1, help="Crop from bottom.")
    parser.add_argument("-c", "--min-cols", type=int, default=-1, help="Crop from left.")
    parser.add_argument("-C", "--max-cols", type=int, default=-1, help="Crop from right.")
    parser.add_argument("-W", "--width", type=int, help="Crop to width.")
    parser.add_argument("-H", "--height", type=int, help="Crop to height.")
    args = parser.parse_args()
    clear_screen = not args.no_clear
    set_title = not args.no_title
    telnet_mode = args.telnet
    show_counter = not args.no_counter
    frame_count = args.frames
    if 10 <= args.delay <= 1000:
        delay_ms = args.delay
    min_row = args.min_rows
    max_row = args.max_rows
    min_col = args.min_cols
    max_col = args.max_cols
    if args.width is not None:
        min_col = (FRAME_WIDTH - args.width) // 2
        max_col = (FRAME_WIDTH + args.width) // 2
    if args.height is not None:
        min_row = (FRAME_HEIGHT - args.height) // 2
        max_row = (FRAME_HEIGHT + args.height) // 2
    signal.signal(signal.SIGINT, lambda sig, frame: finish())
    signal.signal(signal.SIGPIPE, lambda sig, frame: finish())

    def on_winch(sig, frame):
        global terminal_width, terminal_height, min_col, max_col, min_row, max_row
        terminal_width, terminal_height = get_terminal_size()
        if using_automatic_width:
            min_col = (FRAME_WIDTH - terminal_width // 2) // 2
            max_col = (FRAME_WIDTH + terminal_width // 2) // 2
        if using_automatic_height:
            min_row = (FRAME_HEIGHT - (terminal_height - 1)) // 2
            max_row = (FRAME_HEIGHT + (terminal_height - 1)) // 2
    if not telnet_mode:
        try:
            signal.signal(signal.SIGWINCH, on_winch)
        except (AttributeError, ValueError):
            pass

    term = None
    if telnet_mode:
        show_intro = not args.skip_intro
        term, _ = telnet_negotiate()
        if term is None:
            term = ""
    else:
        show_intro = args.intro
        terminal_width, terminal_height = get_terminal_size()
        term = os.environ.get("TERM", "")
    ttype = detect_terminal_type(term, terminal_width, terminal_height)
    run_animation(term, ttype, show_intro)


if __name__ == "__main__":
    main()
