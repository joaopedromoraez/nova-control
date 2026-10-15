"""Configuração persistente em ~/.config/nova-control/config.json."""

from __future__ import annotations

import copy
import re
import json
import os

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "nova-control")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CURVE = [[40, 0], [55, 15], [70, 45], [80, 75], [90, 100]]

DEFAULTS = {
    # "auto" segue o idioma do sistema; ou "en", "pt_BR", "es"…
    "language": "auto",
    "thermal": {
        "profile": "balanced",
        # auto   = firmware decide (boost 0)
        # manual = boost fixo por fan
        # curve  = daemon ajusta boost conforme temperatura
        "fan_mode": "auto",
        "boost": {"1": 0, "2": 0},
        "curves": {"1": DEFAULT_CURVE, "2": DEFAULT_CURVE},
    },
    "lighting": {
        "enabled": True,
        "zone_count": 8,
        "brightness": 100,
        "zones": {},
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


LEGACY_PATH = os.path.join(os.path.dirname(CONFIG_DIR), "alienware-control", "config.json")


def load() -> dict:
    if not os.path.exists(CONFIG_PATH) and os.path.exists(LEGACY_PATH):
        # migra a configuração do nome antigo do projeto
        os.makedirs(CONFIG_DIR, exist_ok=True)
        os.replace(LEGACY_PATH, CONFIG_PATH)
        try:
            os.rmdir(os.path.dirname(LEGACY_PATH))
        except OSError:
            pass
    try:
        with open(CONFIG_PATH) as f:
            return _merge(DEFAULTS, json.load(f))
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULTS)


def save(cfg: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_PATH)


def mtime() -> float:
    try:
        return os.stat(CONFIG_PATH).st_mtime
    except OSError:
        return 0.0


def zone_cfg(cfg: dict, zone: int) -> dict:
    zones = cfg["lighting"].setdefault("zones", {})
    zc = zones.setdefault(str(zone), {
        "name": "",
        "effect": "static",
        "colors": [[0, 128, 255], [255, 0, 128]],
        "speed": 50,
    })
    # nomes padrão gravados por versões antigas ("Zona 3") viram "sem nome" para seguir o idioma
    if re.fullmatch(r"Zona \d+", zc.get("name", "")):
        zc["name"] = ""
    return zc


def zone_name(cfg: dict, zone: int) -> str:
    """Nome dado pelo usuário ou o nome padrão traduzido ("Zone 1", "Zona 1"…)."""
    from .i18n import _
    return zone_cfg(cfg, zone).get("name") or _("Zone {number}").format(number=zone + 1)
