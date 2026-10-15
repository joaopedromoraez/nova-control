#!/bin/sh
# Executado antes de remover o pacote. Em atualizações não faz nada.
# deb: $1 = remove|upgrade ; rpm: $1 = 0 (remoção) ou 1 (atualização) ; Arch: sem argumento
case "${1:-remove}" in
    upgrade|1) exit 0 ;;
esac
if command -v systemctl >/dev/null 2>&1; then
    systemctl --global disable nova-control.service >/dev/null 2>&1 || true
fi
exit 0
