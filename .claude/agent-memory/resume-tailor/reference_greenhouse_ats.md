---
name: greenhouse-ats-access
description: How to fetch full job descriptions from Greenhouse-hosted job board URLs
metadata:
  type: reference
---

Greenhouse job board pages (e.g., `job-boards.greenhouse.io/<company>/jobs/<id>`) embed the full job description inside a JSON blob in the HTML — typically reachable by searching for `"content":"..."` in the curled page. The content is HTML-escaped (unicode `<` for `<`) and HTML-entity-encoded; unescape both to read plaintext. Title is in an `<h1 class="section-header...">` tag.

**Why:** Many companies (Babylist, others) host postings on Greenhouse; the HTML page is hydrated client-side, so simple text scraping misses the body. The JSON content blob is the reliable source.

**How to apply:** Use curl with a browser User-Agent to fetch the page, then parse out the `"content":"..."` field with a regex, run `html.unescape` twice (once for unicode escapes, once for entities), then strip tags.

Related: [[ashby-api-access]], [[rippling-ats-access]]
