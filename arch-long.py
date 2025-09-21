#!/usr/bin/env python3
import subprocess
import argparse
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
    """Liệt kê các disk từ lsblk"""
    out = subprocess.check_output("lsblk -d -n -o NAME,SIZE,TYPE", shell=True, text=True)
    disks = []
    for line in out.strip().split("\n"):
        name, size, dtype = line.split()
        if dtype == "disk":
            disks.append(f"/dev/{name} ({size})")
    return disks

def curses_menu(stdscr, title, options):
    curses.curs_set(0)
    h, w = stdscr.getmaxyx()
    current = 0

    while True:
        stdscr.clear()
        stdscr.addstr(0, w//2 - len(title)//2, title, curses.A_BOLD)

        for idx, option in enumerate(options):
            x = w//2 - len(option)//2
            y = h//2 - len(options)//2 + idx
            if idx == current:
                stdscr.attron(curses.color_pair(1))
                stdscr.addstr(y, x, option)
                stdscr.attroff(curses.color_pair(1))
            else:
                stdscr.addstr(y, x, option)

        key = stdscr.getch()
        if key == curses.KEY_UP and current > 0:
            current -= 1
        elif key == curses.KEY_DOWN and current < len(options)-1:
            current += 1
        elif key in [curses.KEY_ENTER, ord("\n")]:
            return options[current]

def main(stdscr):
    curses.start_color()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)

    # ---- chọn disk ----
    disks = list_disks()
    if not disks:
        raise SystemExit("❌ Không tìm thấy disk nào!")
    chosen_disk = curses_menu(stdscr, "Chọn Disk để cài đặt", disks)
    disk = chosen_disk.split()[0]  # chỉ lấy /dev/sdX

    # ---- chọn kernel, driver, wm/de, bootloader ----
    kernel = curses_menu(stdscr, "Chọn Kernel", ["linux", "linux-lts", "linux-zen"])
    gpu = curses_menu(stdscr, "Chọn GPU Driver", ["intel", "amd", "nvidia"])
    wmde = curses_menu(stdscr, "Chọn WM/DE", ["bspwm", "hyprland", "gnome", "kde"])
    bootloader = curses_menu(stdscr, "Chọn Bootloader", ["systemd-boot", "grub"])

    stdscr.clear()
    stdscr.addstr(0, 0,
        f"Disk: {disk}\nKernel: {kernel}\nGPU: {gpu}\nWM/DE: {wmde}\nBootloader: {bootloader}")
    stdscr.addstr(7, 0, "⚠️ Lưu ý: bạn phải tự mount sẵn /mnt và /mnt/boot trước khi chạy script này.")
    stdscr.addstr(9, 0, "Nhấn Enter để bắt đầu cài đặt...")
    stdscr.refresh()
    stdscr.getch()

    # ---- base install ----
    pkgs = f"base {kernel} {kernel}-headers networkmanager nvim sudo"

    if gpu == "nvidia":
        pkgs += " nvidia-dkms nvidia-utils"
    elif gpu == "amd":
        pkgs += " xf86-video-amdgpu mesa"
    elif gpu == "intel":
        pkgs += " mesa xf86-video-intel"

    if wmde == "bspwm":
        pkgs += " bspwm sxhkd alacritty polybar"
    elif wmde == "hyprland":
        pkgs += " hyprland waybar alacritty"
    elif wmde == "gnome":
        pkgs += " gnome gdm"
    elif wmde == "kde":
        pkgs += " plasma sddm"

    run(f"pacstrap -K /mnt {pkgs}")
    run("genfstab -U /mnt >> /mnt/etc/fstab")

    # ---- system config ----
    run("arch-chroot /mnt ln -sf /usr/share/zoneinfo/Asia/Ho_Chi_Minh /etc/localtime")
    run("arch-chroot /mnt hwclock --systohc")
    run("arch-chroot /mnt locale-gen")
    run("arch-chroot /mnt systemctl enable NetworkManager")

    if wmde == "gnome":
        run("arch-chroot /mnt systemctl enable gdm")
    elif wmde == "kde":
        run("arch-chroot /mnt systemctl enable sddm")

    if bootloader == "systemd-boot":
        run("arch-chroot /mnt bootctl install")
    elif bootloader == "grub":
        run("arch-chroot /mnt pacman -S --noconfirm grub efibootmgr")
        run("arch-chroot /mnt grub-install --target=x86_64-efi --efi-directory=/boot --bootloader-id=GRUB")
        run("arch-chroot /mnt grub-mkconfig -o /boot/grub/grub.cfg")

    username = "long"
    run(f"arch-chroot /mnt useradd -m -G wheel -s /bin/bash {username}")
    run(f"arch-chroot /mnt passwd {username}")
    run("arch-chroot /mnt bash -c \"echo '%wheel ALL=(ALL:ALL) ALL' >> /etc/sudoers\"")

    stdscr.clear()
    stdscr.addstr(0, 0, f"✅ Cài đặt hoàn tất! Log ở {logfile}\nReboot để vào Arch.")
    stdscr.refresh()
    stdscr.getch()

if __name__ == "__main__":
    curses.wrapper(main)

