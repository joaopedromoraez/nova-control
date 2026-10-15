"""Linha de comando: nova-control [gui|status|profile|boost|light|daemon|apply]."""

from __future__ import annotations

import argparse
import sys

from . import config
from .lighting import EFFECTS, ELC, LightingError, apply_lighting_config, find_device
from .thermal import PROFILE_LABELS, Thermal, ThermalError


def parse_color(s: str) -> list[int]:
    s = s.lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError("cor deve ser RRGGBB")
    return [int(s[i : i + 2], 16) for i in (0, 2, 4)]


def cmd_status(_a):
    th = Thermal()
    print(f"Perfil: {th.profile()}  (opções: {', '.join(th.profiles())})")
    for t in th.temps():
        print(f"  {t.label:<8} {t.celsius:5.1f} °C")
    for f in th.fans():
        print(f"  {f.label:<8} {f.rpm:5d} RPM  (máx {f.rpm_max})  boost {f.boost}/255")
    print(f"Escrita permitida: {'sim' if th.can_write() else 'não'}")
    dev = find_device()
    if dev:
        try:
            with ELC(dev) as elc:
                conf = elc.config()
                print(f"LEDs: {dev}  firmware {elc.firmware()}  "
                      f"plataforma {('0x%04x' % conf[0]) if conf else '?'}  zonas {conf[1] if conf else '?'}")
        except LightingError as e:
            print(f"LEDs: {dev} ({e})")
    else:
        print("LEDs: controlador AW-ELC não encontrado")


def cmd_profile(a):
    th = Thermal()
    th.set_profile(a.name)
    cfg = config.load()
    cfg["thermal"]["profile"] = a.name
    config.save(cfg)
    print("Perfil:", a.name)


def cmd_boost(a):
    th = Thermal()
    cfg = config.load()
    val = round(a.percent * 255 / 100)
    th.set_profile("custom")
    th.set_boost(a.fan, val)
    cfg["thermal"]["fan_mode"] = "manual"
    cfg["thermal"]["boost"][str(a.fan)] = val
    config.save(cfg)
    print(f"Fan {a.fan}: boost {a.percent}%")


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
    print("Iluminação aplicada")


def cmd_identify(a):
    cfg = config.load()
    with ELC() as elc:
        elc.identify(a.zone, list(range(cfg["lighting"]["zone_count"])))


def main(argv=None):
    p = argparse.ArgumentParser(prog="nova-control",
                                description="Controle de fans, perfis térmicos e RGB para Alienware.")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("gui", help="abre a interface gráfica (padrão)")
    sub.add_parser("status", help="mostra temperaturas, fans, perfil e LEDs").set_defaults(func=cmd_status)
    sp = sub.add_parser("profile", help="define perfil térmico")
    sp.add_argument("name", choices=list(PROFILE_LABELS))
    sp.set_defaults(func=cmd_profile)
    sb = sub.add_parser("boost", help="boost manual de uma fan (0-100%%)")
    sb.add_argument("fan", type=int, choices=[1, 2])
    sb.add_argument("percent", type=int)
    sb.set_defaults(func=cmd_boost)
    sl = sub.add_parser("light", help="define iluminação")
    sl.add_argument("effect", choices=list(EFFECTS))
    sl.add_argument("color", type=parse_color, nargs="?")
    sl.add_argument("--color2", type=parse_color)
    sl.add_argument("--speed", type=int, default=50)
    sl.add_argument("--brightness", type=int)
    sl.add_argument("--zones", type=int, nargs="+")
    sl.set_defaults(func=cmd_light)
    si = sub.add_parser("identify", help="pisca apenas uma zona")
    si.add_argument("zone", type=int)
    si.set_defaults(func=cmd_identify)
    sub.add_parser("daemon", help="serviço: aplica configuração e curva de fans")
    sub.add_parser("apply", help="aplica a configuração salva uma vez")

    a = p.parse_args(argv)
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
        print("Erro:", e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
