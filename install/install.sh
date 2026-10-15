#!/bin/sh
# Instala o Nova Control. Rode com: sudo ./install/install.sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Rode com sudo: sudo $0" >&2
    exit 1
fi

SRC="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX=/opt/nova-control
TARGET_USER="${SUDO_USER:-}"

if [ -n "$TARGET_USER" ]; then
    UID_T="$(id -u "$TARGET_USER")"
    run_user() { sudo -u "$TARGET_USER" XDG_RUNTIME_DIR="/run/user/$UID_T" "$@"; }
fi

# Remove a instalação antiga ("Alienware Control"), se existir
if [ -e /opt/alienware-control ] || [ -e /usr/lib/systemd/user/alienware-control.service ]; then
    echo "==> Removendo instalação antiga (alienware-control)"
    if [ -n "$TARGET_USER" ] && [ -S "/run/user/$UID_T/bus" ]; then
        run_user systemctl --user disable --now alienware-control.service 2>/dev/null || true
    fi
    rm -rf /opt/alienware-control
    rm -f /usr/local/bin/alienware-control \
          /etc/udev/rules.d/99-alienware-control.rules \
          /usr/share/applications/alienware-control.desktop \
          /usr/lib/systemd/user/alienware-control.service
fi

echo "==> Copiando aplicativo para $PREFIX"
rm -rf "$PREFIX"
mkdir -p "$PREFIX"
cp -r "$SRC/nova_control" "$SRC/bin" "$SRC/data" "$PREFIX/"
find "$PREFIX" -name __pycache__ -prune -exec rm -rf {} +
chmod 755 "$PREFIX/bin/nova-control"
ln -sf "$PREFIX/bin/nova-control" /usr/local/bin/nova-control

echo "==> Instalando regras udev"
install -m 644 "$SRC/install/99-nova-control.rules" /etc/udev/rules.d/99-nova-control.rules
udevadm control --reload-rules
udevadm trigger --subsystem-match=hidraw --action=add
udevadm trigger --subsystem-match=hwmon --action=add
udevadm trigger --subsystem-match=platform-profile --action=add
udevadm settle

echo "==> Ícones, atalho no menu e serviço de usuário"
ICONS=/usr/share/icons/hicolor
install -Dm 644 "$SRC/data/icons/io.github.nova_control.svg" "$ICONS/scalable/apps/io.github.nova_control.svg"
install -Dm 644 "$SRC/data/icons/io.github.nova_control-logo.svg" "$ICONS/scalable/apps/io.github.nova_control-logo.svg"
install -Dm 644 "$SRC/data/icons/io.github.nova_control-symbolic.svg" "$ICONS/symbolic/apps/io.github.nova_control-symbolic.svg"
gtk-update-icon-cache -q -t -f "$ICONS" 2>/dev/null || true
rm -f /usr/share/applications/nova-control.desktop
install -m 644 "$SRC/install/io.github.nova_control.desktop" /usr/share/applications/io.github.nova_control.desktop
update-desktop-database -q /usr/share/applications 2>/dev/null || true
install -m 644 "$SRC/install/nova-control.service" /usr/lib/systemd/user/nova-control.service

if [ -n "$TARGET_USER" ]; then
    if ! id -nG "$TARGET_USER" | grep -qw plugdev; then
        usermod -aG plugdev "$TARGET_USER"
        echo "   Usuário $TARGET_USER adicionado ao grupo plugdev (faça logout/login)."
    fi
    if [ -S "/run/user/$UID_T/bus" ]; then
        run_user systemctl --user daemon-reload || true
        run_user systemctl --user enable nova-control.service || true
        run_user systemctl --user restart nova-control.service || true
    fi
fi

echo
echo "Pronto! Abra 'Nova Control' no menu de aplicativos ou rode: nova-control"
