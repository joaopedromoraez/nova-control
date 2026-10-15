#!/bin/sh
# Executado depois de remover o pacote: recarrega udev e caches.
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules || true
fi
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
exit 0
