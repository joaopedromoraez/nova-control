"""Controle térmico via driver do kernel `alienware_wmi` (interface AWCC).

Usa apenas sysfs:
  * /sys/class/platform-profile/<dev>/profile  -> perfis térmicos (G-Mode = "performance")
  * /sys/class/hwmon/<alienware_wmi>/fanN_*     -> RPM, boost (0-255)
  * /sys/class/hwmon/<alienware_wmi>/tempN_*    -> temperaturas CPU/GPU
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass

PROFILE_LABELS = {
    "quiet": "Silencioso",
    "cool": "Frio",
    "balanced": "Equilibrado",
    "balanced-performance": "Equilibrado+",
    "performance": "Desempenho",
    "custom": "Personalizado (manual)",
}


class ThermalError(Exception):
    pass


@dataclass
class Fan:
    index: int
    label: str
    rpm: int
    rpm_max: int
    boost: int


@dataclass
class Temp:
    index: int
    label: str
    celsius: float


def _read(path: str) -> str:
    with open(path) as f:
        return f.read().strip()


def _write(path: str, value: str) -> None:
    try:
        with open(path, "w") as f:
            f.write(value)
    except PermissionError as e:
        raise ThermalError(
            f"Sem permissão para escrever em {path}. Rode install/install.sh (uma vez, com sudo)."
        ) from e
    except OSError as e:
        raise ThermalError(f"Falha ao escrever '{value}' em {path}: {e}") from e


class Thermal:
    def __init__(self) -> None:
        self.hwmon = self._find_hwmon()
        self.profile_dir = self._find_profile_dir()

    # ---- descoberta -----------------------------------------------------
    @staticmethod
    def _find_hwmon() -> str | None:
        for h in glob.glob("/sys/class/hwmon/hwmon*"):
            try:
                if _read(os.path.join(h, "name")) == "alienware_wmi":
                    return h
            except OSError:
                continue
        return None

    @staticmethod
    def _find_profile_dir() -> str | None:
        for p in glob.glob("/sys/class/platform-profile/platform-profile-*"):
            try:
                if _read(os.path.join(p, "name")) == "alienware-wmi":
                    return p
            except OSError:
                continue
        if os.path.exists("/sys/firmware/acpi/platform_profile"):
            return None  # fallback tratado nas funções
        return None

    @property
    def available(self) -> bool:
        return self.hwmon is not None

    def _profile_path(self, leaf: str) -> str:
        if self.profile_dir:
            return os.path.join(self.profile_dir, "profile" if leaf == "profile" else "choices")
        return "/sys/firmware/acpi/platform_profile" + ("" if leaf == "profile" else "_choices")

    # ---- perfis ---------------------------------------------------------
    def profiles(self) -> list[str]:
        try:
            return _read(self._profile_path("choices")).split()
        except OSError:
            return []

    def profile(self) -> str | None:
        try:
            return _read(self._profile_path("profile"))
        except OSError:
            return None

    def set_profile(self, name: str) -> None:
        if name not in self.profiles():
            raise ThermalError(f"Perfil desconhecido: {name}")
        _write(self._profile_path("profile"), name)

    # ---- sensores -------------------------------------------------------
    def fans(self) -> list[Fan]:
        out = []
        if not self.hwmon:
            return out
        for i in range(1, 5):
            base = os.path.join(self.hwmon, f"fan{i}_")
            if not os.path.exists(base + "input"):
                continue
            out.append(
                Fan(
                    index=i,
                    label=_read(base + "label") if os.path.exists(base + "label") else f"Fan {i}",
                    rpm=int(_read(base + "input")),
                    rpm_max=int(_read(base + "max")) if os.path.exists(base + "max") else 0,
                    boost=int(_read(base + "boost")) if os.path.exists(base + "boost") else 0,
                )
            )
        return out

    def temps(self) -> list[Temp]:
        out = []
        if not self.hwmon:
            return out
        for i in range(1, 9):
            base = os.path.join(self.hwmon, f"temp{i}_")
            if not os.path.exists(base + "input"):
                continue
            out.append(
                Temp(
                    index=i,
                    label=_read(base + "label") if os.path.exists(base + "label") else f"Temp {i}",
                    celsius=int(_read(base + "input")) / 1000.0,
                )
            )
        return out

    def temp_for_fan(self, fan_index: int) -> float | None:
        """Temperatura associada à fan (pwmN_auto_channels_temp é um bitmask de temps)."""
        mask_path = os.path.join(self.hwmon or "", f"pwm{fan_index}_auto_channels_temp")
        temps = {t.index: t.celsius for t in self.temps()}
        try:
            mask = int(_read(mask_path))
            vals = [temps[b + 1] for b in range(8) if mask & (1 << b) and (b + 1) in temps]
            if vals:
                return max(vals)
        except (OSError, ValueError):
            pass
        return temps.get(fan_index)

    def set_boost(self, fan_index: int, value: int) -> None:
        if not self.hwmon:
            raise ThermalError("Driver alienware_wmi não encontrado")
        value = max(0, min(255, int(value)))
        _write(os.path.join(self.hwmon, f"fan{fan_index}_boost"), str(value))

    def can_write(self) -> bool:
        if not self.hwmon:
            return False
        paths = [os.path.join(self.hwmon, "fan1_boost"), self._profile_path("profile")]
        return all(os.access(p, os.W_OK) for p in paths)


def interpolate_curve(points: list[list[float]], temp: float) -> int:
    """Curva linear por partes: points = [[temp_c, boost_pct], ...] -> boost 0-255."""
    pts = sorted(points)
    if not pts:
        return 0
    if temp <= pts[0][0]:
        pct = pts[0][1]
    elif temp >= pts[-1][0]:
        pct = pts[-1][1]
    else:
        pct = pts[-1][1]
        for (t0, p0), (t1, p1) in zip(pts, pts[1:]):
            if t0 <= temp <= t1:
                pct = p0 + (p1 - p0) * (temp - t0) / max(t1 - t0, 1e-6)
                break
    return round(max(0.0, min(100.0, pct)) * 255 / 100)
