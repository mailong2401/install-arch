
---

# 🚀 Arch Linux Auto Installer (Curses Menu)

A Python-based **Arch Linux auto installer** with a simple text-based UI powered by `curses`.  
Instead of typing long commands, you just select your options from menus — the script will then automatically:

- Partition and mount disks  
- Install the base system  
- Set up drivers, kernel, WM/DE, and bootloader  
- Configure users and system defaults  

Perfect for quickly getting a working Arch system up and running. ⚡

---

## 📦 Requirements

- Boot into the official **Arch Linux ISO**  
- Ensure you have **network access** (`ping archlinux.org`)  
- **Python 3** is already included in the ISO  

---

## 🔧 Installation

Clone the repository and run the script:

```bash
git clone https://github.com/yourname/arch-auto-installer.git
cd arch-auto-installer
chmod +x installer.py
python3 installer.py
```

---

## 🖥️ Features

* Disk selection via `lsblk`
* Automatic partitioning:

  * **EFI**: 1G (FAT32)
  * **Root**: remaining space (ext4)
* User creation with password
* Kernel options: `linux`, `linux-lts`, `linux-zen`
* GPU drivers: `intel`, `amd`, `nvidia`
* WM/DE selection: `bspwm`, `hyprland`, `gnome`, `kde`
* Bootloader: `systemd-boot` or `grub`
* Base system installation with `pacstrap`
* Auto configuration: timezone, locale, `NetworkManager`
* User added to `wheel` group with sudo access

---

## 📋 Example Menu

```
[ Choose Kernel ]
 > linux
   linux-lts
   linux-zen

 SELECTED CONFIG
 Disk: /dev/sda (512G)
 Username: long
 Kernel: linux
 GPU: intel
 WM/DE: bspwm
 Bootloader: grub
```

---

## 🧪 Testing in VM

### VirtualBox

1. Create a new VM → Linux → Arch Linux (64-bit)
2. Attach the official **Arch Linux ISO**
3. Boot into the live environment
4. Run:

   ```bash
   pacman -Sy git python
   ```
5. Clone the repo and run the script

### QEMU

```bash
qemu-img create -f qcow2 arch-test.qcow2 20G
qemu-system-x86_64 -m 4G -cdrom archlinux.iso -boot d arch-test.qcow2
```

Then run the installer from inside the ISO.

---

## 🔄 Installation Flow

1. **Select Disk** → detected with `lsblk`
2. **User Setup** → set username & password
3. **Kernel Selection** → choose Linux kernel variant
4. **GPU Driver** → install required driver
5. **WM/DE** → pick your environment
6. **Bootloader** → `systemd-boot` or `grub`
7. **Summary Screen** → review all choices
8. **Installation** → script executes:

   * Partition (EFI + Root)
   * Mount partitions
   * Install system & selected packages
   * Configure timezone & locale
   * Enable `NetworkManager`
   * Install bootloader
   * Create user + password
9. **Reboot** → into your new Arch system 🎉

---

## ⚠️ Warning

* This script will **erase the entire disk** you select
* Always test in a **VM** before using on real hardware

---

## 📜 Logs

All installation steps are saved in:

```
~/install.log
```

---

## 🔮 Roadmap

* [ ] Progress bar during installation
* [ ] Manual partitioning option
* [ ] Install additional packages
* [ ] Safer dual-boot support

---

## 📜 License

Licensed under the **MIT License**.
Free to use, modify, and share.

---

## 👨‍💻 Author

Created by **Mai Duong Long** – Arch Linux enthusiast & automation lover.
Contributions and pull requests are welcome! 🚀
