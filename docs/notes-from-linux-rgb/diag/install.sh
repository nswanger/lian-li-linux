#!/usr/bin/env bash
# Install the bus-1 usbmon capture unit (needs root). Run: sudo ./install.sh
set -euo pipefail
cd "$(dirname "$0")"
install -m 644 usbmon-bus1.service /etc/systemd/system/usbmon-bus1.service
systemctl daemon-reload
systemctl enable --now usbmon-bus1.service
sleep 1
systemctl --no-pager --lines=3 status usbmon-bus1.service
ls -l /var/log/usbmon/
echo "OK — capture runs from next boot too. Remove with: sudo systemctl disable --now usbmon-bus1; sudo rm /etc/systemd/system/usbmon-bus1.service"
