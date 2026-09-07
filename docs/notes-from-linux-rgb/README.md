# Notes from linux-rgb

Landed 2026-09-06 from `~/Github-Repos/linux-rgb`, where they no longer belong: that repo only uses the daemon's OpenRGB passthrough. Fold into this repo's structure; nothing here is authoritative yet.

- `PROTOCOL.md` — HydroShift II wired shared-pipe command legality, with a confidence ledger. Draft, written 2026-08-24 against fw 1.7, one unit.
- `NOTES.md` — chronological investigation log, 2026-08-22 to 2026-08-23: LCD freeze root cause, PushRgbData-in-play-mode, deferral fix. The first four sections are OpenRGB-side and are already captured in linux-rgb.
- `HANDOFF-upstream.md` — upstream PR/issue status as of 2026-08-25. Likely stale after the 0.8.10 pull.
- `diag/` — usbmon capture unit, collector script, captured evidence from 2026-08-23, and the posted #152 comment draft.
