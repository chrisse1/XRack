#!/usr/bin/env bash
#
# Hängt eine per udev erkannte USB-Partition automatisch unter einem
# festen Pfad ein, damit XRack Aufnahmen dorthin kopieren kann - ganz
# ohne Verzeichnisauswahl im Webinterface. Läuft als root, ausgelöst
# von einer udev-Regel (siehe install.sh) bei jedem neu erkannten
# Blockgerät. Unterstützt genau einen angeschlossenen USB-Stick
# gleichzeitig.
#
# Aufruf: xrack-usb-mount.sh <Partition, z.B. sda1> <uid> <gid>
#

set -e

PARTITION="$1"
UID_NUM="$2"
GID_NUM="$3"
DEVICE="/dev/${PARTITION}"
MOUNT_POINT="/media/xrack-usb"

# Nur echte Wechseldatenträger automatisch einhängen - kein internes
# Dateisystem (z.B. Root-/Boot-Partition bei einem per USB gebooteten Pi).
DISK_NAME="$(lsblk -no PKNAME "${DEVICE}" 2>/dev/null || true)"

if [ -z "${DISK_NAME}" ] || [ "$(cat "/sys/block/${DISK_NAME}/removable" 2>/dev/null)" != "1" ]; then
    exit 0
fi

# Schon irgendwo eingehängt? Dann nichts tun.
if mount | grep -q "^${DEVICE} "; then
    exit 0
fi

mkdir -p "${MOUNT_POINT}"

# Mountpunkt schon belegt (ein anderer Stick wurde zuerst erkannt)?
# Dann diese Partition ignorieren.
mountpoint -q "${MOUNT_POINT}" && exit 0

FSTYPE="$(lsblk -no FSTYPE "${DEVICE}" 2>/dev/null || true)"

case "${FSTYPE}" in
    vfat|exfat)
        mount -o "uid=${UID_NUM},gid=${GID_NUM},umask=000" "${DEVICE}" "${MOUNT_POINT}"
        ;;
    ntfs)
        mount -t ntfs-3g -o "uid=${UID_NUM},gid=${GID_NUM},umask=000" "${DEVICE}" "${MOUNT_POINT}"
        ;;
    ext4|ext3|ext2)
        mount "${DEVICE}" "${MOUNT_POINT}"
        chown "${UID_NUM}:${GID_NUM}" "${MOUNT_POINT}"
        ;;
    *)
        exit 0
        ;;
esac
