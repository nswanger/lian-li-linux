# diag

Capture tooling for wired HydroShift II freezes, plus the evidence the
protocol doc cites. Run in this order:

1. `install.sh` needs root: hand Nick `sudo ./install.sh`. It installs
   `usbmon-bus1.service`, a usbmon text capture of USB bus 1 from sysinit
   into `/var/log/usbmon/`. The log grows about 10 MB per hour while the
   LCD streams, so leave it installed only while investigating.
2. `collect.sh` after a freeze and **before any restart**. No root needed.
   It bundles the daemon journal, kernel log, sysfs, an EP0 liveness probe,
   USB holders, ASPM state, and the usbmon log into `out/<timestamp>/`.
3. Recover per §6 of `docs/local/h2-wired-protocol.md`. Never USB-reset the
   AIO.

Daemon debug logging comes from a user drop-in at
`~/.config/systemd/user/lianli-daemon.service.d/debug.conf`. Filter the
journal by the running pid:

```
journalctl --user _PID=$(systemctl --user show -p MainPID --value lianli-daemon)
```

When the investigation ends, hand Nick the cleanup: `sudo systemctl disable
--now usbmon-bus1`, `sudo rm /etc/systemd/system/usbmon-bus1.service`, and
removing the debug drop-in followed by `systemctl --user daemon-reload`.

`out/` is captured evidence, referenced from the protocol doc's evidence
index. Keep it; do not add captures that were not cited.
