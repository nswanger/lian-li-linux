#!/usr/bin/env bash
# Run after an AIO LCD freeze: bundles everything needed to analyse it.
# No root needed (usbmon log is world-readable). Output: diag/out/<timestamp>/
set -uo pipefail
cd "$(dirname "$0")"
out="out/$(date +%Y%m%d-%H%M%S)"; mkdir -p "$out"
echo "collecting into $out"
journalctl -b _COMM=lianli-daemon -o short-precise --no-pager > "$out/daemon.log"
journalctl -b -k --no-pager > "$out/kernel.log"
journalctl -b --no-pager -o short-precise _COMM=openrgb _COMM=lianli-gui > "$out/openrgb-gui.log" 2>/dev/null
uptime > "$out/uptime.txt"; date -Is >> "$out/uptime.txt"
lsusb > "$out/lsusb.txt"; lsusb -t >> "$out/lsusb.txt"
{ for d in /sys/bus/usb/devices/1-*; do [ -f "$d/idVendor" ] || continue; echo "== $d"; for f in idVendor idProduct product serial devnum speed urbnum power/runtime_status power/control; do printf "%s=%s\n" "$f" "$(cat "$d/$f" 2>/dev/null)"; done; done; } > "$out/sysfs-bus1.txt"
{ echo "# EP0 liveness: lsusb -v on the LCD (hangs ~8s when the MCU is wedged)"; time (timeout 10 lsusb -v -d 1cbe:a034 2>&1 | grep -E "iProduct|iSerial|bEndpointAddress" ); } > "$out/ep0-probe.txt" 2>&1
fuser -v /dev/bus/usb/001/* > "$out/usb-holders.txt" 2>&1
ps -eo pid,lstart,cmd | grep -iE "wine|proton|lianli|openrgb" | grep -v grep > "$out/procs.txt"
for d in 0000:03:00.0 0000:0a:00.0 0000:12:00.0; do echo "$d l1_aspm=$(cat /sys/bus/pci/devices/$d/link/l1_aspm 2>/dev/null)"; done > "$out/aspm.txt"
latest=$(ls -t /var/log/usbmon/bus1-*.log 2>/dev/null | head -1)
if [ -n "$latest" ]; then
  cp "$latest" "$out/usbmon-bus1.log"
  echo "usbmon: $(wc -l < "$latest") lines copied"
  # Quick summary: first -110 (ETIMEDOUT) / -2 (cancel) completions and URBs by direction
  awk '$3=="C" && ($5=="-110" || $5=="-2" || $5=="-32" || $5=="-71") {print; n++} n>=20{exit}' "$latest" > "$out/usbmon-first-errors.txt"
else
  echo "no usbmon log found (install.sh not run / unit not active?)" | tee "$out/usbmon-bus1.log"
fi
echo "first daemon WARN/ERROR lines:"; grep -m5 -E "WARN|ERROR" "$out/daemon.log" | cut -c1-200
echo "done: $out"
