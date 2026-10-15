"""Daemon de usuário: aplica a configuração salva e executa a curva de fans.

- No início: aplica perfil térmico, boost manual e iluminação.
- A cada 2 s: se fan_mode == "curve", ajusta fanN_boost conforme a temperatura.
- Recarrega a configuração quando o arquivo muda.
- Detecta retorno de suspensão (salto no relógio) e reaplica a iluminação.
"""

from __future__ import annotations

import signal
import sys
import time

from . import config
from .lighting import LightingError, apply_lighting_config
from .thermal import Thermal, ThermalError, interpolate_curve

INTERVAL = 2.0
DECAY_PER_TICK = 8  # boost desce no máximo isso por ciclo (evita "sobe-desce" da fan)


def log(*a):
    print("[nova-control]", *a, flush=True)


def apply_thermal(th: Thermal, cfg: dict) -> None:
    t = cfg["thermal"]
    prof = "custom" if t.get("fan_mode") == "manual" else t.get("profile")
    if prof and prof in th.profiles() and th.profile() != prof:
        th.set_profile(prof)
        log("perfil:", prof)
    if t.get("fan_mode") == "manual":
        for fan in th.fans():
            th.set_boost(fan.index, t["boost"].get(str(fan.index), 0))
    elif t.get("fan_mode") == "auto":
        for fan in th.fans():
            th.set_boost(fan.index, 0)


def apply_all(th: Thermal, cfg: dict) -> None:
    try:
        apply_thermal(th, cfg)
    except ThermalError as e:
        log("térmico:", e)
    if cfg["lighting"].get("enabled", True):
        try:
            apply_lighting_config(cfg["lighting"])
            log("iluminação aplicada")
        except (LightingError, OSError) as e:
            log("iluminação:", e)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    th = Thermal()
    if not th.available:
        log("driver alienware_wmi não encontrado")
    cfg = config.load()

    if "--apply-once" in argv:
        apply_all(th, cfg)
        return 0

    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    apply_all(th, cfg)
    last_mtime = config.mtime()
    last_wall = time.time()
    current: dict[int, int] = {}

    while running:
        time.sleep(INTERVAL)
        now = time.time()
        resumed = now - last_wall > INTERVAL * 5
        last_wall = now

        m = config.mtime()
        if m != last_mtime:
            last_mtime = m
            cfg = config.load()
            current.clear()
        if resumed:
            log("retorno de suspensão detectado; reaplicando")
            apply_all(th, cfg)
            current.clear()

        t = cfg["thermal"]
        if t.get("fan_mode") != "curve" or not th.available:
            continue
        try:
            for fan in th.fans():
                temp = th.temp_for_fan(fan.index)
                if temp is None:
                    continue
                curve = t["curves"].get(str(fan.index), config.DEFAULT_CURVE)
                target = interpolate_curve(curve, temp)
                prev = current.get(fan.index, fan.boost)
                if target < prev:
                    target = max(target, prev - DECAY_PER_TICK)
                if target != prev or fan.index not in current:
                    th.set_boost(fan.index, target)
                current[fan.index] = target
        except (ThermalError, OSError) as e:
            log("curva:", e)
            time.sleep(10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
