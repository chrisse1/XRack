#!/usr/bin/env bash
#
# Hängt den XRack-USB-Mountpunkt wieder aus - läuft als root, entweder
# ausgelöst von der udev-"remove"-Regel (siehe install.sh) oder manuell
# über den Auswerfen-Button im Webinterface (core/usb_storage.py).
#
# Setzt zusätzlich den zugehörigen xrack-usb-mount@<partition>.service
# zurück auf "inaktiv". Ohne das bleibt der Dienst (wegen
# RemainAfterExit=yes, nötig für FUSE/NTFS) dauerhaft als "aktiv"
# markiert, obwohl der Stick längst wieder ausgehängt ist - beim
# nächsten Einstecken würde die udev-Regel den schon "aktiven" Dienst
# dann gar nicht mehr neu starten, der Stick bliebe unsichtbar.
#

MOUNT_POINT="/media/xrack-usb"

if mountpoint -q "${MOUNT_POINT}"; then

    PARTITION="$(findmnt -n -o SOURCE "${MOUNT_POINT}" 2>/dev/null | sed 's#^/dev/##')"

    umount "${MOUNT_POINT}" || umount -l "${MOUNT_POINT}" || true

    if [ -n "${PARTITION}" ]; then
        systemctl stop "xrack-usb-mount@${PARTITION}.service" 2>/dev/null || true
    fi
fi
