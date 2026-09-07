# Project notes — RGB architecture & findings

Working log for the OpenRGB-as-controller setup (started 2026-08-22).
Read alongside README.md; this file is the context dump for future
sessions (human or Claude).

**See also `PROTOCOL.md`** — the distilled model of which commands are
legal on the wired HydroShift II shared pipe in which panel state, with
a confidence ledger. NOTES.md is the chronological log; PROTOCOL.md is
the rules. DRAFT as of 2026-08-24, structure to be reshaped.

## Architecture decision

OpenRGB owns *all* RGB. lian-li-linux (sgtaziz's app; local checkout at
`~/Github-Repos/lian-li-linux`, Nick contributes upstream) does fan curves and
the AIO LCD only. The daemon's built-in OpenRGB SDK server
(`crates/lianli-daemon/src/openrgb_server.rs`, port 6743) bridges the
Lian Li hardware into OpenRGB. The daemon suppresses its native RGB
handling while an SDK client is connected.

## The switches that made it work

- `~/.config/lianli/config.json`: `"openrgb_server": true`
- OpenRGB config `Server.all_controllers: true` — **the key discovery**:
  without it OpenRGB accepts the daemon's devices but does not re-export
  them on its own SDK port 6742, so scripts can't see them.
- OpenRGB autostart (`~/.config/autostart/OpenRGB.desktop`) runs with
  `--server --profile "Gold Blue Split"`.
- OpenRGB keeps a saved SDK client entry for `localhost:6743` and
  auto-reconnects to the daemon.

## Hardware map (device ids as of 2026-08-22)

| id | device | zones | placement |
|----|--------|-------|-----------|
| 0,1 | Corsair Vengeance DDR5 | 10 LEDs | RAM |
| 2 | PNY RTX 5080 Epic-X | "Front"=bottom strip(20), "Side Logo"=face logo(4), "Arrow"(19)+"Rear Logo"(1)=top | GPU |
| 3 | MSI Mystic Light | 4 header stubs | nothing attached — dead |
| 4 | HydroShift II LCD RGB Ring | Ring, 24 | AIO |
| 5 | HydroShift II LCD-S Wireless | Pump Head, 24 | AIO |
| — | UNI FAN TL Wireless `7b:61:f3` | Fan 1..3 ×26 | top |
| — | UNI FAN TL Wireless `59:a1:64` | Fan 1..3 ×26 | front (AIO rad) |
| — | UNI FAN TL Wireless `af:b0:57` | Fan 1..3 ×26 | bottom (mounted reversed → in `flip_devices`) |
| — | UNI FAN TL Wireless `c4:54:dc` | Fan 1 ×26 | rear exhaust |

The daemon exposes one zone per fan, so no segment support is needed.

**OpenRGB device ids are NOT stable** for the four identical wireless
groups — they enumerate in radio-discovery order, which changes across
daemon restarts. Anything that must target a specific group keys on the
serial (`wireless:<mac>`), which is stable. `pattern.py` accepts MAC
fragments in `flip_devices` for this reason.

## Color calibration

Lian Li LEDs render green-heavy. Gold walked #FFAA00 → #FF8C00 → #FF7000
→ #FF6400 → **#FF5000** (final). Corsair RAM renders the same hex much
more orange and washes out blue → separate `ram_gold #FF7800` /
`ram_blue #33AAFF`, plus `brightness 0.4` (RAM has no hardware dimmer in
Direct mode; we scale the colors).

## OpenRGB profiles

- `Gold Blue Split` — the design; loaded at login.
- `Orange All` — old "Default Orange" look extended to the Lian Li
  devices (sampled orange 54,16,0 — dim by design).
- `Default Orange` — original, pre-bridge, local devices only. Kept as-is.

### RESOLVED 2026-08-23: profiles do NOT cover the bridged devices

The "unverified" note above is now answered, and the answer is no. Do not
use OpenRGB profiles for this build.

**Symptom.** Save a profile, load it back: the fans and both HydroShift
devices go white. RAM, GPU and the MSI header restore correctly. That
victim set is exactly the devices proxied from lianli-daemon; nothing
else in the build partitions that way.

**Measured.** A read-only poller (0.5s) watched OpenRGB's state across a
save/load. Every device stayed in Direct, every LED count held, and no
colour in OpenRGB's state was ever white -- while the hardware was
visibly white. State and hardware had diverged.

**Narrowed, not pinned.** Isolating the calls profile restore makes:

| call to a proxied device | OpenRGB state | hardware |
|---|---|---|
| `set_mode("Direct")`, no colour push | unchanged | unchanged |
| `zone.resize(same size)` | **all-white** | unchanged |
| profile restore (does both) | unchanged | **all-white** |

A bare mode set is innocent. A resize desynchronises state from hardware
-- and has been seen breaking in *both* directions, so the mechanism is
not simply "resize whitens the strip". Resizing one 26-LED zone whitened
all 78 LEDs of the device in OpenRGB's state. Best current reading: on
restore the resize reaches the daemon and clears the strip, after which
OpenRGB writes the profile's colours into its own state without
re-pushing them, since from its point of view nothing changed.

**Proving it** needs a packet capture on 6743 during a profile load, to
see which request whitens the strip. Deliberately not done -- it is an
upstream bug in code we do not own, and there is a better workaround.

**Why the script never trips it.** `build_targets` resizes only when the
size actually differs, and always writes colours immediately after, so
any whitening is overwritten in the same pass.

### Persistence: rgb-pattern.service, not profiles

`~/.config/systemd/user/rgb-pattern.service` (enabled) repaints at login.
Strictly better than a profile: profiles cannot hold the comet effect
either, so this is one mechanism instead of two half-working ones.

OpenRGB autostarts from an XDG entry (`app-OpenRGB@autostart.service`),
which is generated and unreliable to order against, so the unit does not
try. `run.sh --wait N` instead blocks until the SDK answers *and* every
device a rule needs has appeared -- which also covers the RF fan groups
arriving late -- then settles 2s for zones to finish enumerating.

    systemctl --user restart rgb-pattern.service   # re-apply now
    systemctl --user edit rgb-pattern.service      # change palette

Desktop launchers for manual switching: `~/Desktop/rgb-ember.desktop`,
`~/Desktop/rgb-coldsteel.desktop` (also in the app menu as "RGB: Ember" /
"RGB: Cold Steel").

**Future item, only if desired:** capture 6743 during a profile load and
report upstream. Not needed for anything to work.

## Upstream defects found (PR candidates, one PR each)

1. Daemon SDK server advertises protocol 4 but never answers the
   profile-list packet (id 150), hanging standard clients
   (openrgb-python times out during handshake). Workaround: talk to
   OpenRGB on 6742 instead of the daemon directly.
2. ~~Repo PKGBUILD: literal `host-tuple` is not a valid target.~~
   **Wrong — do not re-file.** `host-tuple` is a real Cargo alias for the
   host tuple as of Cargo 1.91 (rust-lang/cargo#15838), and the Arch Rust
   guidelines now recommend it. `rustc --target host-tuple` *does* error,
   which is what misled us — it is a Cargo-level substitution, not a rustc
   one. PR #159 filed and closed 2026-08-24.

## Packaging

Daily driver builds from `~/Github-Repos/lianli-pkg/PKGBUILD` (sources local
repo `main`). npm comes from nvm, invisible to makepkg → build with
`PATH="$HOME/.nvm/versions/node/v24.18.1/bin:$PATH" makepkg -f -d`.

## Backlog

- AIO LCD freeze (h264 timeout) — next major thread, plan below.
- GUI "external SDK client active" lockout indicator (upstream PR).
- AUR package udev-path bug — still unreported.
- **TODO (explore separately): put a test seam at the USB bulk transport.**
  `HidTransport` is a trait and mockable; `RusbBulk` is a concrete struct,
  so the h2/LCD path — the one that keeps regressing — has no seam. Idea:
  a `BulkTransport` trait + fake, then encode the invariants hardware cost
  us power cycles to learn: PushRgbData never written while `streaming`;
  SyncPumpFan flushed only at buffer level <=1 (or <=2 after 3 s);
  `write_full` resumes from the offset on a short write; shutdown refuses
  new transfers but lets in-flight ones drain. Repo already has ~144 test
  fns (devices 75, shared 56, daemon 10, transport 3), so the habit exists
  — the USB path is the gap. Good upstream PR on its own. Raised
  2026-08-24; not started.

## Next thread: AIO LCD freeze — investigation plan

Device: HydroShift II LCD Square, 480x480, wired USB
(`hid:1cbe:a034`). History: freezes with h264 timeout; "more stable
recently" per Nick, but not resolved. Even today's clean daemon starts
log `WARN Read after GetVer failed: USB error: Operation timed out`
during LCD init — that warning is a standing lead.

**New symptom (reported 2026-08-22, investigate first):** the rendered
image no longer fills the LCD panel — content shrank after the
0.8.6 → 0.8.8 upgrade. Suspects in the 0.8.7/0.8.8 range:
"feature parity against old gui for template editor" (a25de2f) and the
template/canvas scaling around it; also upstream PR #152 (wired
HydroShift II changes) and #154 (LCD stream deadlock) touch this
hardware — read both before writing any fix to avoid duplicating
Mats2208's work.

### Findings (2026-08-22, second session)

**Shrunken image — root cause found, fixed locally (not yet built/PR'd).**
Journal shows the 10:04 daemon run encoding `480x480@30fps` and the
10:46/11:27 runs encoding `400x400@30fps` on the same 480x480 panel.
`ServiceManager::prepare_media_assets` (`crates/lianli-daemon/src/service/media.rs`)
sizes the custom-template canvas from a `screen_map` keyed by the
*enumerated* device id and falls back to `ScreenInfo::WIRELESS_LCD`
(400x400) on a miss. The enumerated id is `hid:<serial>`
(`hid:660b8008768a8302w`) when the serial string is readable and
`hid:<vid>:<pid>:<port>` (`hid:1cbe:a034:1-12`) when it isn't (e.g. the
device is still held by a dying daemon). Config had the path form, so
the lookup missed whenever the serial *was* readable; the attach path
has an alias fallback (hence the 1 Hz "using compatible alias" warning)
but the screen lookup didn't. Introduced by 5adfde1 "fix hid matching"
(v0.8.6 → v0.8.7). Not addressed by upstream PR #152 or #154 (checked
their media.rs diffs).

Applied:
- `~/.config/lianli/config.json` lcd serial → `hid:660b8008768a8302w`
  (backup `config.json.bak-20260822`). Also silences the 1 Hz warning.
  Daemon reads config at start → needs a daemon restart to take effect.
- Code fix in `~/Github-Repos/lian-li-linux` (uncommitted): screen lookup
  mirrors the attach alias rule (exactly one LCD config + exactly one
  wired AIO LCD → use its screen). `cargo check -p lianli-daemon` passes.
  Rebuild package, restart, confirm journal says `480x480`. PR candidate #3.

**Freeze — leads, not fixed.** After ~15–35 s of streaming the panel
stops ACKing: `Read after h264 chunk failed: USB error: Operation timed
out` every 2.0 s (h2_lcd `READ_TIMEOUT` = 2 s; 902 occurrences today).
`read_response` only warns — no recovery is triggered — so each frame
blocks 2 s and the stream crawls; that *is* the visible freeze. Ideas:
count consecutive read timeouts and call `try_recover()` (PR #152 item 4
makes `try_recover` actually work by releasing the interface first);
shorten the read timeout for streaming chunks. `GetVer` timeout at init
is the same symptom (PR #152 item 3: "this unit never answers GetVer").
Rebase any freeze work on #152.

**Other:** 11:19–11:26 systemd restart loop (counter 85) was the pidlock
refusing to start because a second daemon (pid 47978, outside systemd)
held `/run/lianli-daemon.lock` — not an LCD crash.

### Findings (2026-08-22, evening — freeze captured live)

Boot 18:52; AIO LCD froze at 18:54:53 and stayed frozen. Logs captured
(`journalctl -b _COMM=lianli-daemon`). Timeline:

- 18:53:00 daemon **#1 runs as `plasmalogin` (uid 958)** — the package's
  user unit is preset-enabled for *every* user, so the greeter session
  starts one too; it opens + inits the LCD (GetVer timeout), then a
  second greeter instance (pid 1650) does it again at 18:54:12. Nick's
  own unit is refused by the pidlock 4× until 1650 exits; his daemon
  (2468) is the 3rd open/init of the panel inside 100 s. Fix candidate:
  `systemctl --user --global disable lianli-daemon` + enable only for
  uid 1000, or a `ConditionUser=!@system`-style guard in the unit.
- 18:54:45 live h264 480x480@30 starts (shrunken-image fix confirmed:
  canvas is 480x480 now). 18:54:53 (+7.5 s): `H264 chunk write failed:
  Operation timed out` — a **bulk OUT write** (200 ms timeout), not the
  read-ACK pattern of the morning. From then on *every* write times out
  (h264 + `SyncPumpFan` fan/pump PWM, 342× each over 8 min) → the AIO
  also lost fan/pump control, not just the picture.
- `try_recover()` (core.rs) on the shared-transport path can only
  `clear_halt`; that itself failed (control transfer) → `device_gone`,
  then the attach loop's `detach_and_configure` hit "interface 0 busy"
  (h2_aio still holds the claim) 20×250 ms and gave up, every ~8 s.
- Live probe at 19:05: `lsusb -v -d 1cbe:a034` hung 8 s (EP0 dead) while
  sysfs/lsusb still listed the device — firmware wedge, kernel unaware.
- Experiment: stopped daemon, `USBDEVFS_RESET` → kernel: "Device not
  responding to setup address… error -71", disconnect, re-enumeration
  retries fail (`device descriptor read/64, error -110`) indefinitely.
  **The MCU is hung hard; only a power cycle brings it back.** So the
  freeze is not a host-side timeout-handling bug — the daemon *cannot*
  recover it in software; the best it can do is stop hammering and
  report. Root cause must be whatever the stream does in the first
  ~10–30 s that crashes the firmware (flow control? `wait_buffer` only
  runs if the chunk ACK arrives; this unit "never answers GetVer" —
  does it answer chunk ACKs/QueryBlock? Needs `usbmon` (root) on the
  next fresh boot: `modprobe usbmon; cat /sys/kernel/debug/usb/usbmon/1u`
  from before stream start through the first timeout).
- Proton/Wine (Witcher 3, 19:03) `winedevice.exe` opened
  `/dev/bus/usb/001/003` + all hidraw nodes (winebus libusb backend).
  Not the cause this time (freeze was 18:54) but a standing risk: Wine
  can claim the LCD interface / talk to it. Consider a udev rule or
  Proton `WINEBUS` tweak if it ever correlates.
- PCIe: `link/l1_aspm` = 1 on 03:00.0, 0a:00.0 and 12:00.0 (the xHCI
  hosting the LCD) — ASPM L1 is *enabled* again on that chain; the
  earlier-session disable did not survive. Re-check with `sudo lspci -vv`.
- Side issue: Plasma session-restore launched plain `/usr/bin/openrgb`
  (no `--server`), beating `~/.config/autostart/OpenRGB.desktop`; SDK
  port 6742 was down so `pattern.py` couldn't connect. Relaunched via
  `systemd-run --user --unit=openrgb-server openrgb --startminimized
  --server --profile "Gold Blue Split"`. The .desktop currently says
  `--profile "Default Orange"` (NOTES above says Gold Blue Split) —
  reconcile. TL fan rule now has `brightness = 0.5` (monitor glare);
  saved into the "Gold Blue Split" profile while the wired LCD ring was
  absent → re-run `./run.sh` + save once the AIO is back.

### Findings (2026-08-22, boot 3 — usbmon capture of the freeze)

Reproduced deterministically: stream start +7.3 s (boot 2: +7.5 s).
Debug log + `/var/log/usbmon/bus1-20260822-192046.log` (copy in
`diag/` scratch) show:

- The panel *does* ACK chunks (buffer-level byte climbs 1→2→3→4→8 before
  the fail) and QueryBlock — so flow control exists; GetVer only fails
  on the cold first init.
- Wire rate ≈210–250 KB/s, one ~60 KB keyframe/s; the device ingests
  bulk at only ~600 KB/s (58 KB in 95 ms) and **NAKs bulk OUT for
  >200 ms mid-keyframe**. First stall (+1.8 s): URB cancelled at 2048
  of 6116 bytes (`C Bo … -2 2048`), `write_full` resumed the rest,
  stream survived. Fatal stall (+7.3 s): cancelled at 20480/58829,
  remainder never accepted, then EP0 dead too → MCU wedged, power
  cycle required (USBDEVFS_RESET → "not accepting address, -71").
- Mechanism: h2_lcd `WRITE_TIMEOUT` = 200 ms; libusb cancels the URB,
  rusb returns `Ok(partial)` on timeout, `write_full` resumes from the
  reported offset → either the firmware crashes on the overrun, or the
  cancel/resume desyncs its packet parser. WinUSB default pipe timeout
  is unbounded, so the vendor app never cancels.
- Patch committed in lian-li-linux `fb21828`: WRITE_TIMEOUT → 5 s.
  Boot 3 on it: 4.7 min clean, 0 cancels — but max write latency was
  12 ms, i.e. the panel never stalled, so the timeout was *not*
  exercised. Not proof. `29e8af7` adds `H264 chunk write stalled N ms`
  WARN (>100 ms) so future boots show absorbed stalls; package
  `0.8.8.r3.g29e8af7`. Hold the PR until reps show stalls absorbed
  (or a wedge with zero cancels → firmware overrun, encoder knob next).
  Test: power cycle → install → watch for `-2` Bo completions in usbmon
  and whether the stream passes the 10 s mark. If it still wedges with
  no cancels, it's a firmware buffer overrun → next knob is encoder
  bitrate / keyframe size (`-x264-params keyint=…`, crf/maxrate) or an
  earlier `wait_buffer` threshold.
- Secondary stressor: the 1 Hz device poll (`LCD candidate`) issues 4
  string-descriptor control reads/s to the streaming MCU (~4 ms each).
  Not proven harmful; candidate if the timeout fix is insufficient.
- Bottom fan group `af:b0:57` (rx=8, weakest link) dropped to built-in
  rainbow once; `./run.sh` restores it. OpenRGB autostart this boot ran
  `--profile "Default Orange"` (the .desktop), not Gold Blue Split.

### ROOT CAUSE (2026-08-22, boot 3b — 19:44 wedge with r3 installed)

Wedge reproduced *with* the 5 s write timeout: three NAK stalls
(231/196/218 ms) absorbed fine (`chunk write stalled` WARN works), then a
61 KB keyframe NAKed 5 s straight with **no host cancel** → MCU dead.
So the timeout is hygiene, not the cure. The discriminator:

- Good 15-min run (pid 2546): `SyncPumpFan` (0xFB) written 4× *before*
  the stream, then never. Zero stalls in 15 min.
- All three fatal runs: `SyncPumpFan` written **2×/s throughout the
  stream** (constant pump/fans config → every 1 s tick, set_fan_speeds
  + set_pump_speed). Each bulk stall starts ~0.3 s after a SyncPumpFan
  write (boot 2: writes :27.96/:28.97/:32.99 → stalls :28.27/:29.44/
  :33.31; boot 3b: :28.62/:29.62/:33.64 → :28.70/:29.74/:33.73). The
  panel's ACK buffer-level byte climbs 1→4 between stalls; a 60 KB
  keyframe on a full buffer kills the firmware.
- Why the good run went quiet: the wired unit is **bridged to the
  wireless AIO** (GetH2Params reply bytes 22–27 = f7:0b:d7:e5:66:e1 =
  the WaterBlock2); `control_wired` skips wired writes for bridged
  units — *if* the MAC was learned. MAC learning = `get_h2_params`'s
  unmatched read on the shared pipe; replies of every command (0x79
  ACK, 0x7A QueryBlock, 0xFA params, 0xFB SyncPumpFan, 0x0A GetVer)
  land in whichever thread reads next. Good run learned it in the
  2-tick pre-stream window; fatal runs didn't and never could once
  the LCD thread was reading 30×/s.
- LCD flow control reads the "buffer level" from whatever reply comes
  next (off by 2–3 replies all the time) — so it can't save the panel.
- **Independent corroboration: upstream PR #152 (Mats2208) measured the
  same wedge on their unit without streaming**: "2/s died at 26.5s,
  1/s at 47.1s" — and rate-limits SyncPumpFan to the vendor's ~3.6 s,
  holds the transport lock across write+read, 250 ms reply read, two
  GetH2Params attempts. With h264 streaming concurrently ours dies in
  6–8 s because each SyncPumpFan stalls ingest ~200 ms.

Test build: branch `test-pr152` = main (fb21828 timeout + 29e8af7 warn)
+ PR #152 merged clean; package built in scratch `pkg-pr152/`. Expect:
≤1 SyncPumpFan per 3.6 s (or none once bridged MAC learned), no stalls.
PR plan: (1) our timeout+warn PR, explicitly "complements #152"; (2)
comment on #152 with the usbmon evidence (stall ↔ SyncPumpFan timing,
streaming case dies in 6–8 s). Possible follow-up: learn the bridge MAC
eagerly at channel open and match replies by command byte.

Fans "de-sync" = every daemon restart drops the direct-color frame
(OpenRGB doesn't re-send on reconnect) — `./run.sh` restores; not RF.

**Status 2026-08-22 20:55:** running `test-pr152` build
(`0.8.8.r20.gc7fac56`, main+#152+timeout+warn): 5+ min clean, SyncPumpFan
2× at startup then silent, 0 stalls/cancels. **PR #161 opened**
(fix/h2-lcd-write-timeout: 5 s timeout + stall WARN, framed as
complementary to #152). #152 comment posted 2026-08-22 20:58
(draft kept at `diag/pr152-comment-draft.md`). Keep the test build
for a few days; follow-up PR idea: match replies by command byte + learn
bridge MAC at channel open.

**Next-boot instrumentation (armed 2026-08-22 evening):**
- `~/.config/systemd/user/lianli-daemon.service.d/debug.conf` sets
  `RUST_LOG=…winusb=debug,lianli_transport=debug,lianli_media=debug…`
  (remove + `daemon-reload` when done).
- `diag/usbmon-bus1.service` + `diag/install.sh` (sudo) — usbmon text
  capture of bus 1 from sysinit into `/var/log/usbmon/bus1-*.log`.
- `diag/collect.sh` — run after a freeze; bundles journal, kernel log,
  sysfs, EP0 probe, USB holders, ASPM state, usbmon into `diag/out/`.
- Keep Proton/games closed during the repro; leave the greeter daemon
  as-is for the first run (one variable at a time), then disable it:
  `sudo systemctl --global disable lianli-daemon && systemctl --user enable lianli-daemon`.

Plan:
1. Reproduce the shrunken image; screenshot/photo. Check
   `~/.config/lianli/` template + config for stored resolution/scale
   values that may have been migrated badly. `git log v0.8.6..v0.8.8 --
   crates/lianli-media crates/lianli-devices/src/winusb` for render or
   resolution changes; bisect with local package builds if unclear.
2. For the freeze itself: run with debug logging
   (`RUST_LOG=lianli_devices=debug,lianli_media=debug`), capture journal
   at freeze time; look at the GetVer timeout path and h264 encoder
   (ffmpeg) timeout handling in lianli-media.
3. Hardware context: PCIe ASPM already disabled on the chipset USB
   bridge chain (earlier session) to preempt LCD disconnects — verify
   that's still in effect before blaming software.
4. File findings as separate single-bug upstream PRs.

### Findings (2026-08-23 morning, boot 1 — second freeze mechanism captured)

Build `test-pr152` (0.8.8.r20.gc7fac56). SyncPumpFan was quiet (2× at
startup, #152 working), 0 write stalls/cancels — and the panel still
died at stream +28 s, but **softly** this time: bulk OUT still accepted
instantly, bulk IN never answers, EP0 alive (`lsusb -v` instant).
usbmon `bus1-20260823-102904.log` + debug journal (`diag/out/20260823-103102/`):

- 10:30:13.30 the ONLY non-stream write of the run: **525 bytes =
  PushRgbData (0xFC)** — 512 header + 13-byte tinyuz payload (solid ring
  colour), from `h2_aio::send_rgb_frames` → triggered by
  `service: OpenRGB server active — resyncing last direct-color frame`
  (Nick re-applied the OpenRGB profile / pattern at that moment).
  100 ms read → no reply. The LCD thread's next QueryBlock poll →
  2 s silence ("Buffer wait aborted"), then every h264 chunk read times
  out forever. Panel was at buffer level 4 (full) when the RGB write
  landed, mid `wait_buffer`.
- So the general rule: **any non-stream command on the shared pipe while
  the panel's ingest buffer is full kills it** — SyncPumpFan yesterday
  (hard wedge, mid-keyframe NAK), PushRgbData today (soft hang). #152
  rate-limits SyncPumpFan but explicitly *enables* PushRgbData on this
  unit (switches it to `write_full`; RGB "failed" before) → new exposure.
- Also seen: today's chunks were ~60 KB pipe-buffer lumps (buffer level
  parked at 3–4, `wait_buffer` ~550 ms per cycle) vs per-frame ~6.6 KB
  chunks in yesterday's good 15-min run. Panel drains slowly → host lags
  → bigger lumps → fuller buffer. Worth understanding, but secondary.
- Still unresolved from the greeter: daemon #1 (uid 958, pid 988) ran
  first again and initialised the LCD; Nick's daemon was refused 3× by
  the pidlock. Disable the global unit (command in previous section).

Fix candidates (not written yet):
1. `send_rgb_frames` (and any h2_aio command) must not write while the
   LCD stream is active — either skip/queue ring RGB while streaming, or
   send it only between chunks when buffer level ≤ 1 (hold the lock for
   the whole write+read, like #152 does for SyncPumpFan).
2. If the wired unit is bridged to the wireless AIO, drive the ring over
   RF (as `control_wired` already does for fans/pump) and never touch
   the wired pipe.
3. Reply matching by command byte (0x79/0x7A/0xFA/0xFB/0xFC) so flow
   control reads a real buffer level.

**Status 2026-08-23 ~10:40:** `systemctl --user restart lianli-daemon`
recovered the soft hang (panel ACKing ~30/s again) — no power cycle
needed for this variant. Buffer levels seen in today's stream: 2–9
(never ≤1; level 2 ≈ 1×/s; the 60 KB lumps are ~8 frames each, so the
level is probably a frame count). GetH2Params (0xFA) was also sent 7×
mid-stream and survived — telemetry reads are not the killer.

**Patch written:** lian-li-linux branch
`fix/h2-defer-control-while-streaming` (50acd28 on top of test-pr152).
`LcdLink { bulk, streaming, pending }` replaces `Arc<Mutex<RusbBulk>>`;
h2_aio's SyncPumpFan/PushRgbData are queued while the LCD streams and
flushed by the stream thread at buffer level ≤1 (or ≤2 after 3 s wait;
level 2 is what the vendor waits for before a keyframe), or at clean
stream end. Package built from scratch `pkg-defer/` (PKGBUILD =
lianli-pkg's with branch swapped). Test: install, restart, re-apply the
OpenRGB profile / `./run.sh` mid-stream — should log
`H2: PushRgbData … (deferred)` then `Sending deferred PushRgbData …`
and the panel must keep ACKing. PR candidate #4 once it survives a day.

**10:51 test of r21 (level-gated deferral): FAILED for RGB.** PushRgbData
was deferred and sent 13 ms later at buffer level **1** — panel died
anyway (same soft hang). So PushRgbData during play mode is lethal at any
level (n=2: level 4, level 1); likely the firmware hands the post-header
payload to its stream parser. SyncPumpFan (header-only, 512 B) is a
different animal — keep level-gated. Amended fix: `PendingCmd.play_safe`;
PushRgbData is held until clean stream end + WARN pointing at the
wireless pump-head device (OpenRGB `[5] HydroShift II LCD-S Wireless /
Pump Head`, same 24 LEDs over RF via the bridged WaterBlock2) which
`pattern.toml`'s "HydroShift" rule already paints. Rebuilt as r21
(amended 50acd28→new hash). Restart recovered the panel again.

**10:55 test of r21.g6a52407 (PushRgbData held to stream end): PASS.**
`./run.sh` 3× mid-stream → 3× "ring RGB held" WARN, nothing on the wire,
0 timeouts, 30 ACKs/s sustained. Installed and running. Next: let it
soak through a reboot + normal use; if a day is clean, open PR #4
(`fix/h2-defer-control-while-streaming`, 6a52407, on top of test-pr152
— rebase onto main+#152 or state the dependency). Check Nick confirms
the pump-head ring colours still follow the pattern (via RF device [5]).
Still open: greeter-user daemon start, 60 KB lump / level 2–9 behaviour.

## Handoff (2026-08-23 11:05) — next steps for a future session

State: `lianli-linux-git 0.8.8.r21.g6a52407` installed = test-pr152 +
fix/h2-defer-control-while-streaming (6a52407). Soaking. Nick confirmed
the pump-head ring split still renders (via RF device [5]).

1. **Greeter daemon:** user-level enable done
   (`~/.config/systemd/user/default.target.wants/lianli-daemon.service`).
   Global symlink `/etc/systemd/user/default.target.wants/lianli-daemon.service`
   (Aug 1) still to remove:
   `sudo systemctl --global disable lianli-daemon.service` (or `sudo rm`
   that symlink). Nick's first attempt errored "--global is not allowed"
   — probably typed with --user too; plain rm is equivalent. Verify next
   boot: `journalctl -b _COMM=lianli-daemon | grep -m1 pidlock` should be
   empty and the first daemon should be uid 1000.
   Upstream follow-up (later, separate tiny PR): package should not
   globally enable the user unit for every user (greeter instance opens
   the LCD first).
2. **PR for the deferral fix:** wait for #152 (Mats2208) / #161 (ours)
   to resolve, then rebase `fix/h2-defer-control-while-streaming` onto
   main (+#152 if merged; else state dependency) and open. Body: the
   2026-08-22/23 usbmon evidence (SyncPumpFan ↔ NAK stalls; PushRgbData
   hangs at level 4 and level 1).
   **Done 2026-08-24:** the PushRgbData finding is filed as upstream
   issue #163, which states the fix exists and is waiting on #152 and
   asks sgtaziz whether he wants it stacked or rebased. Confirmed
   against the diff that #152's `dcefcff` (write → write_full in
   `send_rgb_frames`) is what makes the write reachable — so it is a new
   exposure, not a pre-existing bug. Cherry-picking 6a52407 onto main
   fails: it needs `last_sync` (#152 370b0c5), `params_cache`/
   `PARAMS_CACHE_TTL` (#152 6fb2c66) and `sysfs_serial` (#152 cda7624).
3. **#161 write timeout is inert on the fixed stack — don't re-soak it.**
   Amended 2026-08-24 from 5 s to 2 s (matching base.rs/slv3.rs/
   hs2_oled.rs) plus timing moved inside the transport lock. Do **not**
   propose a "15 min soak at 2 s" to validate it: the installed r21
   build already carries the stall WARN (29e8af7) and 5 s (fb21828), and
   7 days of continuous streaming (38,573 chunk-response lines) logged
   **zero** stalls >100 ms. With #152 + the deferral in place nothing
   approaches the timeout, so 200 ms / 2 s / 5 s are indistinguishable
   and the soak has no diagnostic power. The only config that produces
   stalls is bare main + #161, which wedges the panel (power cycle).
   The number that matters is the stall durations: 196 / 218 / 231 ms.
4. **Parked:** 60 KB pipe lumps / buffer levels 2–9 mid-stream (perf, not
   a freeze cause); GetH2Params mid-stream (survived 7×, fine); reply
   matching by command byte + eager bridge-MAC learning (nice-to-have).
5. **Cleanup when done soaking:** remove debug drop-in
   `~/.config/systemd/user/lianli-daemon.service.d/debug.conf` +
   `daemon-reload`; `sudo systemctl disable --now usbmon-bus1` +
   rm the unit (see diag/install.sh) — usbmon log grows ~10 MB/hour
   while streaming.
6. If the AIO freezes again: run `diag/collect.sh` first, then
   `systemctl --user restart lianli-daemon` (recovers the soft variant).
   Never USB-reset the header.
