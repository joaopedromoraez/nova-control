#!/bin/sh
# Instala o Nova Control a partir do código-fonte (em /usr/local).
# Prefira os pacotes .deb/.rpm/Arch da página de Releases quando houver um para sua distro.
#
#   sudo ./install/install.sh               instala
#   sudo ./install/install.sh --uninstall   remove
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Rode com sudo: sudo $0 $*" >&2
    exit 1
fi

SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP_ID=io.github.nova_control
export PREFIX=/usr/local

owned_by_package() {
    { command -v dpkg >/dev/null 2>&1 && dpkg -S "$1" >/dev/null 2>&1; } ||
    { command -v rpm >/dev/null 2>&1 && rpm -qf "$1" >/dev/null 2>&1; } ||
    { command -v pacman >/dev/null 2>&1 && pacman -Qo "$1" >/dev/null 2>&1; }
}

if [ "${1:-}" = "--uninstall" ]; then
    echo "==> Removendo Nova Control de $PREFIX"
    systemctl --global disable nova-control.service >/dev/null 2>&1 || true
    "$SRC/packaging/install-files.sh" --uninstall
    sh "$SRC/packaging/scripts/postremove.sh"
    echo "Removido."
    exit 0
fi

# Arquivos que a versão 0.1 copiava direto para /usr/share e /usr/lib (sem pacote)
for f in /usr/share/applications/$APP_ID.desktop \
         /usr/share/applications/nova-control.desktop \
         /usr/share/icons/hicolor/scalable/apps/$APP_ID.svg \
         /usr/share/icons/hicolor/scalable/apps/$APP_ID-logo.svg \
         /usr/share/icons/hicolor/symbolic/apps/$APP_ID-symbolic.svg \
         /usr/lib/systemd/user/nova-control.service; do
    if [ -e "$f" ] && ! owned_by_package "$f"; then
        rm -f "$f"
    fi
done

echo "==> Instalando arquivos em $PREFIX"
"$SRC/packaging/install-files.sh"

echo "==> Configurando permissões, serviço e ícones"
sh "$SRC/packaging/scripts/postinstall.sh"

# Inicia o serviço agora para quem instalou (o postinstall só o ativa para os próximos logins)
if [ -n "${SUDO_USER:-}" ]; then
    UID_T="$(id -u "$SUDO_USER")"
    if [ -S "/run/user/$UID_T/bus" ]; then
        sudo -u "$SUDO_USER" XDG_RUNTIME_DIR="/run/user/$UID_T" systemctl --user daemon-reload || true
        sudo -u "$SUDO_USER" XDG_RUNTIME_DIR="/run/user/$UID_T" systemctl --user restart nova-control.service || true
    fi
fi

echo
echo "Pronto! Abra 'Nova Control' no menu de aplicativos ou rode: nova-control"
