#!/bin/sh
# Layout de instalação do Nova Control — fonte única usada pelos pacotes e por install/install.sh.
#
#   packaging/install-files.sh                       -> instala em /usr/local
#   PREFIX=/usr DESTDIR=build/root packaging/install-files.sh   -> árvore para empacotamento
#   packaging/install-files.sh --uninstall           -> remove (mesmos PREFIX/DESTDIR)
set -eu

SRC="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX="${PREFIX:-/usr/local}"
DESTDIR="${DESTDIR:-}"
APP_ID=io.github.nova_control

BINDIR="$DESTDIR$PREFIX/bin"
DATADIR="$DESTDIR$PREFIX/share"
LIBDIR="$DATADIR/nova-control"
# udev e systemd sempre em /usr/lib: é onde as distros procuram arquivos de pacote
UDEVDIR="$DESTDIR/usr/lib/udev/rules.d"
USERUNITDIR="$DESTDIR/usr/lib/systemd/user"

FILES="
$BINDIR/nova-control
$UDEVDIR/99-nova-control.rules
$USERUNITDIR/nova-control.service
$DATADIR/applications/$APP_ID.desktop
$DATADIR/metainfo/$APP_ID.metainfo.xml
$DATADIR/icons/hicolor/scalable/apps/$APP_ID.svg
$DATADIR/icons/hicolor/scalable/apps/$APP_ID-logo.svg
$DATADIR/icons/hicolor/symbolic/apps/$APP_ID-symbolic.svg
"

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$LIBDIR" "$DATADIR/licenses/nova-control"
    for f in $FILES; do rm -f "$f"; done
    exit 0
fi

install -d "$LIBDIR/nova_control"
install -m 644 "$SRC"/nova_control/*.py "$LIBDIR/nova_control/"
install -d "$LIBDIR/po"
install -m 644 "$SRC"/po/*.po "$LIBDIR/po/"
install -Dm 755 "$SRC/bin/nova-control" "$BINDIR/nova-control"
install -Dm 644 "$SRC/data/99-nova-control.rules" "$UDEVDIR/99-nova-control.rules"
install -Dm 644 "$SRC/data/nova-control.service" "$USERUNITDIR/nova-control.service"
install -Dm 644 "$SRC/data/$APP_ID.desktop" "$DATADIR/applications/$APP_ID.desktop"
install -Dm 644 "$SRC/data/$APP_ID.metainfo.xml" "$DATADIR/metainfo/$APP_ID.metainfo.xml"
install -Dm 644 "$SRC/data/icons/$APP_ID.svg" "$DATADIR/icons/hicolor/scalable/apps/$APP_ID.svg"
install -Dm 644 "$SRC/data/icons/$APP_ID-logo.svg" "$DATADIR/icons/hicolor/scalable/apps/$APP_ID-logo.svg"
install -Dm 644 "$SRC/data/icons/$APP_ID-symbolic.svg" "$DATADIR/icons/hicolor/symbolic/apps/$APP_ID-symbolic.svg"
install -Dm 644 "$SRC/LICENSE" "$DATADIR/licenses/nova-control/LICENSE"
