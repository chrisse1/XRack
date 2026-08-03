#!/usr/bin/env bash
#
# Hängt den XRack-USB-Mountpunkt wieder aus, sobald der Stick entfernt
# wurde. Läuft als root, ausgelöst von einer udev-Regel (siehe
# install.sh).
#

MOUNT_POINT="/media/xrack-usb"

if mountpoint -q "${MOUNT_POINT}"; then
    umount "${MOUNT_POINT}" || umount -l "${MOUNT_POINT}" || true
fi
