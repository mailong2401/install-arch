#!/usr/bin/env python3
import subprocess
import curses
import logging
import os

# ---- Logging setup ----
logfile = os.path.expanduser("~/install.log")
logging.basicConfig(
    filename=logfile,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def run(cmd):
    print(f"[RUN] {cmd}")
    logging.info(f"Running: {cmd}")
    subprocess.run(cmd, shell=True, check=True)

def list_disks():
    out = subprocess.check_output("lsblk -d -n -o NAME,SIZE,TYPE", shell=True, text=True)
    disks = []
    for line in out.strip().split("\n"):
        name, size, dtype = line.split()
        if dtype == "disk":
            disks.append(f"/dev/{name} ({size})")
    return disks

# ---- UI helper ----
def draw_summary(stdscr, config):
    """Hiển thị config đã chọn bên phải"""
    h, w = stdscr.getmaxyx()
    x = w//2 + 2
    stdscr.attron(curses.color_pair(2))
    stdscr.addstr(0, x, " CẤU HÌNH ĐÃ CHỌN ")
    stdscr.attroff(curses.color_pair(2))
    y = 2
    for key, value in config.items():
        stdscr.addstr(y, x, f"{key}: {value}")
        y += 1

def curses_menu(stdscr, title, options, config, keyname):
    curses.curs_set(0)
    h, w = stdscr.getmaxyx()
    current = 0

    while True:
        stdscr.clear()
        stdscr.attron(curses.color_pair(1))
        stdscr.addstr(0, 2, f"[ {title} ]")
        stdscr.attroff(curses.color_pair(1))

        # render options (bên trái)
        for idx, option in enumerate(options):
            x = 2
            y = h//2 - len(options)//2 + idx
            if idx == current:
                stdscr.attron(curses.color_pair(2))
                stdscr.addstr(y, x, f"> {option}")
                stdscr.attroff(curses.color_pair(2))
            else:
                stdscr.addstr(y, x, f"  {option}")

        # render summary (bên phải)
        draw_summary(stdscr, config)

        key = stdscr.getch()
        if key == curses.KEY_UP and current > 0:
            current -= 1
        elif key == curses.KEY_DOWN and current < len(options)-1:
            current += 1
        elif key in [curses.KEY_ENTER, ord("\n")]:
            config[keyname] = options[current]
            return options[current]

def curses_input(stdscr, prompt, config, keyname, hidden=False):
    curses.echo()
    stdscr.clear()
    stdscr.addstr(0, 2, prompt)
    stdscr.refresh()
    if hidden:
        curses.noecho()
        inp = ""
        while True:
            ch = stdscr.getch()
            if ch in [curses.KEY_ENTER, ord("\n")]:
                break
            elif ch in [curses.KEY_BACKSPACE, 127]:
                inp = inp[:-1]
            else:
                inp += chr(ch)
            stdscr.addstr(1, 2, "*" * len(inp))
            stdscr.refresh()
    else:
        inp = stdscr.getstr(1, 2, 20).decode("utf-8")
    curses.noecho()
    config[keyname] = inp.strip()
    return inp.strip()

# ---- main ----
def main(stdscr):
    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)   # title
    curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)   # highlight

    config = {}

    # --- chọn disk ---
    disks = list_disks()
    if not disks:
        raise SystemExit("❌ Không tìm thấy disk nào!")
    curses_menu(stdscr, "Chọn Disk để cài đặt", disks, config, "Disk")

    # --- user + password ---
    make_user = curses_menu(stdscr, "Tạo user?", ["Có", "Không"], config, "User?")
    if make_user == "Có":
        curses_input(stdscr, "Nhập tên user:", config, "Username")
        curses_input(stdscr, "Nhập password:", config, "Password", hidden=True)
    else:
        config["Username"] = "root only"

    # --- chọn kernel, gpu, wm/de, bootloader ---
    curses_menu(stdscr, "Chọn Kernel", ["linux", "linux-lts", "linux-zen"], config, "Kernel")
    curses_menu(stdscr, "Chọn GPU Driver", ["intel", "amd", "nvidia"], config, "GPU")
    curses_menu(stdscr, "Chọn WM/DE", ["bspwm", "hyprland", "gnome", "kde"], config, "WM/DE")
    curses_menu(stdscr, "Chọn Bootloader", ["systemd-boot", "grub"], config, "Bootloader")

    # --- summary final ---
    stdscr.clear()
    stdscr.addstr(0, 2, "TÓM TẮT CẤU HÌNH", curses.A_BOLD)
    y = 2
    for k, v in config.items():
        stdscr.addstr(y, 2, f"{k}: {v}")
        y += 1
    stdscr.addstr(y+2, 2, "Nhấn Enter để bắt đầu cài đặt...")
    stdscr.refresh()
    stdscr.getch()

    # TODO: chạy auto partition + pacstrap như code trước
    # (cái phần này mình giữ nguyên không thay đổi)

if __name__ == "__main__":
    curses.wrapper(main)

