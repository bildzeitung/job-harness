---
name: Rippling ATS Job Posting Access
description: Rippling-hosted job pages (ats.rippling.com) embed the full job description in __NEXT_DATA__ JSON under props.pageProps.apiData.jobPost.description.role
type: reference
---

Rippling ATS job pages expose the full job description inside a `<script id="__NEXT_DATA__" type="application/json">` block.

**How to apply:** To pull a full Rippling job description programmatically:
1. `curl -sL <job-url> -A "Mozilla/5.0 ..."`
2. Extract the `__NEXT_DATA__` JSON
3. Walk to `props.pageProps.apiData.jobPost.description.role` (and `.company` for the company blurb)
4. Strip the embedded HTML to recover the clean text — paragraphs/bullets are wrapped in `<p>`/`<li>`

The og:description meta tag only contains the first ~200 characters and is not enough for tailoring.
