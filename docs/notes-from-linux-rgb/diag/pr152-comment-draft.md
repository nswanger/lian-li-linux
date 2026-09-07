<!-- DRAFT — review before posting to https://github.com/sgtaziz/lian-li-linux/pull/152 -->

Some wire-level data that backs up item 4 / the `SyncPumpFan` rate limit, from a HydroShift II LCD Square (1cbe:a034, fw 1.7) that is also streaming live h264 to the panel. Captured with usbmon on the bus plus the daemon at debug.

**The streaming case dies much faster than 26 s.** With the default wired config (constant pump/fans → `set_fan_speeds` + `set_pump_speed` every 1 s tick = 2 `SyncPumpFan`/s) the panel wedges 6–8 s into an h264 stream, three boots in a row (+7.5 s, +7.3 s, +6.2 s). Wedge = bulk OUT NAKed indefinitely *and* EP0 dead; `USBDEVFS_RESET` gives `Device not responding to setup address … -71`; only a reboot/power cycle brings it back.

**Every bulk stall starts ~0.3 s after a `SyncPumpFan` write.** Two runs:

| `SyncPumpFan` write | bulk OUT stall starts |
|---|---|
| :27.96 / :28.97 / :32.99 | :28.27 / :29.44 / :33.31 → fatal :34.81 |
| :28.62 / :29.62 / :33.64 | :28.70 / :29.74 / :33.73 → fatal :34.45 |

Stalls are 80–230 ms; between them the panel's chunk-ACK buffer-level byte climbs 1→2→3→4; the fatal one is always a ~60 KB keyframe that gets NAKed forever (28160 of 61317 bytes accepted, then nothing).

**The one run that survived (15 min, zero stalls) is the one where the controller went quiet.** This unit is bridged to a wireless AIO (the `GetH2Params` reply carries the WaterBlock2's MAC at bytes 22–27), so `control_wired` is meant to skip it — but that depends on `get_h2_params` having read *its own* reply on the shared pipe. Replies of every command (0x79 chunk ACK, 0x7A QueryBlock, 0xFA params, 0xFB SyncPumpFan, 0x0A GetVer) turn up in whichever thread reads next; in the good run the MAC got learned in the two ticks before the stream started, in the bad runs it never did. Your "hold the transport across write+read" + two-attempt `GetH2Params` should help a lot here; matching the reply by command byte would close it fully.

**With this PR applied** (on top of main + the small write-timeout change in #161): `SyncPumpFan` goes out twice at startup (~4 s apart) and then not at all once the bridge MAC is learned; 0 stalls, 0 cancelled URBs over 15+ min of streaming.

One detail worth knowing for the 26 s number: the h2 LCD write timeout was 200 ms (the other LCD drivers use 2 s), so on a NAK stall libusb cancelled the URB mid-transfer and `write_full` resumed from the partial offset. That's what #161 changes; it doesn't prevent the wedge by itself — the rate limit does — but it removes a second way of corrupting the stream once the panel is stalling.

Happy to share the usbmon captures if useful.
