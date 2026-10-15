"""Linha de comando: nova-control [gui|status|profile|boost|light|daemon|apply]."""

from __future__ import annotations

import argparse
import sys

from . import config
from .i18n import _
from .procname import set_process_name
from .lighting import EFFECTS, ELC, LightingError, apply_lighting_config, find_device
from .thermal import PROFILE_LABELS, Thermal, ThermalError


def parse_color(s: str) -> list[int]:
    s = s.lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError(_("color must be RRGGBB"))
    return [int(s[i : i + 2], 16) for i in (0, 2, 4)]


def cmd_status(_a):
    th = Thermal()
    print(_("Profile: {profile}  (options: {options})").format(
        profile=th.profile(), options=", ".join(th.profiles())))
    for t in th.temps():
        print(f"  {t.label:<8} {t.celsius:5.1f} °C")
    for f in th.fans():
        print(_("  {label:<8} {rpm:5d} RPM  (max {max})  boost {boost}/255").format(
            label=f.label, rpm=f.rpm, max=f.rpm_max, boost=f.boost))
    print(_("Write access: {answer}").format(answer=_("yes") if th.can_write() else _("no")))
    dev = find_device()
    if dev:
        try:
            with ELC(dev) as elc:
                conf = elc.config()
                print(_("LEDs: {device}  firmware {firmware}  platform {platform}  zones {zones}").format(
                    device=dev, firmware=elc.firmware(),
                    platform=("0x%04x" % conf[0]) if conf else "?", zones=conf[1] if conf else "?"))
        except LightingError as e:
            print(f"LEDs: {dev} ({e})")
    else:
        print(_("LEDs: AW-ELC controller not found"))


def cmd_profile(a):
    th = Thermal()
    th.set_profile(a.name)
    cfg = config.load()
    cfg["thermal"]["profile"] = a.name
    config.save(cfg)
    print(_("Profile: {profile}").format(profile=a.name))


def cmd_boost(a):
    th = Thermal()
    cfg = config.load()
    val = round(a.percent * 255 / 100)
    th.set_profile("custom")
    th.set_boost(a.fan, val)
    cfg["thermal"]["fan_mode"] = "manual"
    cfg["thermal"]["boost"][str(a.fan)] = val
    config.save(cfg)
    print(_("Fan {fan}: boost {percent}%").format(fan=a.fan, percent=a.percent))


def cmd_light(a):
    cfg = config.load()
    lc = cfg["lighting"]
    zones = a.zones if a.zones is not None else list(range(lc["zone_count"]))
    for z in zones:
        zc = config.zone_cfg(cfg, z)
        zc["effect"] = a.effect
        if a.color:
            zc["colors"] = [a.color, a.color2 or zc["colors"][-1]]
        zc["speed"] = a.speed
    if a.brightness is not None:
        lc["brightness"] = a.brightness
    config.save(cfg)
    apply_lighting_config(lc)
    print(_("Lighting applied"))


def cmd_identify(a):
    cfg = config.load()
    with ELC() as elc:
        elc.identify(a.zone, list(range(cfg["lighting"]["zone_count"])))


def main(argv=None):
    p = argparse.ArgumentParser(prog="nova-control",
                                description=_("Fan control, thermal profiles and RGB lighting for Alienware laptops."))
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("gui", help=_("open the graphical interface (default)"))
    sub.add_parser("status", help=_("show temperatures, fans, profile and LEDs")).set_defaults(func=cmd_status)
    sp = sub.add_parser("profile", help=_("set the thermal profile"))
    sp.add_argument("name", choices=list(PROFILE_LABELS))
    sp.set_defaults(func=cmd_profile)
    sb = sub.add_parser("boost", help=_("manual boost for one fan (0-100%%)"))
    sb.add_argument("fan", type=int, choices=[1, 2])
    sb.add_argument("percent", type=int)
    sb.set_defaults(func=cmd_boost)
    sl = sub.add_parser("light", help=_("set the lighting"))
    sl.add_argument("effect", choices=list(EFFECTS))
    sl.add_argument("color", type=parse_color, nargs="?")
    sl.add_argument("--color2", type=parse_color)
    sl.add_argument("--speed", type=int, default=50)
    sl.add_argument("--brightness", type=int)
    sl.add_argument("--zones", type=int, nargs="+")
    sl.set_defaults(func=cmd_light)
    si = sub.add_parser("identify", help=_("flash a single zone"))
    si.add_argument("zone", type=int)
    si.set_defaults(func=cmd_identify)
    sub.add_parser("daemon", help=_("service: apply settings and run the fan curve"))
    sub.add_parser("apply", help=_("apply the saved settings once"))

    a = p.parse_args(argv)
    set_process_name(sys.argv[1:] if argv is None else argv)
    if a.cmd in (None, "gui"):
        from .gui import main as gui_main
        return gui_main()
    if a.cmd == "daemon":
        from .daemon import main as dmain
        return dmain([])
    if a.cmd == "apply":
        from .daemon import main as dmain
        return dmain(["--apply-once"])
    try:
        a.func(a)
    except (ThermalError, LightingError, OSError) as e:
        print(_("Error: {error}").format(error=e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
