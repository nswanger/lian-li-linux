# diag

Capture tooling for AIO freezes. Run in this order:

1. `sudo ./install.sh` — installs `usbmon-bus1.service`, a usbmon text capture of bus 1 from sysinit into `/var/log/usbmon/`. Log grows ~10 MB/hour while streaming; disable when not investigating.
2. `./collect.sh` after a freeze, before any restart — bundles journal, kernel log, sysfs, EP0 probe, USB holders, ASPM state and usbmon into `out/<timestamp>/`.

`out/` holds captured evidence and is referenced from `PROTOCOL.md`'s evidence index. `pr152-comment-draft.md` is the posted draft of an upstream comment, kept as a record.
