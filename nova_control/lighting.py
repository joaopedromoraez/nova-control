"""Driver userspace do controlador de iluminação Alienware AW-ELC (USB 187c:0550/0551).

Protocolo "ELC" (API v4), mesmo usado por OpenRGB e alienfx-tools:
  relatório de saída HID de 33 bytes, sem report ID; byte 0 = 0x03, byte 1 = comando.

  0x20 REPORT       sub: 0x00 firmware, 0x01 status, 0x02 config (platform id + nº de zonas)
  0x21 USER_ANIM    sub(16b) anim(16b) duration(16b)   NEW=1 FINISH_SAVE=2 FINISH_PLAY=3 ...
  0x23 SELECT_ZONES loop(1) count(16b) zone_ids...
  0x24 ADD_ACTION   até 3x [mode, duration(16b), tempo(16b), r, g, b]
  0x26 DIM          percent(0=brilho máximo, 100=apagado) count(16b) zone_ids...
  0x27 SET_COLOR    r g b count(16b) zone_ids...
"""

from __future__ import annotations

import fcntl
import glob
import os
import time
from dataclasses import dataclass

from .i18n import _

VENDOR = 0x187C
PRODUCTS = (0x0550, 0x0551)
REPORT_SIZE = 33
MAX_ZONES_PER_PACKET = 25

CMD_REPORT = 0x20
CMD_USER_ANIM = 0x21
CMD_SELECT_ZONES = 0x23
CMD_ADD_ACTION = 0x24
CMD_DIM = 0x26
CMD_SET_COLOR = 0x27
CMD_RESET = 0x28

REPORT_FIRMWARE = 0x00
REPORT_CONFIG = 0x02

ANIM_NEW = 0x0001
ANIM_FINISH_SAVE = 0x0002
ANIM_FINISH_PLAY = 0x0003
ANIM_KEYBOARD = 0xFFFF  # animação "volátil", aplicada imediatamente

ACT_COLOR = 0x00
ACT_PULSE = 0x01
ACT_MORPH = 0x02

TEMPO_MAX = 250

EFFECTS = {
    "static": _("Static"),
    "breathing": _("Breathing"),
    "pulse": _("Pulse"),
    "morph": _("Morph (2 colors)"),
    "spectrum": _("Spectrum"),
    "wave": _("Rainbow wave"),
    "off": _("Off"),
}

SPECTRUM = [
    (255, 0, 0), (255, 165, 0), (255, 255, 0), (0, 255, 0),
    (0, 255, 255), (0, 0, 255), (255, 0, 255),
]


def _hidioc(nr: int, size: int) -> int:
    """_IOC(_IOC_READ|_IOC_WRITE, 'H', nr, size) — ioctls de feature report do hidraw."""
    return (3 << 30) | (size << 16) | (ord("H") << 8) | nr


class LightingError(Exception):
    pass


Color = tuple[int, int, int]


@dataclass
class Action:
    mode: int
    duration: int
    tempo: int
    color: Color

    def pack(self) -> bytes:
        r, g, b = self.color
        return bytes([
            self.mode,
            (self.duration >> 8) & 0xFF, self.duration & 0xFF,
            (self.tempo >> 8) & 0xFF, self.tempo & 0xFF,
            r & 0xFF, g & 0xFF, b & 0xFF,
        ])


def find_device() -> str | None:
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(node, "device", "uevent")) as f:
                ue = f.read()
        except OSError:
            continue
        for line in ue.splitlines():
            if line.startswith("HID_ID="):
                _bus, vid, pid = line.split("=", 1)[1].split(":")
                if int(vid, 16) == VENDOR and int(pid, 16) in PRODUCTS:
                    return "/dev/" + os.path.basename(node)
    return None


def speed_to_timing(speed: int) -> tuple[int, int]:
    """speed 1..100 -> (duração do passo em ms, tempo)."""
    speed = max(1, min(100, speed))
    duration = int(3000 - (speed - 1) * (2700 / 99))  # 3000ms .. 300ms
    tempo = int(100 + (speed - 1) * (150 / 99))       # 100 .. 250
    return duration, tempo


def build_actions(effect: str, colors: list[Color], speed: int, phase: int = 0) -> list[Action]:
    """Converte efeito de alto nível em lista de ações de hardware para uma zona."""
    c1 = tuple(colors[0]) if colors else (255, 255, 255)
    c2 = tuple(colors[1]) if len(colors) > 1 else (0, 0, 0)
    dur, tempo = speed_to_timing(speed)
    if effect == "off":
        return [Action(ACT_COLOR, 2000, TEMPO_MAX, (0, 0, 0))]
    if effect == "static":
        return [Action(ACT_COLOR, 2000, TEMPO_MAX, c1)]
    if effect == "pulse":
        return [Action(ACT_PULSE, dur, tempo, c1)]
    if effect == "breathing":
        return [Action(ACT_MORPH, dur, tempo, c1), Action(ACT_MORPH, dur, tempo, (0, 0, 0))]
    if effect == "morph":
        return [Action(ACT_MORPH, dur, tempo, c1), Action(ACT_MORPH, dur, tempo, c2)]
    if effect in ("spectrum", "wave"):
        step = max(150, dur // 3)
        seq = SPECTRUM[phase % len(SPECTRUM):] + SPECTRUM[: phase % len(SPECTRUM)]
        return [Action(ACT_MORPH, step, tempo, c) for c in seq]
    raise LightingError(_("Unknown effect: {effect}").format(effect=effect))


class ELC:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or find_device()
        if not self.path:
            raise LightingError(_("AW-ELC lighting controller (187c:0550) not found"))
        try:
            self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError as e:
            raise LightingError(
                _("No permission to access {path}. Install the nova-control package or add your user to the plugdev group.").format(path=self.path)
            ) from e
        # um processo por vez (GUI, serviço e CLI compartilham o controlador;
        # comandos intercalados misturam as respostas)
        deadline = time.monotonic() + 10
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    os.close(self.fd)
                    raise LightingError(_("The LED controller is busy in another process"))
                time.sleep(0.05)

    def close(self) -> None:
        if getattr(self, "fd", None) is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- transporte -----------------------------------------------------
    # O firmware não responde pelo endpoint de interrupção: comandos e respostas
    # trafegam como "feature reports" (HIDIOCSFEATURE / HIDIOCGFEATURE).
    def send(self, cmd: int, payload: bytes = b"", delay: float = 0.06) -> bytes | None:
        body = bytes([0x03, cmd]) + payload
        if len(body) > REPORT_SIZE:
            raise LightingError("Packet larger than 33 bytes")
        buf = bytearray(b"\x00" + body.ljust(REPORT_SIZE, b"\x00"))  # 0x00 = sem report ID
        try:
            fcntl.ioctl(self.fd, _hidioc(0x06, len(buf)), buf)
            time.sleep(delay)
            resp = bytearray(len(buf))
            fcntl.ioctl(self.fd, _hidioc(0x07, len(resp)), resp)
        except OSError as e:
            raise LightingError(_("Communication with the LED controller failed: {error}").format(error=e)) from e
        return bytes(resp[1:])  # remove o byte de report ID

    # ---- consultas ------------------------------------------------------
    def firmware(self) -> str | None:
        resp = self.send(CMD_REPORT, bytes([REPORT_FIRMWARE]))
        if resp and resp[:3] == bytes([0x03, CMD_REPORT, REPORT_FIRMWARE]):
            return f"{resp[3]}.{resp[4]}.{resp[5]}"
        return None

    def config(self) -> tuple[int, int] | None:
        """Retorna (platform_id, número de zonas)."""
        resp = self.send(CMD_REPORT, bytes([REPORT_CONFIG]))
        if resp and resp[:3] == bytes([0x03, CMD_REPORT, REPORT_CONFIG]):
            return (resp[3] << 8) | resp[4], resp[5]
        return None

    # ---- primitivas -----------------------------------------------------
    @staticmethod
    def _chunks(zones: list[int]):
        for i in range(0, len(zones), MAX_ZONES_PER_PACKET):
            yield zones[i : i + MAX_ZONES_PER_PACKET]

    def user_anim(self, sub: int, anim: int = ANIM_KEYBOARD, duration: int = 0) -> None:
        self.send(CMD_USER_ANIM, bytes([
            sub >> 8, sub & 0xFF, anim >> 8, anim & 0xFF, duration >> 8, duration & 0xFF,
        ]), delay=1.0 if sub in (ANIM_FINISH_PLAY, ANIM_FINISH_SAVE) else 0.06)

    def select_zones(self, zones: list[int]) -> None:
        n = len(zones)
        self.send(CMD_SELECT_ZONES, bytes([1, n >> 8, n & 0xFF, *zones]))

    def add_actions(self, actions: list[Action]) -> None:
        for i in range(0, len(actions), 3):
            self.send(CMD_ADD_ACTION, b"".join(a.pack() for a in actions[i : i + 3]))

    def set_color_direct(self, zones: list[int], color: Color) -> None:
        r, g, b = color
        for chunk in self._chunks(zones):
            n = len(chunk)
            self.send(CMD_SET_COLOR, bytes([r, g, b, n >> 8, n & 0xFF, *chunk]))

    def dim(self, zones: list[int], brightness: int) -> None:
        """brightness 0..100 (100 = máximo)."""
        pct = 100 - max(0, min(100, int(brightness)))
        for chunk in self._chunks(zones):
            n = len(chunk)
            self.send(CMD_DIM, bytes([pct, n >> 8, n & 0xFF, *chunk]))

    # ---- alto nível -----------------------------------------------------
    def apply(self, zone_actions: dict[int, list[Action]], brightness: int | None = None) -> None:
        """Programa uma animação nova com ações por zona e a executa."""
        self.user_anim(ANIM_NEW)
        # agrupa zonas com ações idênticas num só SELECT para economizar pacotes
        groups: dict[bytes, list[int]] = {}
        for z, acts in zone_actions.items():
            key = b"".join(a.pack() for a in acts)
            groups.setdefault(key, []).append(z)
        for key, zones in groups.items():
            acts = zone_actions[zones[0]]
            for chunk in self._chunks(sorted(zones)):
                self.select_zones(chunk)
                self.add_actions(acts)
        self.user_anim(ANIM_FINISH_PLAY)
        if brightness is not None:
            self.dim(sorted(zone_actions), brightness)

    def identify(self, zone: int, all_zones: list[int]) -> None:
        """Acende só uma zona em branco (para descobrir qual LED é qual)."""
        acts = {z: [Action(ACT_COLOR, 2000, TEMPO_MAX, (0, 0, 0))] for z in all_zones}
        acts[zone] = [Action(ACT_PULSE, 600, TEMPO_MAX, (255, 255, 255))]
        self.apply(acts, brightness=100)


def apply_lighting_config(cfg: dict, elc: ELC | None = None) -> None:
    """Aplica a seção `lighting` da configuração."""
    own = elc is None
    elc = elc or ELC()
    try:
        zones_cfg: dict = cfg.get("zones", {})
        zone_ids = [int(z) for z in zones_cfg] or list(range(cfg.get("zone_count", 4)))
        actions = {}
        for idx, z in enumerate(sorted(zone_ids)):
            zc = zones_cfg.get(str(z), {})
            effect = zc.get("effect", cfg.get("effect", "static"))
            colors = [tuple(c) for c in zc.get("colors", cfg.get("colors", [[0, 128, 255]]))]
            speed = zc.get("speed", cfg.get("speed", 50))
            phase = idx if effect == "wave" else 0
            actions[z] = build_actions(effect, colors, speed, phase)
        elc.apply(actions, brightness=cfg.get("brightness", 100))
    finally:
        if own:
            elc.close()
