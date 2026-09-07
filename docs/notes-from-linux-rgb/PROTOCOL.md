# HydroShift II wired — shared-pipe protocol model

**Status: DRAFT, 2026-08-24. Structure is provisional — Nick to reshape.**

Purpose: the hardware-derived rules that no static analysis can recover.
Which commands are legal on the shared bulk pipe, in which panel state,
and what it costs to get it wrong. `NOTES.md` is the chronological log;
this file is the *model* distilled from it.

**Normative use:** before changing anything that writes to the wired
HydroShift II transport, check the command against this table. If you
learn something that contradicts a row, change the row and cite the
capture — do not leave the doc and the code disagreeing.

Scope: wired HydroShift II LCD, `1cbe:a034`, fw 1.7, one unit (Nick's
LCD Square). Everything here is n=1 hardware unless a row says otherwise.

---

## 1. The shared pipe

The LCD panel and the AIO controller (pump, fans, RGB ring) are the same
USB device and share one bulk pipe. `H2AioController` and the LCD stream
thread both write to it under one mutex. There is no per-command reply
routing: a reply to *any* command is picked up by whichever thread reads
next (§4.1). That single fact explains most of the failure modes below.

## 2. Panel states

| State | Meaning | How it is entered / left |
|---|---|---|
| `idle` | not streaming; control commands accepted normally | default; after `StopPlay` + wake preamble (§5) |
| `play` | H.264 play mode, panel ingesting a stream | `StartPlay` (0x79) → chunk writes; ends at clean stream end |

`play` is the dangerous state. In code the flag is `LcdLink::streaming`
(`lcd/core.rs:58`), set around the stream loop at `core.rs:728/736`.

The panel reports an **ingest buffer level** in byte 8 of its chunk-ACK
reply. Observed range 0–9. Probably a frame count: 60 KB pipe lumps are
~8 frames and the level tracked them; level 2 recurs ~1×/s during a
healthy 30 fps stream. Not confirmed against vendor docs.

## 3. Command legality

Command bytes are from `crates/lianli-devices/src/crypto.rs:11-34`.

| Byte | Command | Size | `idle` | `play` | Confidence |
|---|---|---|---|---|---|
| 0x79 | StartPlay / h264 chunk | 512 + chunk | n/a | **required** — this *is* the stream | high |
| 0x7A | QueryBlock | 512 | safe | **safe** — the stream's own flow control | high |
| 0xFB | SyncPumpFan | 512 (header only) | safe | **gated**: only at buffer level ≤1, or ≤2 after a 3 s wait | high (failure), medium (gate) |
| 0xFC | PushRgbData | 512 + payload (525 typical) | safe | **LETHAL at any buffer level** — hold until stream end | medium (n=2) |
| 0xFA | GetH2Params | 512 | safe | *unproven* — survived 7 sends mid-stream, never stress-tested | low |
| 0x0A | GetVer | 512 | safe | untested in `play` | none |
| 0x7B | StopPlay | 512 | safe | ends the stream; part of wake preamble | high |
| 0x34 | StopClock | 512 | safe | untested in `play` | none |

Gate constants in code: `CONTROL_SAFE_LEVEL = 1`, `CONTROL_RELAXED_LEVEL = 2`,
`CONTROL_RELAX_AFTER = 3s` (`lcd/core.rs:110-114`), applied in
`flush_pending_control` (`core.rs:643`).

### 3.1 Why SyncPumpFan is gated rather than banned

512-byte header, no payload. In `play` with a full buffer it triggers a
bulk-OUT NAK stall ~0.3 s later; a keyframe landing on the full buffer
then kills the MCU.

Evidence — 2026-08-22 usbmon, wedge 6–8 s into a stream on three
consecutive boots (+7.5 s, +7.3 s, +6.2 s), with every stall traceable to
a preceding write:

| SyncPumpFan write | stall starts | outcome |
|---|---|---|
| :27.96 / :28.97 / :32.99 | :28.27 / :29.44 / :33.31 | fatal :34.81 |
| :28.62 / :29.62 / :33.64 | :28.70 / :29.74 / :33.73 | fatal :34.45 |

Stalls 80–230 ms; buffer-level byte climbs 1→2→3→4 between them; the
fatal one is always a ~60 KB keyframe NAKed forever.

The gate (level ≤1) has run 7 days without a counterexample, but absence
of failure at n=1 unit is weak evidence that the threshold is *correct*
rather than merely conservative.

### 3.2 Why PushRgbData is banned outright

512-byte header **plus payload** (13-byte tinyuz for a solid colour).
This is the only AIO command exceeding one bulk packet.

The intuitive fix — gate it on buffer level like SyncPumpFan — was tried
and **failed**: deferred 13 ms and sent at level **1**, the panel died
anyway (2026-08-23 10:51). Combined with the level-4 case at 10:30, that
is n=2 across opposite ends of the buffer range, so level is not the
variable. Working hypothesis: in `play` the firmware feeds whatever
follows the 512-byte header to its H.264 stream parser, which would
explain why header-only commands behave differently. Unverified.

Upstream: filed as issue #163. Note this only became reachable when
#152's `dcefcff` switched the write from `write()` to `write_full()` —
before that the payload silently short-wrote and wired ring RGB simply
did not work.

**Workaround:** on a bridged unit the same 24-LED ring is reachable over
RF via the wireless pump-head device, which is unaffected.

## 4. Transport invariants

These are properties of the code, not the firmware, but breaking them
reproduces firmware failures.

1. **`write_full` timeout is per URB, not per call.** It loops until the
   whole buffer is accepted and each `write_bulk` gets the full timeout,
   so worst case is `timeout × chunks` — as the doc comment at
   `lianli-transport/src/usb.rs:210` states. The `shutting_down()` guard
   is checked on entry only, not per iteration.
2. **Never resume a partial write after a mid-URB cancel.** A too-short
   write timeout makes libusb cancel mid-packet; `rusb` reports the
   partial count as `Ok(n)`, `write_full` resumes from that offset, and
   the firmware desyncs. This is what PR #161 addresses (200 ms → 2 s).
3. **Never abandon a command mid-`write_full`.** Forcing the daemon down
   mid-transfer left the AIO not servicing USB at all. The shutdown guard
   belongs at command boundaries, not inside one.
4. **Hold the transport across write *and* reply read.** See §4.1.

### 4.1 Reply routing is by arrival order, not command byte

Replies to 0x79 / 0x7A / 0xFA / 0xFB / 0x0A all land in whichever thread
reads next. Consequences seen in practice:

- `get_h2_params` can miss its own reply, so the bridged pump-head MAC
  (bytes 22–27 of the 0xFA reply) is never learned, so `control_wired`
  keeps talking to a unit it should be skipping. The one clean 15-minute
  run was the run where the MAC *was* learned early.
- A slow reply left queued poisons the next read — the reason the
  SyncPumpFan reply wait went 50 ms → 250 ms.

**Open fix:** match replies by command byte. Would close this properly.

## 5. Wake preamble

After `play`, the device ignores control commands until re-armed by
`StopPlay` (0x7B) → `StopClock` (0x34) → `GetVer` (0x0A), 150 ms apart
(`winusb/h2_aio.rs::wake`). Asserted by the existing code comment; not
independently re-measured.

## 6. Failure modes and recovery

| Mode | Signature | Recovery |
|---|---|---|
| **Soft hang** | bulk IN silent, EP0 alive (`lsusb -v` instant) | `systemctl --user restart lianli-daemon` |
| **Hard wedge** | bulk *and* EP0 dead; `Device not responding to setup address`, `-71` | power cycle or S3 suspend **only** |

**Never USB-reset the header.** No `USBDEVFS_RESET`, sysfs unbind/bind,
`authorized=0/1`, or port power toggle against `1cbe:a034` or its xHCI
controller — it locks the header out until a full power cycle. Diagnosis
stays read-only: journal, usbmon, `lsusb`, sysfs reads.

## 7. Confidence ledger

Rows worth distrusting, in order:

1. `GetH2Params` in `play` — marked *unproven*, n=7 with no adverse
   event. Absence of a wedge is not proof of safety; it may simply be
   rarer than the 6–8 s SyncPumpFan window.
2. `SyncPumpFan` level ≤1 gate — the threshold is a guess that has held
   for 7 days. Untested whether ≤2 or ≤3 would also hold.
3. `PushRgbData` "any level" — n=2 (levels 4 and 1). Strong enough to
   act on, not strong enough to explain.
4. Buffer level = frame count — inferred from lump sizes, never
   confirmed.
5. Everything here is one unit, one firmware (1.7). Mats2208's LCD
   Circle showed different behaviour on the same code and traced his to
   a documented power-delivery fault, so cross-unit generalisation is
   unsafe.

## 8. Evidence index

| Date | Artefact | What it shows |
|---|---|---|
| 2026-08-22 | usbmon bus 1 + debug journal | SyncPumpFan ↔ NAK stall correlation; 6–8 s wedge, 3 boots |
| 2026-08-23 | `bus1-20260823-102904.log`, `diag/out/20260823-103102/` | PushRgbData at level 4 → soft hang; only non-stream write of the run |
| 2026-08-23 10:51 | daemon debug | PushRgbData at level 1 → soft hang (level-gating disproved) |
| 2026-08-24 | 7-day journal, 38,573 chunk-response lines | zero stalls >100 ms with #152 + deferral in place |
