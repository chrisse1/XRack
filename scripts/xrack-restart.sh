#!/usr/bin/env bash
#
# Plant einen verzögerten Neustart von xrack.service (z.B. nach
# einer Port-Änderung) über einen eigenständigen, transienten
# systemd-Task - unabhängig von der Cgroup des laufenden XRack-
# Dienstes. Würde stattdessen einfach "sleep && systemctl restart"
# als Kindprozess laufen, könnte systemd beim Stoppen des Dienstes
# (Kill-Mode "control-group") den Neustart-Befehl selbst mit
# erschlagen, bevor er fertig ist.
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/system_control.py), nie interaktiv.
#

set -e

systemd-run --on-active=2 --unit="xrack-restart-trigger-$$" \
    systemctl restart xrack.service
