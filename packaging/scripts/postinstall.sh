#!/bin/sh
# Executado como root depois de instalar/atualizar o pacote (deb, rpm e Arch).
set -u

# Remove a instalação manual antiga (install.sh das versões 0.1.x em /opt)
if [ -d /opt/nova-control ]; then
    rm -rf /opt/nova-control
    rm -f /etc/udev/rules.d/99-nova-control.rules
    [ -L /usr/local/bin/nova-control ] && rm -f /usr/local/bin/nova-control
fi

# Grupo que recebe acesso ao hardware (Fedora/Arch não o criam por padrão)
getent group plugdev >/dev/null 2>&1 || groupadd --system plugdev

# Quem instalou via sudo entra no grupo automaticamente
for u in "${SUDO_USER:-}" "$(id -nu "${PKEXEC_UID:-x}" 2>/dev/null)"; do
    if [ -n "$u" ] && [ "$u" != root ] && id "$u" >/dev/null 2>&1; then
        if ! id -nG "$u" | grep -qw plugdev; then
            usermod -aG plugdev "$u"
            echo "nova-control: usuário $u adicionado ao grupo plugdev (saia e entre na sessão)."
        fi
    fi
done

# Aplica as regras udev aos dispositivos já conectados
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules || true
    for s in hidraw hwmon platform-profile; do
        udevadm trigger --subsystem-match="$s" --action=add || true
    done
fi

# Serviço de usuário ativado para todos os usuários (inicia no próximo login)
if command -v systemctl >/dev/null 2>&1; then
    systemctl --global enable nova-control.service >/dev/null 2>&1 || true
fi

command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
exit 0
