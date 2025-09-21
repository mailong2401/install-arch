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
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {cmd} - Error: {e}")
        print(f"ERROR: {e.stderr}")
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

# ---- Kiểm tra disk có được mount không ----
def is_disk_mounted(disk):
    try:
        result = subprocess.run(f"mount | grep {disk}", shell=True, capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False

# ---- Unmount disk nếu cần ----
def unmount_disk(disk):
    # Kiểm tra các partition có được mount không
    try:
        result = subprocess.run(f"lsblk -ln -o MOUNTPOINTS {disk} | grep -v '^$'", shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            mount_points = result.stdout.strip().split('\n')
            for mount_point in mount_points:
                if mount_point:
                    run(f"umount -f {mount_point}")
    except:
        pass
    
    # Thử unmount disk chính
    try:
        run(f"umount -f {disk}* 2>/dev/null || true")
    except:
        pass

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

# ---- Cấu hình locale ----
def setup_locale(locale_conf):
    # Cấu hình locale.gen
    locales_to_enable = [
        "en_US.UTF-8 UTF-8",
        "vi_VN.UTF-8 UTF-8",
        locale_conf["locale"] + " UTF-8"
    ]
    
    # Đảm bảo không trùng lặp
    unique_locales = list(set(locales_to_enable))
    
    with open("/mnt/etc/locale.gen", "r") as f:
        content = f.read()
    
    for locale in unique_locales:
        # Bỏ comment trước locale nếu cần
        content = content.replace(f"#{locale}", locale)
    
    with open("/mnt/etc/locale.gen", "w") as f:
        f.write(content)
    
    # Tạo locale.conf
    locale_content = f"""LANG={locale_conf['lang']}
LC_TIME={locale_conf['time_format']}
LC_NUMERIC={locale_conf['number_format']}
LC_MONETARY={locale_conf['currency_format']}
"""
    with open("/mnt/etc/locale.conf", "w") as f:
        f.write(locale_content)
    
    # Generate locales
    run("arch-chroot /mnt locale-gen")


# ---- Tạo file locale cho user (sau khi user được tạo) ----
def setup_user_locale(username, locale_conf):
    if not username:
        return

    # Tạo file locale.conf cho user trong chroot
    locale_content = f"""LANG={locale_conf['lang']}
LC_TIME={locale_conf['time_format']}
LC_NUMERIC={locale_conf['number_format']}
LC_MONETARY={locale_conf['currency_format']}
"""

    temp_path = f"/mnt/home/{username}/.config"
    os.makedirs(temp_path, exist_ok=True)
    with open(f"{temp_path}/locale.conf", "w") as f:
        f.write(locale_content)

    # Đảm bảo user sở hữu file này
    run(f"arch-chroot /mnt chown -R {username}:{username} /home/{username}/.config")



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
            # Hiển thị tối đa 2 dòng cho mỗi giá trị
            if len(str(value)) > w - x - 10:
                value_str = str(value)[:w - x - 13] + "..."
            else:
                value_str = str(value)
            stdscr.addstr(y, x, f"{key}: {value_str}")
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

def curses_input(stdscr, prompt, config, keyname, hidden=False, default=""):
    curses.curs_set(1)  # Hiện con trỏ
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    stdscr.addstr(0, 2, prompt)
    if default:
        stdscr.addstr(1, 2, f"(Mặc định: {default})")
    
    stdscr.refresh()
    
    inp = default
    cursor_pos = len(inp)
    
    while True:
        stdscr.move(2, 2)
        stdscr.clrtobot()
        if hidden:
            stdscr.addstr(2, 2, "*" * len(inp))
        else:
            stdscr.addstr(2, 2, inp)
        
        # Hiển thị vị trí con trỏ
        stdscr.move(2, 2 + cursor_pos)
        stdscr.refresh()
        
        ch = stdscr.getch()
        if ch in [curses.KEY_ENTER, 10, 13]:
            break
        elif ch in [curses.KEY_BACKSPACE, 127, 8]:
            if cursor_pos > 0:
                inp = inp[:cursor_pos-1] + inp[cursor_pos:]
                cursor_pos -= 1
        elif ch == curses.KEY_LEFT:
            cursor_pos = max(0, cursor_pos - 1)
        elif ch == curses.KEY_RIGHT:
            cursor_pos = min(len(inp), cursor_pos + 1)
        elif ch == 27:  # ESC key
            raise SystemExit("Hủy cài đặt")
        elif ch in [curses.KEY_HOME, 1]:  # Home key or Ctrl+A
            cursor_pos = 0
        elif ch in [curses.KEY_END, 5]:  # End key or Ctrl+E
            cursor_pos = len(inp)
        elif ch in [21, 11]:  # Ctrl+U or Ctrl+K
            inp = ""
            cursor_pos = 0
        elif 32 <= ch <= 126:  # Ký tự có thể in được
            inp = inp[:cursor_pos] + chr(ch) + inp[cursor_pos:]
            cursor_pos += 1
    
    curses.curs_set(0)  # Ẩn con trỏ
    config[keyname] = inp.strip()
    return inp.strip()

# ---- Lấy danh sách locale có sẵn ----
def get_available_locales():
    try:
        result = subprocess.run("locale -a", shell=True, capture_output=True, text=True)
        return result.stdout.strip().split('\n')
    except:
        return ["en_US.UTF-8", "vi_VN.UTF-8", "C.UTF-8"]

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

    # --- cấu hình locale ---
    locale_config = {}
    locale_choice = curses_menu(stdscr, "Cấu hình locale?", ["Có", "Không"], config, "Cấu hình locale?")
    
    if locale_choice == "Có":
        # Chọn locale chính
        available_locales = get_available_locales()
        main_locale = curses_menu(stdscr, "Chọn locale chính", available_locales, config, "Locale chính")
        
        # Chọn các cài đặt locale cụ thể
        locale_config['locale'] = main_locale
        locale_config['lang'] = curses_input(stdscr, "Ngôn ngữ hệ thống (LANG):", config, "LANG", default=main_locale.split('.')[0])
        locale_config['time_format'] = curses_input(stdscr, "Định dạng thời gian (LC_TIME):", config, "LC_TIME", default=main_locale)
        locale_config['number_format'] = curses_input(stdscr, "Định dạng số (LC_NUMERIC):", config, "LC_NUMERIC", default=main_locale)
        locale_config['currency_format'] = curses_input(stdscr, "Định dạng tiền tệ (LC_MONETARY):", config, "LC_MONETARY", default=main_locale)
    else:
        # Sử dụng mặc định
        locale_config = {
            'locale': 'en_US.UTF-8',
            'lang': 'en_US.UTF-8',
            'time_format': 'en_US.UTF-8',
            'number_format': 'en_US.UTF-8',
            'currency_format': 'en_US.UTF-8'
        }

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

    # ---- Unmount disk trước khi thao tác ----
    stdscr.clear()
    stdscr.addstr(0, 0, "Đang unmount disk...")
    stdscr.refresh()
    unmount_disk(chosen_disk)

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

    # ---- Cấu hình locale ----
    setup_locale(locale_config)

    # ---- system config ----
    run("arch-chroot /mnt ln -sf /usr/share/zoneinfo/Asia/Ho_Chi_Minh /etc/localtime")
    run("arch-chroot /mnt hwclock --systohc")
    
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

        # Tạo file locale cho user (sau khi user đã được tạo)
        setup_user_locale(username, locale_config)

    stdscr.clear()
    stdscr.addstr(0, 0, f"✅ Cài đặt hoàn tất! Log ở {logfile}\nNhấn Enter để reboot hoặc ESC để không reboot.")
    stdscr.refresh()
    
    key = stdscr.getch()
    if key not in [27]:  # Không phải ESC
        run("reboot")

if __name__ == "__main__":
    curses.wrapper(main)
