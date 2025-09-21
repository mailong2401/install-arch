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

def list_partitions(disk):
    out = subprocess.check_output(f"lsblk -ln -o NAME,TYPE,SIZE {disk}", shell=True, text=True)
    parts = []
    for line in out.strip().split("\n"):
        cols = line.split()
        if cols[1] == "part":
            dev = f"/dev/{cols[0]}"
            size = cols[2]
            parts.append(f"{dev} ({size})")
    return parts

def choose_partition(stdscr, disk, label):
    while True:
        parts = list_partitions(disk)
        parts.append("[Tạo phân vùng mới bằng cfdisk]")
        choice = curses_menu(stdscr, f"Chọn {label} Partition", parts)

        if choice.startswith("[Tạo"):
            curses.endwin()
            subprocess.run(f"cfdisk {disk}", shell=True)
            stdscr.clear()
            continue
        else:
            return choice.split()[0]

def run(cmd):
    print(f"[RUN] {cmd}")
    logging.info(f"Running: {cmd}")
    subprocess.run(cmd, shell=True, check=True)

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

    parser = argparse.ArgumentParser(description="Mini Arch Installer")
    parser.add_argument("--disk", default="/dev/nvme0n1", help="Target disk")
    args, _ = parser.parse_known_args()

    kernel = curses_menu(stdscr, "Chọn Kernel", ["linux", "linux-lts", "linux-zen"])
    gpu = curses_menu(stdscr, "Chọn GPU Driver", ["intel", "amd", "nvidia"])
    wmde = curses_menu(stdscr, "Chọn WM/DE", ["bspwm", "hyprland", "gnome", "kde"])
    bootloader = curses_menu(stdscr, "Chọn Bootloader", ["systemd-boot", "grub"])

    stdscr.clear()
    stdscr.addstr(0, 0,
        f"Disk: {args.disk}\nKernel: {kernel}\nGPU: {gpu}\nWM/DE: {wmde}\nBootloader: {bootloader}")
    stdscr.addstr(6, 0, "Nhấn Enter để bắt đầu cài đặt...")
    stdscr.refresh()
    stdscr.getch()

    # ---- partition chọn qua menu/cfdisk ----
    efi_partition = choose_partition(stdscr, args.disk, "EFI")
    root_partition = choose_partition(stdscr, args.disk, "Root")

    run(f"mkfs.fat -F32 {efi_partition}")
    run(f"mkfs.ext4 {root_partition}")
    run(f"mount {root_partition} /mnt")
    run("mkdir -p /mnt/boot")
    run(f"mount {efi_partition} /mnt/boot")

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

