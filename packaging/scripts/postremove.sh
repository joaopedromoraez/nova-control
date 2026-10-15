#!/bin/sh
# Executado depois de remover o pacote: recarrega udev e caches.

# Cache do Python criado ao rodar o app como root não pertence ao pacote
rm -rf /usr/share/nova-control/nova_control/__pycache__
rmdir /usr/share/nova-control/nova_control /usr/share/nova-control 2>/dev/null || true
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules || true
fi
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
exit 0
