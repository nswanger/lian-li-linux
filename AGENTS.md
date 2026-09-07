# lian-li-linux (Nick's fork)

Contributor checkout of `sgtaziz/lian-li-linux`, the open-source Linux
replacement for L-Connect 3. Upstream is the product. This fork exists to fix
what breaks on a local machine, send each fix upstream as one small PR, and
hold the hardware knowledge those fixes needed. `main` mirrors upstream and
is never committed to directly; `nswanger/local` is `main` plus fork-only commits and
is what the daily driver is built from. Out of scope: features nobody
upstream asked for, and custom modifications that do not provide general
benefit. A change should never benefit one user at the detriment of others.

## Non-negotiables

- **Upstream is the product.** The maintainer squash-merges and has AI
  reviews; Conventional Commit subjects are welcome. Their decisions are not
  re-litigated in our PRs. Nothing fork-only reaches a PR: PR branches are
  cut from `main`, never from `nswanger/local`.
- **One hardware set, one configuration.** We can test what we have: a wired
  HydroShift II LCD Square (`1cbe:a034`, firmware 1.7) bridged to its
  wireless pump head, four wireless UNI FAN TL groups on one TX/RX dongle,
  the per-user daemon on CachyOS built from the local package, and
  `openrgb_server` on with OpenRGB owning every RGB surface through the SDK
  server. Every other device family, wired-only units, the daemon's native
  RGB effect path, the system-service mode, and Fedora packaging are untested
  by default. We can cover additional scenarios, but note limitations.
  The PR body names what could not be tested.
- **Hardware safety.** Never USB-reset the AIO. No write to the wired
  HydroShift II pipe that `docs/local/h2-wired-protocol.md` does not mark
  safe.
- **Verify before asserting in public.** A claim in an upstream issue, PR, or
  comment has been reproduced, or it is labelled as inference. PR 159 was
  filed on a misreading of a Cargo alias and closed as wrong.

## A note from Nick

I moved to this repo when switching to Linux and run it daily on my PC. Any
fix impacts a maintainer and other users who cannot see my setup and I
cannot see theirs. The bar is a small diff, an honest PR body, and no behavior
change for anyone I did not test.

Prefer the boring fix that addresses the core issue and minimizes the surfaces
we touch. Tell me when something is wrong, including when the wrong claim was
ours. Flag it once, then proceed with what I choose. If a rule here fights the
task in front of you, say so and get my sign-off before breaking it. Everything
below is good defaults, not law.

## Glossary

- **Daemon / GUI**: `lianli-daemon` owns the hardware; `lianli-gui` (Tauri)
  talks to it over a Unix socket.
- **Wired / wireless**: wired devices are on USB directly; wireless ones sit
  behind a TX/RX dongle and are addressed by radio MAC.
- **Bridged unit**: a wired HydroShift II paired to a wireless pump head, so
  its ring is reachable over RF as well as over the wired pipe.
- **RF-owned**: an RGB zone the daemon drives over the dongle and therefore
  hides from the wired path and the SDK server.
- **Shared pipe**: the one bulk pipe the HydroShift II LCD and AIO controller
  share; replies route by arrival order, not command byte.
- **Play mode**: the panel ingesting an H.264 stream; the state in which most
  control writes are unsafe.
- **PushRgbData**: the 0xFC ring-colour upload; on the wired pipe it goes
  through a stop/push/reopen cycle.
- **SDK server**: the daemon's OpenRGB-protocol listener on port 6743; while a
  client is connected the daemon suppresses its native RGB config.
- **Daily driver**: the installed package built from `nswanger/local`; a running one
  is a soak and the soak is evidence.

## Ways to hurt yourself

- Never USB-reset the AIO or its xHCI controller: no `USBDEVFS_RESET`,
  unbind, `authorized`, or port power toggle. It locks the header until a
  power cycle.
- Root commands are the user's to run. Hand over the exact command in a block;
  the agent has no sudo password, and guessed flags produced the systemctl
  "--global is not allowed" error.
- Build the package with `makepkg -f -d` under the nvm node on PATH. The
  `-s` flag tries to sudo-install npm, which pacman does not know about.
- Give the user the `sudo pacman -U` and `systemctl --user restart`
  lines when needing to be run together.
- Udev rules go to `/usr/lib/udev/rules.d/`, never `/etc/udev/rules.d/`; an
  etc copy shadows the packaged rule silently.
- After a package upgrade, clear the lingering global-scope enable
  (`systemctl --global disable lianli-daemon.service`, as root) before
  picking a service mode. A greeter instance once opened the LCD first and
  held the pidlock.
- OpenRGB device ids are not stable across daemon restarts. Key wireless
  groups by radio serial.
- A PR whose base is not `main` gets no CI run. Put the local results in the
  PR body.

## Where things live

| Path | Role |
|---|---|
| `crates/lianli-daemon/` | daemon: controllers, IPC, SDK server (`openrgb_server.rs`) |
| `crates/lianli-devices/` | device drivers; `winusb/` is the wired HydroShift II and LCDs, `wireless/` the dongle |
| `crates/lianli-transport/`, `crates/lianli-media/` | USB/HID transports; H.264 and template rendering |
| `crates/lianli-gui/`, `crates/lianli-shared/` | Tauri GUI; types shared over IPC |
| `packaging/` | upstream udev, systemd, sysusers, Arch and Fedora packaging |
| `docs/local/h2-wired-protocol.md` | living doc: what is legal on the wired HydroShift II pipe, with confidence and evidence |
| `docs/local/diag/` | freeze capture tooling and cited evidence; has a README |
| `docs/rgb-mode-capabilities-plan.md`, `README.md`, `CHANGELOG.md`, `templates/` | upstream-owned; not restructured here |
| `~/Github-Repos/lianli-pkg/PKGBUILD` | builds the daily driver from this checkout's `nswanger/local` branch; the older package files beside it are the rollback path |
| `~/Github-Repos/linux-rgb/` | OpenRGB scripts and palettes that consume the SDK server |

Tracker: fork-local work is GitHub Issues in `nswanger/lian-li-linux`, via
`gh`. Anything upstream-facing is an issue or PR on `sgtaziz/lian-li-linux`,
where we create no labels. Everything pending lives in one of those; docs
hold nothing pending. Validation: `python scripts/doc_lint.py` after any doc
change. Deviations from the framework: upstream-owned files are exempt from
its structural tests and change only through upstream PRs; the upstream
`README.md` is linted for dead paths only, as a source of docs PRs.

## Verifying

`cargo check`, `cargo test -p lianli-devices`, and `cargo fmt --check` gate a
PR; CI runs a full build and test on PRs to `main`. The real proof is the
daily driver: rebuild the package, hand the user the install and restart lines,
and read the journal by the new pid.
