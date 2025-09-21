#!/usr/bin/env python3
import subprocess
import curses
import logging
import os
import re

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
    try:
        subprocess.run(cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {cmd} - Error: {e}")
        raise

def list_disks():
    out = subprocess.check_output("lsblk -d -n -o NAME,SIZE,TYPE", shell=True, text=True)
    disks = []
    for line in out.strip().split("\n"):
        parts = line.split()
        if len(parts) >= 3 and parts[2] == "disk":
            name, size = parts[0], parts[1]
            disks.append(f"/dev/{name} ({size})")
    return disks

# ---- Kiểm tra UEFI ----
def check_efi():
    return os.path.exists("/sys/firmware/efi")

# ---- Tối ưu mirrorlist ----
def optimize_mirrorlist():
    run("pacman -S --noconfirm reflector")
    run("reflector --country Vietnam --age 12 --protocol https --sort rate --save /etc/pacman.d/mirrorlist")

# ---- Thêm microcode ----
def add_microcode():
    # Kiểm tra CPU và thêm microcode phù hợp
    try:
        with open("/proc/cpuinfo", "r") as f:
            cpuinfo = f.read()
        
        if "GenuineIntel" in cpuinfo:
            run("pacstrap /mnt intel-ucode")
            return "intel-ucode.img"
        elif "AuthenticAMD" in cpuinfo:
            run("pacstrap /mnt amd-ucode")
            return "amd-ucode.img"
    except Exception as e:
        logging.warning(f"Could not determine CPU type: {e}")
    
    return None

# ---- Tạo swap file ----
def setup_swapfile():
    run("dd if=/dev/zero of=/mnt/swapfile bs=1M count=2048 status=progress")
    run("chmod 600 /mnt/swapfile")
    run("mkswap /mnt/swapfile")
    run("echo '/swapfile none swap defaults 0 0' >> /mnt/etc/fstab")

# ---- Cấu hình systemd-boot ----
def setup_systemd_boot(root_partition, kernel, gpu):
    run("arch-chroot /mnt bootctl install")
    
    # Tạo file loader.conf
    loader_conf = """default arch.conf
timeout 3
console-mode keep
editor no
"""
    with open("/mnt/boot/loader/loader.conf", "w") as f:
        f.write(loader_conf)
    
    # Thêm microcode nếu có
    microcode_initrd = ""
    microcode_file = add_microcode()
    if microcode_file:
        microcode_initrd = f"initrd /{microcode_file}\n"
    
    # Tạo entry Arch Linux chính
    options = f"root={root_partition} rw quiet"
    if gpu == "nvidia":
        options += " nvidia-drm.modeset=1"
    
    arch_entry = f"""title Arch Linux ({kernel})
linux /vmlinuz-{kernel}
{microcode_initrd}initrd /initramfs-{kernel}.img
options {options}
"""
    os.makedirs("/mnt/boot/loader/entries", exist_ok=True)
    with open("/mnt/boot/loader/entries/arch.conf", "w") as f:
        f.write(arch_entry)
    
    # Tạo entry fallback
    arch_fallback = f"""title Arch Linux ({kernel}) (fallback)
linux /vmlinuz-{kernel}
{microcode_initrd}initrd /initramfs-{kernel}-fallback.img
options {options}
"""
    with open("/mnt/boot/loader/entries/arch-fallback.conf", "w") as f:
        f.write(arch_fallback)

# ---- Cấu hình GRUB ----
def setup_grub(root_partition):
    run("arch-chroot /mnt pacman -S --noconfirm grub efibootmgr")
    run(f"arch-chroot /mnt grub-install --target=x86_64-efi --efi-directory=/boot --bootloader-id=GRUB")
    
    # Thêm microcode nếu có
    microcode_file = add_microcode()
    if microcode_file:
        run(f"arch-chroot /mnt sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT=\"/GRUB_CMDLINE_LINUX_DEFAULT=\"initrd=\\\\{microcode_file} /' /etc/default/grub")
    
    run("arch-chroot /mnt grub-mkconfig -o /boot/grub/grub.cfg")

# ---- UI helper ----
def draw_summary(stdscr, config):
    h, w = stdscr.getmaxyx()
    x = w//2 + 2
    stdscr.attron(curses.color_pair(2))
    stdscr.addstr(0, x, " CẤU HÌNH ĐÃ CHỌN ")
    stdscr.attroff(curses.color_pair(2))
    y = 2
    for key, value in config.items():
        if y < h-1:
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

        for idx, option in enumerate(options):
            x = 2
            y = h//2 - len(options)//2 + idx
            if y < h and y >= 0:
                if idx == current:
                    stdscr.attron(curses.color_pair(2))
                    stdscr.addstr(y, x, f"> {option}")
                    stdscr.attroff(curses.color_pair(2))
                else:
                    stdscr.addstr(y, x, f"  {option}")

        draw_summary(stdscr, config)

        key = stdscr.getch()
        if key == curses.KEY_UP and current > 0:
            current -= 1
        elif key == curses.KEY_DOWN and current < len(options)-1:
            current += 1
        elif key in [curses.KEY_ENTER, 10, 13]:
            config[keyname] = options[current]
            return options[current]
        elif key == 27:  # ESC key
            raise SystemExit("Hủy cài đặt")

def curses_input(stdscr, prompt, config, keyname, hidden=False):
    curses.echo()
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    stdscr.addstr(0, 2, prompt)
    stdscr.refresh()
    
    if hidden:
        curses.noecho()
        inp = ""
        while True:
            ch = stdscr.getch()
            if ch in [curses.KEY_ENTER, 10, 13]:
                break
            elif ch in [curses.KEY_BACKSPACE, 127]:
                inp = inp[:-1]
                stdscr.move(1, 2)
                stdscr.clrtoeol()
                stdscr.addstr(1, 2, "*" * len(inp))
            elif ch == 27:  # ESC key
                raise SystemExit("Hủy cài đặt")
            else:
                inp += chr(ch)
                stdscr.addstr(1, 2, "*" * len(inp))
            stdscr.refresh()
    else:
        curses.echo()
        stdscr.addstr(1, 2, " " * 20)
        stdscr.refresh()
        inp = stdscr.getstr(1, 2, 20).decode("utf-8")
    
    curses.noecho()
    config[keyname] = inp.strip()
    return inp.strip()

# ---- main ----
def main(stdscr):
    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)   # title
    curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)   # highlight

    # Kiểm tra UEFI
    if not check_efi():
        stdscr.addstr(0, 0, "❌ Hệ thống không hỗ trợ UEFI! Chỉ hỗ trợ UEFI.")
        stdscr.refresh()
        stdscr.getch()
        raise SystemExit("Hệ thống không hỗ trợ UEFI")

    config = {}

    # --- chọn disk ---
    disks = list_disks()
    if not disks:
        raise SystemExit("❌ Không tìm thấy disk nào!")
    chosen_disk = curses_menu(stdscr, "Chọn Disk để cài đặt", disks, config, "Disk")
    chosen_disk = chosen_disk.split()[0]   # lấy /dev/sdX

    # --- user + password ---
    make_user = curses_menu(stdscr, "Tạo user?", ["Có", "Không"], config, "User?")
    username = userpass = None
    if make_user == "Có":
        username = curses_input(stdscr, "Nhập tên user:", config, "Username")
        userpass = curses_input(stdscr, "Nhập password:", config, "Password", hidden=True)
    else:
        config["Username"] = "root only"

    rootpass = curses_input(stdscr, "Nhập mật khẩu root:", config, "Root Password", hidden=True)

    # --- chọn kernel, gpu, wm/de, bootloader ---
    kernel = curses_menu(stdscr, "Chọn Kernel", ["linux", "linux-lts", "linux-zen"], config, "Kernel")
    gpu = curses_menu(stdscr, "Chọn GPU Driver", ["intel", "amd", "nvidia"], config, "GPU")
    wmde = curses_menu(stdscr, "Chọn WM/DE", ["bspwm", "hyprland", "gnome", "kde"], config, "WM/DE")
    bootloader = curses_menu(stdscr, "Chọn Bootloader", ["systemd-boot", "grub"], config, "Bootloader")

    # --- swap file ---
    swap_choice = curses_menu(stdscr, "Tạo swap file?", ["Có", "Không"], config, "Swap file")
    use_swap = (swap_choice == "Có")

    # --- summary final ---
    stdscr.clear()
    stdscr.addstr(0, 2, "TÓM TẮT CẤU HÌNH", curses.A_BOLD)
    y = 2
    for k, v in config.items():
        if y < curses.LINES-1:
            stdscr.addstr(y, 2, f"{k}: {v}")
        y += 1
    stdscr.addstr(y+2, 2, "Nhấn Enter để bắt đầu cài đặt, ESC để hủy...")
    stdscr.refresh()
    
    key = stdscr.getch()
    if key == 27:  # ESC key
        raise SystemExit("Hủy cài đặt")

    # ---- auto partition ----
    run(f"wipefs -a {chosen_disk}")
    run(f"sgdisk -Z {chosen_disk}")
    run(f"sgdisk -o {chosen_disk}")
    run(f"sgdisk -n 1:0:+1G -t 1:ef00 {chosen_disk}")
    run(f"sgdisk -n 2:0:0 -t 2:8300 {chosen_disk}")

    efi_partition = f"{chosen_disk}1"
    root_partition = f"{chosen_disk}2"

    run(f"mkfs.fat -F32 {efi_partition}")
    run(f"mkfs.ext4 -F {root_partition}")
    run(f"mount {root_partition} /mnt")
    run("mkdir -p /mnt/boot")
    run(f"mount {efi_partition} /mnt/boot")

    # ---- Tối ưu mirrorlist ----
    optimize_mirrorlist()

    # ---- base install ----
    pkgs = f"base {kernel} {kernel}-headers networkmanager sudo"
    if gpu == "nvidia":
        pkgs += " nvidia-dkms nvidia-utils nvidia-settings"
    elif gpu == "amd":
        pkgs += " xf86-video-amdgpu mesa vulkan-radeon"
    elif gpu == "intel":
        pkgs += " mesa vulkan-intel xf86-video-intel"

    if wmde == "bspwm":
        pkgs += " bspwm sxhkd alacritty polybar xorg xorg-xinit"
    elif wmde == "hyprland":
        pkgs += " hyprland waybar alacritty xdg-desktop-portal-hyprland"
    elif wmde == "gnome":
        pkgs += " gnome gdm"
    elif wmde == "kde":
        pkgs += " plasma sddm konsole"

    run(f"pacstrap -K /mnt {pkgs}")
    run("genfstab -U /mnt >> /mnt/etc/fstab")

    # ---- Tạo swap file nếu được chọn ----
    if use_swap:
        setup_swapfile()

    # ---- system config ----
    run("arch-chroot /mnt ln -sf /usr/share/zoneinfo/Asia/Ho_Chi_Minh /etc/localtime")
    run("arch-chroot /mnt hwclock --systohc")
    
    # Cấu hình locale
    run("arch-chroot /mnt sed -i 's/^#en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen")
    run("arch-chroot /mnt sed -i 's/^#vi_VN.UTF-8/vi_VN.UTF-8/' /etc/locale.gen")
    run("arch-chroot /mnt locale-gen")
    run("arch-chroot /mnt bash -c 'echo \"LANG=en_US.UTF-8\" > /etc/locale.conf'")
    
    run("arch-chroot /mnt systemctl enable NetworkManager")

    if wmde == "gnome":
        run("arch-chroot /mnt systemctl enable gdm")
    elif wmde == "kde":
        run("arch-chroot /mnt systemctl enable sddm")

    # ---- Cấu hình bootloader ----
    if bootloader == "systemd-boot":
        setup_systemd_boot(root_partition, kernel, gpu)
    elif bootloader == "grub":
        setup_grub(root_partition)

    # ---- set root password ----
    run(f"arch-chroot /mnt bash -c \"echo 'root:{rootpass}' | chpasswd\"")

    # ---- create user ----
    if username:
        run(f"arch-chroot /mnt useradd -m -G wheel -s /bin/bash {username}")
        run(f"arch-chroot /mnt bash -c \"echo '{username}:{userpass}' | chpasswd\"")
        run("arch-chroot /mnt bash -c \"echo '%wheel ALL=(ALL:ALL) ALL' >> /etc/sudoers\"")

        # Tạo thư mục cấu hình cho user
        run(f"arch-chroot /mnt mkdir -p /home/{username}/.config")
        run(f"arch-chroot /mnt chown -R {username}:{username} /home/{username}")

    stdscr.clear()
    stdscr.addstr(0, 0, f"✅ Cài đặt hoàn tất! Log ở {logfile}\nNhấn Enter để reboot hoặc ESC để không reboot.")
    stdscr.refresh()
    
    key = stdscr.getch()
    if key not in [27]:  # Không phải ESC
        run("reboot")

if __name__ == "__main__":
    curses.wrapper(main)
