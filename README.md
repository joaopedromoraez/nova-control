<div align="center">

<img src="data/icons/io.github.nova_control.svg" width="128" height="128" alt="Nova Control logo">

# Nova Control

**Alienware Command Center (AWCC) alternative for Linux: fan control, thermal profiles, G-Mode and AlienFX RGB lighting.**

A native GTK4 / libadwaita app for Alienware gaming laptops on Ubuntu, Fedora and other Linux distributions.

**English** · [Português](README.pt-BR.md)

[![MIT License](https://img.shields.io/badge/license-MIT-3FBAF9)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/joaopedromoraez/nova-control?color=A08EFA)](https://github.com/joaopedromoraez/nova-control/releases)
![Linux](https://img.shields.io/badge/platform-Linux-A08EFA)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3FBAF9)
![GTK4 + libadwaita](https://img.shields.io/badge/GTK4-libadwaita-A08EFA)

</div>

---

<p align="center">
  <img src="docs/screenshot-curve.png" width="49%" alt="Nova Control fan curve editor and thermal profiles on an Alienware laptop running Linux">
  <img src="docs/screenshot-lighting.png" width="49%" alt="Nova Control AlienFX RGB keyboard lighting controls per zone on Linux">
</p>

Dell ships the **Alienware Command Center** only for Windows. On Linux there is no official way to change fan speed, switch thermal profiles, enable **G-Mode** or set the **RGB keyboard lighting**. Nova Control fills that gap with a native desktop app, a background service and a command-line tool. It runs **without root** after a one-time install.

## Features

### 🌡️ Fan control and thermal profiles
- **Live monitoring** of CPU/GPU temperature and fan RPM
- **Firmware thermal profiles**: Cool, Quiet, Balanced, Balanced Performance and Performance (**G-Mode**)
- **Three fan control modes**:
  - **Automatic**: firmware-managed
  - **Fixed boost**: a manual speed boost per fan
  - **Custom fan curve**: drag points on a temperature × speed graph

### 💡 AlienFX RGB lighting
- Effects: **static, breathing, pulse, two-color morph, spectrum, rainbow wave** and off
- **Brightness**, **speed** and **color** per zone or for all zones at once
- **Identify** button that flashes one zone at a time, so you can find and name each LED zone (keyboard, logo, rear strip…)
- One-click color presets

### ⚙️ Runs in the background
- A **systemd user service** re-applies your settings at login and after resume from suspend
- The custom fan curve keeps working **with the app closed**
- A full **command-line interface** for scripts and keyboard shortcuts

## Compatibility

| Tested on | |
|---|---|
| Laptop | Alienware m15 R6 |
| OS | Ubuntu 26.04 (GNOME) |
| Kernel | 7.0 |

Other recent Alienware laptops (m15, m16, m17, m18, x15, x16, x17 series) should work if:

- the kernel loads the `alienware_wmi` driver with **AWCC** support (fans and thermal profiles; kernel 6.15 or newer);
- the laptop has the **AW-ELC** lighting controller (USB `187c:0550` or `187c:0551`).

Check with:

```bash
lsusb | grep 187c
```

```bash
cat /sys/class/platform-profile/*/name
```

> [!NOTE]
> Tried it on another model? [Send a compatibility report](https://github.com/joaopedromoraez/nova-control/issues/new?template=compatibility.yml), even if it only partially works. It helps grow the list of supported laptops.

## Installation

Requires **GTK 4.14+** and **libadwaita 1.7+**: Ubuntu 25.04+, Fedora 42+, Debian 13+, Arch Linux and derivatives.

### Packages (recommended)

Download the package for your distribution from the [latest release](https://github.com/joaopedromoraez/nova-control/releases/latest), then install it:

| Distribution | Command |
|---|---|
| Ubuntu, Debian, Pop!_OS, Mint | `sudo apt install ./nova-control_*_all.deb` |
| Fedora, Nobara | `sudo dnf install ./nova-control-*.noarch.rpm` |
| Arch, Manjaro, CachyOS | `sudo pacman -U nova-control-*-any.pkg.tar.zst` |

The package:

1. installs **udev rules** so the hardware can be controlled **without root** (access for the `plugdev` group);
2. adds the user who ran the install to `plugdev`;
3. enables the `nova-control.service` user service for every user.

Log out and back in once, then open **Nova Control** from your app menu.

### From source

```bash
git clone https://github.com/joaopedromoraez/nova-control.git
cd nova-control
sudo ./install/install.sh
```

This installs to `/usr/local` using the same layout as the packages. Remove it with `sudo ./install/install.sh --uninstall`.

## Command line

```bash
nova-control                       # open the GUI
nova-control status                # temperatures, fans, profile and LEDs
nova-control profile performance   # thermal profile (enables G-Mode)
nova-control boost 1 60            # fan 1 (CPU) at 60% boost
nova-control light static 00b4ff --brightness 80
nova-control light morph ff0000 --color2 0000ff --speed 70
nova-control light wave            # rainbow wave
nova-control identify 0            # flash only zone 0
```

## How it works

Nova Control ships no kernel driver. It talks directly to interfaces the Linux kernel already provides.

| Feature | Interface |
|---|---|
| Thermal profiles and G-Mode | `/sys/class/platform-profile/*/profile` (`alienware_wmi` driver) |
| Fan speed | `/sys/class/hwmon/<alienware_wmi>/fanN_boost` (0–255) |
| Temperatures and RPM | `/sys/class/hwmon/<alienware_wmi>/{temp,fan}N_input` |
| RGB lighting | `/dev/hidrawN` of the AW-ELC controller, ELC protocol over 33-byte HID feature reports |

```
nova-control/
├── nova_control/
│   ├── gui.py        # GTK4 / libadwaita interface
│   ├── thermal.py    # profiles, fans and sensors (sysfs)
│   ├── lighting.py   # userspace AW-ELC driver
│   ├── daemon.py     # service: re-applies settings and runs the fan curve
│   ├── config.py     # ~/.config/nova-control/config.json
│   └── cli.py        # command line
├── data/             # udev rules, systemd unit, .desktop, AppStream metainfo, icons
├── packaging/        # install layout, nFPM config and package scripts
├── install/          # install from source
└── bin/nova-control
```

## Notes

- GNOME's **Power Mode** switch also changes the thermal profile. The most recent choice wins, whether made in GNOME or in Nova Control.
- In **Fixed boost** mode the firmware is switched to the `custom` profile, where manual fan control is reliable.
- The interface is currently in Brazilian Portuguese. Translations are welcome.
- Settings are stored in `~/.config/nova-control/config.json`.

## Uninstall

Use your package manager, for example `sudo apt remove nova-control`, `sudo dnf remove nova-control` or `sudo pacman -R nova-control`. Your settings stay in `~/.config/nova-control/`.

## Credits

The AW-ELC lighting protocol was documented by [OpenRGB](https://gitlab.com/CalcProgrammer1/OpenRGB) and [alienfx-tools](https://github.com/T-Troll/alienfx-tools). Fan and thermal profile support comes from the Linux kernel `alienware-wmi` driver.

*Alienware is a registered trademark of Dell Inc. This project is not affiliated with Dell or Alienware.*

## License

Released under the [MIT License](LICENSE).

If Nova Control is useful to you, please ⭐ the repository: it helps other Alienware owners on Linux find it.
