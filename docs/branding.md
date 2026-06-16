# Matchwright — branding & launch checklist

Operational checklist for standing up the **Matchwright** brand. Captures
decisions already made, the open steps (domains, handles, trademark, asset
exports), and notes from the naming research so we don't re-derive them.

> Status legend: ✅ done · ⏳ in progress · ☐ to do

## Decisions already made

- **Product name:** **Matchwright** (*match* + *-wright*, "the craftsman who
  matches you to the role"). ✅
- **Launch domains:** `matchwright.app` + `getmatchwright.com` (the bare
  `matchwright.com` is taken — see below). ✅ *(decision; not yet registered)*
- **Logo:** cheerful cartoon-goose patch with a curved `MATCHWRIGHT` wordmark.
  The goose is a **mascot** — it does not literally depict the name. ✅
  - Canonical SVG: `assets/logo.svg` (served from `web/assets/logo.svg`)
  - ASCII: `assets/logo.txt` (+ `tui/tui/logo.py`)
- **Palette** (from `assets/README.md`): sky `#BFE6F2`, body `#FFFFFF`, beak
  `#F6A623`, sparkles `#FFD24A`, outline/eye/wordmark `#2B2B2B`. ✅

## Domains

### `matchwright.com` — taken, dormant (watch it)
From RDAP (as of 2026-06-16):
- Registered **2026-06-12**, **expires 2027-06-12**, registrar **Cloudflare**.
- WHOIS privacy on; only leaked detail is region **NM (New Mexico, US)**.
- No website, no MX (email), no TXT, **no TLS certs ever issued** → it's a bare
  speculative hold, not an active build. Competitor risk currently low.

Options (no direct contact possible — privacy-protected):
- ☐ **Backorder** it for the 2027-06-12 expiry (Dynadot / Porkbun / GoDaddy
  backorder) in case the holder lets it lapse.
- ☐ **Anonymous broker offer** (Sedo / Dan.com / GoDaddy Domain Buy) to ask if
  it's for sale — cheap to inquire.
- ☐ Re-check status periodically (has a site/competitor appeared?).

### Register now
- ☐ `matchwright.app` — primary launch domain (`.app` forces HTTPS, which is fine).
- ☐ `getmatchwright.com` — marketing/redirect.
- ☐ Defensive grabs (cheap, optional): `matchwright.io`, `matchwright.co`,
  `matchwright.dev`, `trymatchwright.com`. Skip TLDs you won't use.

### DNS / email after registration
- ☐ Point DNS (Cloudflare DNS recommended even if registered elsewhere).
- ☐ Set up email — at minimum forwarding for `hello@` / `support@`
  (free with Cloudflare Email Routing or Porkbun), or Google Workspace later.
- ☐ Add SPF/DKIM/DMARC once email is live.

## Social handles (grab `matchwright`, fall back to `getmatchwright`)
- ☐ GitHub org `matchwright` (probed free on 2026-06-16)
- ☐ X / Twitter
- ☐ LinkedIn company page
- ☐ Instagram
- ☐ Bluesky
- ☐ Reddit (`r/matchwright` if community planned)
- ☐ YouTube (if video planned)

## Trademark (not legal advice — confirm with a TM attorney)
- ☐ Search **USPTO** (tmsearch.uspto.gov) and **CIPO** (Canada) for "matchwright".
  Nothing surfaced in casual searches, but do an authoritative check.
- ☐ Decide on classes if filing: **9** (software), **42** (SaaS/PaaS), and
  consider **35** (employment/recruitment services) — note class 35 is crowded
  with HR-adjacent players (e.g. the "Aptly" cluster), so vet carefully.
- ☐ Consider filing once revenue/traction justifies the cost.

## Asset exports (from `assets/logo.svg`)
- ☐ `favicon.ico` + `favicon.svg`
- ☐ PNG app icons: 512, 192, 180 (Apple touch), 32, 16
- ☐ Social avatar (square, 400×400+) and banner/OG image (1200×630)
- ☐ Monochrome / single-colour version (for stamps, dark UIs)
- ☐ Light- and dark-background variants
- ☐ Wire favicon + OG tags into the web app (`web/`)

## Brand basics (lightweight)
- ☐ One-line tagline (e.g. "Finds your roles, tailors your applications.")
- ☐ Voice/tone note (playful, goose-friendly — "honk!")
- ☐ Typography choice for marketing (the logo wordmark uses a bold sans).
- ☐ Mascot usage notes (do/don't) if others will use the assets.

## Codebase (optional, larger follow-up)
The user-facing name is rebranded (web/TUI titles, `MatchwrightApp`, READMEs).
Internal identifiers were intentionally left as-is. A future pass could rename:
- ☐ Packages/console scripts → `matchwright-*` (`job-tui`, `job-web`, `harness-db`)
- ☐ Env vars (`HARNESS_DB`, `JOB_DATA_ROOT`) — high blast radius (DB, Docker, CI)
- ☐ `CLAUDE.md` references
This is a deep refactor (imports, entry points, Docker, CI) — scope separately.

## Registrar notes
See the recommendation in the launch discussion; short version:
- **Cheapest renewals / long term:** **Cloudflare Registrar** (at-cost, no
  markup, free WHOIS privacy) — but you must use Cloudflare DNS and register
  most TLDs by transfer-in rather than fresh.
- **Cheapest + easiest to register fresh (incl. `.app`/`.io`):** **Porkbun**
  (low first-year + honest renewals, free WHOIS privacy, good UI).
- **Also fine:** Namecheap (promo-driven). **Avoid** GoDaddy for holdings
  (upsells, higher renewals) — fine only for its backorder/broker services.
