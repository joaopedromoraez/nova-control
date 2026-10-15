"""Interface gráfica GTK4 / libadwaita."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Graphene, Gsk, Gtk, Pango  # noqa: E402

from . import APP_ID, __version__, config  # noqa: E402
from .i18n import _, ngettext  # noqa: E402
from .lighting import ELC, EFFECTS, LightingError, apply_lighting_config, find_device  # noqa: E402
from .thermal import PROFILE_LABELS, Thermal, ThermalError  # noqa: E402

SERVICE = "nova-control.service"
GITHUB_URL = "https://github.com/joaopedromoraez"
REPO_URL = GITHUB_URL + "/nova-control"
ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "icons")
LOGO_ICON = APP_ID + "-logo"
TWO_COLOR_EFFECTS = {"morph"}
NO_COLOR_EFFECTS = {"spectrum", "wave", "off"}
NO_SPEED_EFFECTS = {"static", "off"}

CSS = """
.temp-big { font-size: 26px; font-weight: 800; font-feature-settings: "tnum"; }
.rpm { font-feature-settings: "tnum"; }
.sensor-card { padding: 14px 18px; border-radius: 12px; }
levelbar.fan block.filled { background-color: #00b4ff; }
.splash-logo { animation: nova-pulse 1.8s ease-in-out infinite; }
@keyframes nova-pulse {
  0%, 100% { opacity: 1; -gtk-icon-transform: scale(1); }
  50% { opacity: 0.6; -gtk-icon-transform: scale(0.92); }
}
.splash-title { font-size: 30px; font-weight: 800; }
"""
SPLASH_MIN_SECONDS = 1.2


def rgba_to_tuple(rgba: Gdk.RGBA) -> list[int]:
    return [round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255)]


def tuple_to_rgba(c) -> Gdk.RGBA:
    rgba = Gdk.RGBA()
    rgba.red, rgba.green, rgba.blue, rgba.alpha = c[0] / 255, c[1] / 255, c[2] / 255, 1.0
    return rgba


def probe_elc() -> dict:
    """Consulta o controlador de LEDs. Seguro para rodar fora da thread da interface."""
    dev = find_device()
    if not dev:
        return {"summary": _("Not found")}
    try:
        with ELC(dev) as elc:
            fw = elc.firmware()
            conf = elc.config()
    except (LightingError, OSError) as e:
        return {"summary": str(e)}
    if conf and 1 <= conf[1] <= 64:
        zones = ngettext("{count} zone", "{count} zones", conf[1]).format(count=conf[1])
        return {"zones": conf[1],
                "summary": _("{device} · firmware {firmware} · platform 0x{platform:04x} · {zones}").format(
                    device=dev, firmware=fw or "?", platform=conf[0], zones=zones)}
    return {"summary": _("{device} · firmware {firmware} · no configuration response").format(
        device=dev, firmware=fw or "?")}


def service_active() -> bool:
    try:
        r = subprocess.run(["systemctl", "--user", "is-active", SERVICE],
                           capture_output=True, text=True, timeout=2)
        return r.stdout.strip() == "active"
    except (OSError, subprocess.SubprocessError):
        return False


# ---------------------------------------------------------------------------
# Editor de curva
# ---------------------------------------------------------------------------
class CurveEditor(Gtk.Widget):
    T_MIN, T_MAX = 30, 100
    PAD_L, PAD_R, PAD_T, PAD_B = 40, 14, 12, 26

    def __init__(self, points: list[list[float]], on_changed):
        super().__init__()
        self.points = [list(p) for p in sorted(points)]
        self.on_changed = on_changed
        self.current_temp: float | None = None
        self._drag_idx: int | None = None
        self._drag_start = (0.0, 0.0)
        self.set_size_request(-1, 200)
        self.set_hexpand(True)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._begin)
        drag.connect("drag-update", self._update)
        drag.connect("drag-end", self._end)
        self.add_controller(drag)

    # coordenadas
    def _area(self):
        w, h = self.get_width(), self.get_height()
        return self.PAD_L, self.PAD_T, w - self.PAD_L - self.PAD_R, h - self.PAD_T - self.PAD_B

    def _to_px(self, t, p):
        x0, y0, w, h = self._area()
        return x0 + (t - self.T_MIN) / (self.T_MAX - self.T_MIN) * w, y0 + h - p / 100 * h

    def _from_px(self, x, y):
        x0, y0, w, h = self._area()
        t = self.T_MIN + (x - x0) / max(w, 1) * (self.T_MAX - self.T_MIN)
        p = (y0 + h - y) / max(h, 1) * 100
        return t, p

    # desenho com a API nativa do GTK4 (sem dependência de pycairo)
    @staticmethod
    def _rgba(r, g, b, a=1.0):
        c = Gdk.RGBA()
        c.red, c.green, c.blue, c.alpha = r, g, b, a
        return c

    def _text(self, snap, text, x, y, color):
        layout = self.create_pango_layout(text)
        layout.set_font_description(Pango.FontDescription.from_string("9"))
        snap.save()
        snap.translate(Graphene.Point().init(x, y))
        snap.append_layout(layout, color)
        snap.restore()

    def do_snapshot(self, snap):
        fg = self.get_color()
        accent = self._rgba(0.0, 0.7, 1.0)
        x0, y0, w, h = self._area()
        if w <= 0 or h <= 0:
            return
        # grade
        grid = Gsk.PathBuilder.new()
        for t in range(self.T_MIN, self.T_MAX + 1, 10):
            x, _y = self._to_px(t, 0)
            grid.move_to(x, y0); grid.line_to(x, y0 + h)
        for p in range(0, 101, 25):
            _x, y = self._to_px(self.T_MIN, p)
            grid.move_to(x0, y); grid.line_to(x0 + w, y)
        snap.append_stroke(grid.to_path(), Gsk.Stroke.new(1),
                           self._rgba(fg.red, fg.green, fg.blue, 0.12))
        # rótulos
        label = self._rgba(fg.red, fg.green, fg.blue, 0.6)
        for t in range(self.T_MIN, self.T_MAX + 1, 10):
            x, _y = self._to_px(t, 0)
            self._text(snap, f"{t}°", x - 9, y0 + h + 6, label)
        for p in range(0, 101, 25):
            _x, y = self._to_px(self.T_MIN, p)
            self._text(snap, f"{p}%", 4, y - 7, label)
        # área sob a curva e linha
        pts = [self._to_px(*p) for p in self.points]
        line = Gsk.PathBuilder.new()
        line.move_to(x0, pts[0][1])
        for x, y in pts:
            line.line_to(x, y)
        line.line_to(x0 + w, pts[-1][1])
        area = Gsk.PathBuilder.new()
        area.move_to(x0, y0 + h); area.line_to(x0, pts[0][1])
        for x, y in pts:
            area.line_to(x, y)
        area.line_to(x0 + w, pts[-1][1]); area.line_to(x0 + w, y0 + h); area.close()
        snap.append_fill(area.to_path(), Gsk.FillRule.WINDING, self._rgba(0.0, 0.7, 1.0, 0.15))
        stroke = Gsk.Stroke.new(2.5)
        stroke.set_line_join(Gsk.LineJoin.ROUND)
        snap.append_stroke(line.to_path(), stroke, accent)
        # pontos
        for i, (x, y) in enumerate(pts):
            dot = Gsk.PathBuilder.new()
            dot.add_circle(Graphene.Point().init(x, y), 7 if i == self._drag_idx else 5.5)
            path = dot.to_path()
            snap.append_fill(path, Gsk.FillRule.WINDING, self._rgba(1, 1, 1))
            snap.append_stroke(path, Gsk.Stroke.new(2.5), accent)
        # temperatura atual
        if self.current_temp is not None:
            t = max(self.T_MIN, min(self.T_MAX, self.current_temp))
            x, _y = self._to_px(t, 0)
            now = self._rgba(1.0, 0.35, 0.2, 0.9)
            marker = Gsk.PathBuilder.new()
            marker.move_to(x, y0); marker.line_to(x, y0 + h)
            dashed = Gsk.Stroke.new(1.5)
            dashed.set_dash([4, 3])
            snap.append_stroke(marker.to_path(), dashed, now)
            self._text(snap, f"{self.current_temp:.0f}°C", x + 4, y0, now)

    def _begin(self, _g, x, y):
        best, best_d = None, 15 ** 2
        for i, p in enumerate(self.points):
            px, py = self._to_px(*p)
            d = (px - x) ** 2 + (py - y) ** 2
            if d < best_d:
                best, best_d = i, d
        self._drag_idx = best
        self._drag_start = (x, y)
        self.queue_draw()

    def _update(self, _g, dx, dy):
        i = self._drag_idx
        if i is None:
            return
        t, p = self._from_px(self._drag_start[0] + dx, self._drag_start[1] + dy)
        lo = self.points[i - 1][0] + 1 if i > 0 else self.T_MIN
        hi = self.points[i + 1][0] - 1 if i < len(self.points) - 1 else self.T_MAX
        self.points[i] = [round(max(lo, min(hi, t))), round(max(0, min(100, p)))]
        self.queue_draw()

    def _end(self, *_args):
        if self._drag_idx is not None:
            self._drag_idx = None
            self.queue_draw()
            self.on_changed([list(p) for p in self.points])

    def set_points(self, points):
        self.points = [list(p) for p in sorted(points)]
        self.queue_draw()


# ---------------------------------------------------------------------------
# Janela
# ---------------------------------------------------------------------------
class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Nova Control")
        self.set_default_size(820, 900)
        self.cfg = config.load()
        self.thermal: Thermal | None = None
        self._elc_info: dict = {}
        self._light_lock = threading.Lock()
        self._light_pending = False
        self._light_timer = 0
        self._updating = False

        # tela de carregamento enquanto o hardware é detectado em segundo plano
        self.root = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=450)
        self.root.add_named(self._build_splash(), "splash")
        self.set_content(self.root)
        self._loading_started = time.monotonic()
        threading.Thread(target=self._probe_hardware, daemon=True).start()

    # ---- carregamento -----------------------------------------------------
    def _build_splash(self):
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar(show_title=False, css_classes=["flat"]))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER, margin_bottom=48)
        logo = Gtk.Image(icon_name=LOGO_ICON, pixel_size=128, css_classes=["splash-logo"], margin_bottom=8)
        title = Gtk.Label(label="Nova Control", css_classes=["splash-title"])
        spinner = Adw.Spinner(width_request=28, height_request=28, margin_top=18)
        self.splash_status = Gtk.Label(label=_("Starting…"), css_classes=["dim-label"])
        version = Gtk.Label(label=_("version {version}").format(version=__version__), css_classes=["caption", "dim-label"], margin_top=4)
        for w in (logo, title, spinner, self.splash_status, version):
            box.append(w)
        view.set_content(box)
        return view

    def _probe_hardware(self):
        """Roda fora da thread da interface: tudo que pode demorar (USB, subprocessos)."""
        def step(msg):
            GLib.idle_add(self.splash_status.set_label, msg)

        step(_("Reading thermal sensors…"))
        thermal = Thermal()
        thermal.fans(); thermal.temps(); thermal.profiles()
        step(_("Connecting to the LED controller…"))
        elc_info = probe_elc()
        step(_("Checking the background service…"))
        service_active()
        step(_("Ready"))
        GLib.idle_add(self._finish_loading, thermal, elc_info)

    def _finish_loading(self, thermal, elc_info):
        self.thermal = thermal
        self._elc_info = elc_info
        remaining = SPLASH_MIN_SECONDS - (time.monotonic() - self._loading_started)
        GLib.timeout_add(max(0, int(remaining * 1000)), lambda: self._build_main() and False)
        return False

    def _build_main(self):
        self.toasts = Adw.ToastOverlay()
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)
        header.pack_start(Gtk.Image(icon_name=LOGO_ICON, pixel_size=24, margin_start=4,
                                    tooltip_text="Nova Control"))
        about_btn = Gtk.Button(icon_name="help-about-symbolic", tooltip_text=_("About"))
        about_btn.connect("clicked", self._about)
        header.pack_end(about_btn)
        toolbar.add_top_bar(header)

        self.banner = Adw.Banner(button_label=_("How to fix"))
        self.banner.connect("button-clicked", self._show_install_help)
        toolbar.add_top_bar(self.banner)

        toolbar.set_content(self.stack)
        self.toasts.set_child(toolbar)

        self.stack.add_titled_with_icon(self._build_thermal_page(), "thermal", _("Thermal and fans"),
                                        "power-profile-performance-symbolic")
        self.stack.add_titled_with_icon(self._build_lighting_page(), "lighting", _("Lighting"),
                                        "display-brightness-symbolic")
        self._check_permissions()
        self._refresh()
        self.root.add_named(self.toasts, "main")
        self.root.set_visible_child_name("main")
        GLib.timeout_add(1000, self._refresh)
        GLib.timeout_add_seconds(5, self._refresh_service)
        self._refresh_service()

    # ---- util -----------------------------------------------------------
    def toast(self, msg: str):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(msg), timeout=4))

    def save(self):
        config.save(self.cfg)

    def _check_permissions(self):
        problems = []
        if not self.thermal.available:
            problems.append(_("alienware_wmi driver not loaded"))
        elif not self.thermal.can_write():
            problems.append(_("no permission for fans and profiles"))
        dev = find_device()
        if not dev:
            problems.append(_("LED controller not found"))
        else:
            if not os.access(dev, os.R_OK | os.W_OK):
                problems.append(_("no permission for the LED controller"))
        if problems:
            self.banner.set_title(_("Limited access: {problems}").format(problems="; ".join(problems)))
            self.banner.set_revealed(True)
        else:
            self.banner.set_revealed(False)

    def _show_install_help(self, *_args):
        d = Adw.AlertDialog(
            heading=_("Hardware permissions"),
            body=_("Controlling fans, profiles and LEDs requires access to kernel files that, by default, "
                   "only root can write. Nova Control grants that access to the 'plugdev' group.\n\n"
                   "1. Make sure the nova-control package is installed (or run sudo ./install/install.sh "
                   "from the source code).\n"
                   "2. Add your user to the group, if it isn't already:\n\n"
                   "sudo usermod -aG plugdev $USER\n\n"
                   "3. Log out and back in."),
        )
        d.add_response("ok", _("OK"))
        d.present(self)

    def _about(self, *_args):
        about = Adw.AboutDialog(
            application_name="Nova Control",
            version=__version__,
            comments=_("Fan control, thermal profiles and RGB lighting for Alienware laptops on Linux."),
            developer_name="João Pedro Moraes",
            license_type=Gtk.License.MIT_X11,
            application_icon=LOGO_ICON,
            website=REPO_URL,
            issue_url=REPO_URL + "/issues",
            developers=[f"João Pedro Moraes {GITHUB_URL}"],
            copyright="© 2026 João Pedro Moraes",
        )
        about.add_link(_("GitHub repository"), REPO_URL)
        about.add_link(_("Author on GitHub"), GITHUB_URL)
        about.present(self)

    # ---- página térmica ---------------------------------------------------
    def _build_thermal_page(self):
        page = Adw.PreferencesPage()

        # cartões de sensores
        sensors = Adw.PreferencesGroup(title=_("Monitor"))
        grid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, homogeneous=True)
        self.temp_labels = {}
        self.fan_widgets = {}
        temps = {t.index: t for t in self.thermal.temps()}
        for fan in self.thermal.fans() or []:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            card.add_css_class("card"); card.add_css_class("sensor-card")
            t = temps.get(fan.index)
            title = Gtk.Label(label=(t.label if t else fan.label), xalign=0)
            title.add_css_class("heading")
            temp = Gtk.Label(label="--°C", xalign=0); temp.add_css_class("temp-big")
            rpm = Gtk.Label(label="-- RPM", xalign=0); rpm.add_css_class("rpm"); rpm.add_css_class("dim-label")
            bar = Gtk.LevelBar(min_value=0, max_value=max(fan.rpm_max, 1)); bar.add_css_class("fan")
            for name in ("low", "high", "full"):
                bar.remove_offset_value(name)
            boost = Gtk.Label(label="", xalign=0); boost.add_css_class("caption"); boost.add_css_class("dim-label")
            for w in (title, temp, rpm, bar, boost):
                card.append(w)
            grid.append(card)
            self.fan_widgets[fan.index] = (rpm, bar, boost)
            if t:
                self.temp_labels[t.index] = temp
        if not self.thermal.available:
            grid.append(Gtk.Label(label=_("alienware_wmi driver not found.")))
        sensors.add(grid)
        page.add(sensors)

        # perfil
        prof_group = Adw.PreferencesGroup(
            title=_("Thermal profile"),
            description=_("“Performance” enables G-Mode. GNOME's power mode switch also changes this profile."),
        )
        self.profile_toggle = Adw.ToggleGroup(homogeneous=False)
        self.profile_toggle.add_css_class("round")
        for p in self.thermal.profiles():
            if p == "custom":
                continue
            self.profile_toggle.add(Adw.Toggle(label=PROFILE_LABELS.get(p, p), name=p))
        self.profile_toggle.connect("notify::active-name", self._on_profile)
        prof_box = Gtk.Box(halign=Gtk.Align.CENTER, margin_top=6, margin_bottom=6)
        prof_box.append(self.profile_toggle)
        prof_group.add(prof_box)
        page.add(prof_group)

        # controle das fans
        fan_group = Adw.PreferencesGroup(title=_("Fan control"))
        self.fan_mode_toggle = Adw.ToggleGroup()
        for name, label in (("auto", _("Automatic")), ("manual", _("Fixed boost")), ("curve", _("Custom curve"))):
            self.fan_mode_toggle.add(Adw.Toggle(label=label, name=name))
        self.fan_mode_toggle.set_active_name(self.cfg["thermal"]["fan_mode"])
        self.fan_mode_toggle.connect("notify::active-name", self._on_fan_mode)
        mode_box = Gtk.Box(halign=Gtk.Align.CENTER, margin_top=6, margin_bottom=12)
        mode_box.append(self.fan_mode_toggle)
        fan_group.add(mode_box)

        self.fan_mode_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vhomogeneous=False)

        auto_lbl = Gtk.Label(
            label=_("The firmware controls the fans according to the selected thermal profile."),
            wrap=True, css_classes=["dim-label"], margin_top=6, margin_bottom=6)
        self.fan_mode_stack.add_named(auto_lbl, "auto")

        manual = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        self.boost_scales = {}
        for fan in self.thermal.fans():
            row = Adw.ActionRow(title=fan.label, subtitle=_("Boost above the base speed"))
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
            scale.set_size_request(280, -1); scale.set_valign(Gtk.Align.CENTER)
            scale.set_draw_value(True); scale.set_value_pos(Gtk.PositionType.RIGHT)
            scale.set_format_value_func(lambda _s, v: f"{v:.0f}%")
            scale.set_value(self.cfg["thermal"]["boost"].get(str(fan.index), 0) * 100 / 255)
            scale.connect("value-changed", self._on_boost, fan.index)
            row.add_suffix(scale)
            manual.append(row)
            self.boost_scales[fan.index] = scale
        self.fan_mode_stack.add_named(manual, "manual")

        curve_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.service_row = Adw.ActionRow(
            title=_("Background service"),
            subtitle=_("Required for the curve to work with the app closed"))
        self.service_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.service_switch.connect("state-set", self._on_service_switch)
        self.service_row.add_suffix(self.service_switch)
        svc_list = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        svc_list.append(self.service_row)
        curve_box.append(svc_list)
        self.curve_editors = {}
        for fan in self.thermal.fans():
            frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["card"])
            hdr = Gtk.Box(margin_start=12, margin_end=8, margin_top=8)
            hdr.append(Gtk.Label(label=_("{fan} — drag the points").format(fan=fan.label), xalign=0, hexpand=True,
                                 css_classes=["heading"]))
            reset = Gtk.Button(label=_("Default"), css_classes=["flat"])
            hdr.append(reset)
            frame.append(hdr)
            ed = CurveEditor(self.cfg["thermal"]["curves"].get(str(fan.index), config.DEFAULT_CURVE),
                             lambda pts, i=fan.index: self._on_curve(i, pts))
            ed.set_margin_start(6); ed.set_margin_end(6); ed.set_margin_bottom(6)
            reset.connect("clicked", lambda _b, e=ed, i=fan.index: (e.set_points(config.DEFAULT_CURVE),
                                                                     self._on_curve(i, config.DEFAULT_CURVE)))
            frame.append(ed)
            curve_box.append(frame)
            self.curve_editors[fan.index] = ed
        self.fan_mode_stack.add_named(curve_box, "curve")
        self.fan_mode_stack.set_visible_child_name(self.cfg["thermal"]["fan_mode"])
        fan_group.add(self.fan_mode_stack)
        page.add(fan_group)
        return page

    def _on_profile(self, toggle, _p):
        if self._updating:
            return
        name = toggle.get_active_name()
        if not name:
            return
        self.cfg["thermal"]["profile"] = name
        self.save()
        if self.cfg["thermal"]["fan_mode"] == "manual":
            # escolher um perfil de firmware devolve o controle das fans ao firmware
            self.fan_mode_toggle.set_active_name("auto")
            return
        try:
            self.thermal.set_profile(name)
        except ThermalError as e:
            self.toast(str(e))

    def _on_fan_mode(self, toggle, _p):
        mode = toggle.get_active_name()
        if not mode:
            return
        self.fan_mode_stack.set_visible_child_name(mode)
        self.cfg["thermal"]["fan_mode"] = mode
        self.save()
        try:
            if mode == "auto":
                for f in self.thermal.fans():
                    self.thermal.set_boost(f.index, 0)
                self.thermal.set_profile(self.cfg["thermal"]["profile"])
            elif mode == "manual":
                # controle manual é mais confiável no perfil "custom"
                self.thermal.set_profile("custom")
                for i, s in self.boost_scales.items():
                    self.thermal.set_boost(i, round(s.get_value() * 255 / 100))
            elif mode == "curve":
                if not service_active():
                    self.toast(_("Turn on the background service for the curve to work"))
        except ThermalError as e:
            self.toast(str(e))

    def _on_boost(self, scale, fan_index):
        val = round(scale.get_value() * 255 / 100)
        self.cfg["thermal"]["boost"][str(fan_index)] = val
        self.save()
        if self.cfg["thermal"]["fan_mode"] == "manual":
            try:
                self.thermal.set_boost(fan_index, val)
            except ThermalError as e:
                self.toast(str(e))

    def _on_curve(self, fan_index, pts):
        self.cfg["thermal"]["curves"][str(fan_index)] = pts
        self.save()

    def _on_service_switch(self, _sw, state):
        cmd = ["systemctl", "--user", "enable" if state else "disable", "--now", SERVICE]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            self.toast(_("Failed: {error}").format(error=r.stderr.strip() or _("service not installed")))
            GLib.idle_add(self._refresh_service)
            return True
        return False

    def _refresh_service(self):
        active = service_active()
        self.service_switch.handler_block_by_func(self._on_service_switch)
        self.service_switch.set_active(active)
        self.service_switch.handler_unblock_by_func(self._on_service_switch)
        self.service_row.set_subtitle(_("Active — applying settings and curve") if active
                                      else _("Inactive — the curve will not be applied"))
        return True

    def _refresh(self):
        if not self.thermal.available:
            return True
        temps = {t.index: t.celsius for t in self.thermal.temps()}
        for idx, lbl in self.temp_labels.items():
            if idx in temps:
                lbl.set_label(f"{temps[idx]:.0f}°C")
        for fan in self.thermal.fans():
            w = self.fan_widgets.get(fan.index)
            if not w:
                continue
            rpm, bar, boost = w
            rpm.set_label(_("{rpm} RPM  ·  max {max}").format(rpm=fan.rpm, max=fan.rpm_max))
            bar.set_value(min(fan.rpm, bar.get_max_value()))
            boost.set_label(_("Boost: {percent}%").format(percent=fan.boost * 100 // 255))
            ed = self.curve_editors.get(fan.index)
            if ed:
                ed.current_temp = self.thermal.temp_for_fan(fan.index)
                ed.queue_draw()
        prof = self.thermal.profile()
        if prof and prof != "custom" and prof != self.profile_toggle.get_active_name():
            self._updating = True
            self.profile_toggle.set_active_name(prof)
            self._updating = False
        return True

    # ---- página de iluminação ---------------------------------------------
    def _build_lighting_page(self):
        page = Adw.PreferencesPage()
        lc = self.cfg["lighting"]

        info = Adw.PreferencesGroup(title=_("Controller"))
        self.dev_row = Adw.ActionRow(title="AW-ELC", subtitle=_("Searching…"))
        detect = Gtk.Button(label=_("Detect zones"), valign=Gtk.Align.CENTER)
        detect.connect("clicked", lambda *_args: self._detect_zones(force=True))
        self.dev_row.add_suffix(detect)
        info.add(self.dev_row)
        page.add(info)

        general = Adw.PreferencesGroup(title=_("General"))
        en = Adw.SwitchRow(title=_("Apply lighting at login"), active=lc.get("enabled", True))
        en.connect("notify::active", lambda r, _p: (lc.__setitem__("enabled", r.get_active()), self.save()))
        general.add(en)

        bright = Adw.ActionRow(title=_("Brightness"))
        bscale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        bscale.set_size_request(280, -1); bscale.set_valign(Gtk.Align.CENTER)
        bscale.set_draw_value(True); bscale.set_value_pos(Gtk.PositionType.RIGHT)
        bscale.set_format_value_func(lambda _s, v: f"{v:.0f}%")
        bscale.set_value(lc.get("brightness", 100))
        bscale.connect("value-changed", lambda s: (lc.__setitem__("brightness", int(s.get_value())),
                                                   self._schedule_light()))
        bright.add_suffix(bscale)
        general.add(bright)

        self.sync_row = Adw.SwitchRow(title=_("Same effect on all zones"),
                                      subtitle=_("Changes to the first zone are copied to the others"),
                                      active=lc.get("sync", True))
        self.sync_row.connect("notify::active", self._on_sync)
        general.add(self.sync_row)

        presets = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER, margin_top=12)
        for name, color in ((_("Alien"), (0, 180, 255)), (_("Red"), (255, 0, 0)), (_("Green"), (0, 255, 60)),
                            (_("Purple"), (150, 0, 255)), (_("White"), (255, 255, 255))):
            b = Gtk.Button(label=name, css_classes=["pill"])
            b.connect("clicked", lambda _b, c=color: self._preset(c))
            presets.append(b)
        rb = Gtk.Button(label=_("Rainbow"), css_classes=["pill"])
        rb.connect("clicked", lambda _b: self._preset(None, "wave"))
        presets.append(rb)
        general.add(presets)
        page.add(general)

        self.zones_group = Adw.PreferencesGroup(
            title=_("Zones"), description=_("Use “Identify” to find out which zone is which, then rename it."))
        page.add(self.zones_group)
        self.zone_rows = []
        self._apply_elc_info(self._elc_info, force=False)
        return page

    def _detect_zones(self, force: bool):
        self._apply_elc_info(probe_elc(), force)

    def _apply_elc_info(self, info: dict, force: bool):
        lc = self.cfg["lighting"]
        self.dev_row.set_subtitle(info.get("summary", ""))
        zones = info.get("zones")
        if zones and (force or "detected" not in lc):
            lc["zone_count"] = zones
            lc["detected"] = True
            self.save()
        self._build_zone_rows()

    def _build_zone_rows(self):
        for r in self.zone_rows:
            self.zones_group.remove(r)
        self.zone_rows = []
        self.zone_ctrls = {}
        for z in range(self.cfg["lighting"]["zone_count"]):
            zc = config.zone_cfg(self.cfg, z)
            row = Adw.ExpanderRow(title=GLib.markup_escape_text(config.zone_name(self.cfg, z)),
                                  subtitle=EFFECTS.get(zc["effect"], ""))
            swatch = Gtk.Box(css_classes=["card"], valign=Gtk.Align.CENTER)
            swatch.set_size_request(22, 22)
            row.add_prefix(swatch)

            name = Adw.EntryRow(title=_("Name"), text=config.zone_name(self.cfg, z))
            name.connect("changed", self._on_zone_name, z, row)
            row.add_row(name)

            effects = list(EFFECTS)
            eff = Adw.ComboRow(title=_("Effect"), model=Gtk.StringList.new([EFFECTS[e] for e in effects]))
            eff.set_selected(effects.index(zc["effect"]) if zc["effect"] in effects else 0)
            row.add_row(eff)

            colors_row = Adw.ActionRow(title=_("Colors"))
            c1 = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER,
                                       rgba=tuple_to_rgba(zc["colors"][0]))
            c2 = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER,
                                       rgba=tuple_to_rgba(zc["colors"][1] if len(zc["colors"]) > 1 else [0, 0, 0]))
            colors_row.add_suffix(c1); colors_row.add_suffix(c2)
            row.add_row(colors_row)

            speed_row = Adw.ActionRow(title=_("Speed"))
            speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
            speed.set_size_request(240, -1); speed.set_valign(Gtk.Align.CENTER)
            speed.set_value(zc["speed"])
            speed_row.add_suffix(speed)
            row.add_row(speed_row)

            ident_row = Adw.ActionRow(title=_("Identify zone"), subtitle=_("Flashes only this zone in white for 3 s"))
            ident = Gtk.Button(label=_("Identify"), valign=Gtk.Align.CENTER)
            ident.connect("clicked", self._identify, z)
            ident_row.add_suffix(ident)
            row.add_row(ident_row)

            ctrl = dict(row=row, swatch=swatch, eff=eff, c1=c1, c2=c2, speed=speed,
                        colors_row=colors_row, speed_row=speed_row, effects=effects)
            self.zone_ctrls[z] = ctrl
            eff.connect("notify::selected", lambda *_a, z=z: self._on_zone_change(z))
            c1.connect("notify::rgba", lambda *_a, z=z: self._on_zone_change(z))
            c2.connect("notify::rgba", lambda *_a, z=z: self._on_zone_change(z))
            speed.connect("value-changed", lambda *_a, z=z: self._on_zone_change(z))
            self._update_zone_visuals(z)

            self.zones_group.add(row)
            self.zone_rows.append(row)

    def _update_zone_visuals(self, z):
        c = self.zone_ctrls[z]
        zc = config.zone_cfg(self.cfg, z)
        effect = zc["effect"]
        c["row"].set_subtitle(EFFECTS.get(effect, ""))
        c["colors_row"].set_visible(effect not in NO_COLOR_EFFECTS)
        c["c2"].set_visible(effect in TWO_COLOR_EFFECTS)
        c["speed_row"].set_visible(effect not in NO_SPEED_EFFECTS)
        r, g, b = zc["colors"][0] if effect not in NO_COLOR_EFFECTS else (60, 60, 60)
        if effect == "off":
            r, g, b = 0, 0, 0
        prov = Gtk.CssProvider()
        bg = ("linear-gradient(90deg,#f00,#ff0,#0f0,#0ff,#00f,#f0f)" if effect in ("spectrum", "wave")
              else f"rgb({r},{g},{b})")
        prov.load_from_string(f"box {{ background: {bg}; }}")
        c["swatch"].get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def _read_zone_ctrls(self, z) -> dict:
        c = self.zone_ctrls[z]
        return {
            "effect": c["effects"][c["eff"].get_selected()],
            "colors": [rgba_to_tuple(c["c1"].get_rgba()), rgba_to_tuple(c["c2"].get_rgba())],
            "speed": int(c["speed"].get_value()),
        }

    def _on_zone_change(self, z):
        if self._updating:
            return
        vals = self._read_zone_ctrls(z)
        targets = list(self.zone_ctrls) if self.cfg["lighting"].get("sync", True) and z == 0 else [z]
        for t in targets:
            config.zone_cfg(self.cfg, t).update(vals)
        if len(targets) > 1:
            self._updating = True
            for t in targets[1:]:
                c = self.zone_ctrls[t]
                c["eff"].set_selected(c["effects"].index(vals["effect"]))
                c["c1"].set_rgba(tuple_to_rgba(vals["colors"][0]))
                c["c2"].set_rgba(tuple_to_rgba(vals["colors"][1]))
                c["speed"].set_value(vals["speed"])
            self._updating = False
        for t in targets:
            self._update_zone_visuals(t)
        self._schedule_light()

    def _on_zone_name(self, entry, z, row):
        config.zone_cfg(self.cfg, z)["name"] = entry.get_text().strip()
        row.set_title(GLib.markup_escape_text(config.zone_name(self.cfg, z)))
        self.save()

    def _on_sync(self, row, _p):
        self.cfg["lighting"]["sync"] = row.get_active()
        self.save()
        if row.get_active() and 0 in self.zone_ctrls:
            self._on_zone_change(0)

    def _preset(self, color, effect="static"):
        self._updating = True
        for z, c in self.zone_ctrls.items():
            zc = config.zone_cfg(self.cfg, z)
            zc["effect"] = effect
            if color:
                zc["colors"][0] = list(color)
                c["c1"].set_rgba(tuple_to_rgba(color))
            c["eff"].set_selected(c["effects"].index(effect))
            self._update_zone_visuals(z)
        self._updating = False
        self._schedule_light()

    def _identify(self, _btn, z):
        def work():
            try:
                with self._light_lock, ELC() as elc:
                    elc.identify(z, list(range(self.cfg["lighting"]["zone_count"])))
            except (LightingError, OSError) as e:
                GLib.idle_add(self.toast, str(e))
            GLib.timeout_add(3000, lambda: (self._schedule_light(0), False)[1])
        threading.Thread(target=work, daemon=True).start()

    # aplicação com debounce em thread (o protocolo USB é lento)
    def _schedule_light(self, delay=250):
        self.save()
        if self._light_timer:
            GLib.source_remove(self._light_timer)
        self._light_timer = GLib.timeout_add(delay, self._kick_light)

    def _kick_light(self):
        self._light_timer = 0
        if self._light_lock.locked():
            self._light_pending = True
            return False
        cfg = {k: v for k, v in self.cfg["lighting"].items()}
        cfg["zones"] = {str(z): dict(config.zone_cfg(self.cfg, z)) for z in range(cfg["zone_count"])}

        def work():
            with self._light_lock:
                try:
                    apply_lighting_config(cfg)
                except (LightingError, OSError) as e:
                    GLib.idle_add(self.toast, str(e))
            if self._light_pending:
                self._light_pending = False
                GLib.idle_add(self._kick_light)
        threading.Thread(target=work, daemon=True).start()
        return False


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.connect("activate", self._activate)

    def _activate(self, app):
        prov = Gtk.CssProvider()
        prov.load_from_string(CSS)
        # ícones do projeto (funciona também sem instalar no tema do sistema)
        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(ICONS_DIR)
        Gtk.Window.set_default_icon_name(APP_ID)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
        win = self.props.active_window or Window(app)
        win.present()


def main():
    return App().run(sys.argv[:1])


if __name__ == "__main__":
    sys.exit(main())
