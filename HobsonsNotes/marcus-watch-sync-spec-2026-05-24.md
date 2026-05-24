# Marcus Watch-Sync — Build Spec (from BD, 2026-05-24)

Hobson — this is from BD downstairs. Dan's de-Googled NVIDIA Shield now plays
Marcus's queue via **SmartTube** (anonymous, no Google account on the device).
The one thing that breaks in that setup: Marcus never learns what Dan actually
watched on the couch, because there's no Discord on the TV and no account to
read history from. This spec closes that loop.

You built Marcus and know the DB cold — I'm not going to explain `marcus.video`
or `db.py` to you. The only integration point you need is the one you already
have: **`db.py --set-status <video_id> watched`**. Everything below is the
Shield-side stuff you can't see from up there, plus the design and the
acceptance bar.

## Goal

A host-side poller that detects which Marcus-queued video Dan watched (to
completion) on the Shield and flips it to `watched` in the Marcus DB — so your
existing `pick`/`get_*` queries (which already exclude `watched`) stop
re-queuing it, and the taste loop has real signal. No Google, no login, no
root, nothing leaves the LAN.

## The mechanism (PROVEN — I ran this on the device today)

SmartTube publishes a MediaSession. `adb shell dumpsys media_session` while it
plays exposes the now-playing **title + channel + playback position** — no root,
no account. Real capture from the Shield, mid-playback:

```
  Sessions Stack - have 1 sessions:
    org.smarttube.stable org.smarttube.stable/org.smarttube.stable (userId=0)
      package=org.smarttube.stable
      active=true
      state=PlaybackState {state=2, position=7626, buffered position=44320, speed=0.0, ...}
      metadata: size=6, description=Gas explosion at Shanxi coal mine kills at least 90: State media, Al Jazeera English, null
```

Parse notes:
- `package=org.smarttube.stable` — filter on this; ignore any other session.
- `metadata: ... description=<TITLE>, <CHANNEL>, <icon/null>` — the title is the
  first comma-field, channel the second. **Title is the join key** (you store
  exact titles in `marcus.video.title`); channel is a good tiebreaker.
- `state=PlaybackState {state=N, position=MS, ...}` — `N`: 1=stopped, 2=paused,
  3=playing, 6=buffering. `position` is **milliseconds**.
- dumpsys exposes title, **not** the 11-char video_id. Hence title(+channel)
  match against currently-`queued` rows. The daily queue is ~30 items, so
  collisions are vanishingly unlikely; title+channel makes it safe.

## "Watched" heuristic

- Compute completion from `position` (ms → s) vs `marcus.video.duration_seconds`.
  Mark `watched` at **≥ ~85%** (tune to taste). Some duration rows are null —
  for those, skip the %-calc and fall back to "seen near the end across two
  consecutive polls," or just leave them for manual handling. Your call.
- **De-dupe:** once a video_id is flipped to `watched`, don't re-fire.
- Don't infer `skipped` in v1 — pause-vs-bail is ambiguous and Dan's playback
  mode pauses after every video by design (see below). Only ever set `watched`.
  Leave everything else alone.

## Shield / ADB facts you need

- **Endpoint:** `192.168.50.41:5555` (Ethernet, DHCP-reserved at the ASUS router
  → stable, won't drift).
- **adb on the host:** install it if it's not there. The poller shells out to
  `adb connect 192.168.50.41:5555` then `adb shell dumpsys media_session`.
- **⚠️ One-time authorization (Dan, physical):** only BD's container key is
  currently authorized on the Shield. The host's adb key is different, so the
  first `adb connect` from the host will throw a "Allow USB debugging?" prompt
  **on the TV** — Dan taps Allow (check "always allow from this computer").
  Until that tap, host adb shows `unauthorized`. This is the one human step.
- **Playback mode is "pause after each video."** BD set this so the algorithm
  can't autoplay Dan off the curated queue. Practical effect for you: when a
  video ends, SmartTube sits at `state=2` (paused) with `position` near the end,
  often for a while. So treat **high-position-while-paused** as a completion
  signal too, not just `state=3`.
- **Sleep/disconnect:** Shield sleeps; adb will drop. Poller must reconnect and
  no-op gracefully (no session / not-authorized / connection refused are all
  normal — log quietly, never crash the service).

## Architecture (recommendation, not gospel)

- **Long-running host service**, not a cron/timer — you want a tight-ish loop.
  Poll every **~30s** (shortest content is 2–3 min news, so 30s never misses a
  completion window). A `coys@marcus-watch`-style systemd unit fits your
  existing pattern, or a standalone unit; runs as the `marcus` user so it
  already has `~/.pgpass` and the venv.
- Reuse Marcus's venv/`db.py` import, or just call
  `db.py --set-status <id> watched` as a subprocess. Either's fine — it's your
  module.
- **Do NOT touch Marcus's existing scripts.** This is new infra (your lane per
  your own standing corrections); the curator scripts stay frozen. The only
  Marcus surface this uses is the `--set-status` CLI you already shipped.

## Privacy invariants (do not violate — this is the whole point of the Shield)

- Never sign SmartTube into a Google account. Never add an account to the Shield.
- Never allowlist a blocked Google host to "make something work."
- Keep all of this LAN-local. The poller talks host↔Shield and host↔Postgres.
  Nothing about Dan's viewing goes to Google.

## Acceptance criteria (so Dan can say "go" and watch it work)

1. Dan plays a Marcus-queued video on the Shield to the end → within one poll
   cycle, that row's `status` = `watched` in `marcus.video`.
2. A video he opens but bails on early does **not** get marked watched.
3. The next nightly `build_playlist` no longer includes the watched one
   (already true via your existing exclusion logic — just confirm end-to-end).
4. Service survives Shield sleep + reboot: reconnects, keeps going, no crash.
5. Zero Google account / login / root anywhere in the path.

## Open decisions to confirm with Dan at "go"

- Poll interval (default 30s) and watched threshold (default 85%).
- Service form (long-running unit recommended).
- v2 maybe-later: capture videos Dan watched that *weren't* in the queue (i.e.
  he followed a recommendation) as a taste signal. Out of scope for v1 — there's
  no Marcus row to attach it to yet.

---
*BD ran the dumpsys capture and the SmartTube setup from the container on
2026-05-24; ADB from an authorized session works. The only unproven bit on the
host side is the one-time auth tap above.*
