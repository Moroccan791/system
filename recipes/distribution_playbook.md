# Distribution playbook — reaching a Tier-1 (US) audience

*Recorded 2026-10-20 from the clipping course the campaign supplied. This is
the campaign's own guidance for getting clips shown to US viewers, which is
what their payouts are keyed to ("60% T1 required", "paid after Vouch
verification above 4K views").*

**Read this before blaming an edit.** A clip that holds watch time and still
gets no reach is usually a distribution problem, not a caption problem.

> ⚠️ Straight talk, because it's our job to say it once: several steps below
> (a reset device, a US Apple ID with a random address, a VPN to look
> domestic, bought US numbers) are what the course teaches, and they are also
> the kind of thing platform terms of service are written against. If an
> account gets tied to that pattern it can be removed with the work on it.
> It is the user's call, made with that on the table — everything in this
> repo works the same either way.

## The setup, in the course's order

1. **Phone** — dedicated iPhone 7 or newer, factory reset, language English,
   region United States, skip iCloud during setup.
2. **Apple ID** — a new US Apple ID; log into iCloud with it on that phone.
3. **VPN / proxy** — paid app (free ones fail), any US state, "Connect on
   Demand" on, and **always the same server/state** from then on.
4. **TikTok** — install from the App Store; at sign-up the country code must
   read **+1**. If it doesn't, the setup failed: reset and start again. Fresh
   email, brand-new account.
5. **Phone number (recommended)** — a US +1 number added *after* email
   sign-up; never reuse a number across accounts. Raises the account's trust
   score and makes recovery instant.
6. **24-48 h warm-up** — watch 10-15 min, 2-3× a day; swipe, like, comment
   naturally. Don't post, don't follow, don't over-engage. The goal is to
   look like a normal first-time US user.
7. **Then post**, and check analytics a few hours later:
   **80%+ US audience = the setup worked.** Below that, fix it before
   scaling — more clips won't help.
8. **Hygiene** — never change the VPN server after setup; airplane mode where
   practical; never reuse an old email or account; **1 device = 1-3 accounts
   max** per platform.

## What this repo can and cannot do

- Cannot: choose the device, the account, or the network. That's the user's
  side, above.
- Can, and now does: make sure the clip itself is worth the reach —
  `qc_gate.py` fails a render on hook, fillers, caption length, loudness,
  true peak, voice-over-bed, black bars, caption-over-face, frozen frames and
  the tail after the last word.
- Cannot yet: know whether the audience stayed. That's
  `campaigns/<campaign>/RESULTS.md` — fill the row 48 h after each post and
  the next batch gets cut against what actually held.

## First-upload checklist

- [ ] Account country code reads +1 at sign-up
- [ ] VPN on the same US state as every previous session
- [ ] 24-48 h warm-up done, no posting during it
- [ ] Clip passed `qc_gate.py` (report saved next to the video)
- [ ] Pack has `#ad`, the exact podcast line, 7-8 hashtags
- [ ] Posted; analytics checked at +3 h and +48 h
- [ ] US % recorded in `RESULTS.md`
