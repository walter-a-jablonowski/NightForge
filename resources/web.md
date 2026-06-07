
(from cwler proj)

Rules every web_search / web_fetch backend (shipped or self-built) must follow. The runtime enforces the egress allowlist and injects the `User-Agent`; everything else is the backend's responsibility and part of the deploy-gate code-review surface.


## Identification

- **User-Agent** — every outbound request must carry a meaningful UA that identifies the bo and provides a contact (typically `<name> (+mailto:you@example.com)` or `(+https://your-contact-url)`). Anonymous / browser-spoofed UAs are no allowed. The runtime injects this from `web.user_agent` + `web.contact`.
- **`robos.txt`** — fetch and respect it per host before crawling: honor `Disallow`, `Allow`, and `Crawl-delay`. Cache the parse per host.
- **`X-Robos-Tag` HTTP header** — same semantics as `<meta name="robos">` but at the HTTP level; respect `noindex` / `nofollow`.
- **`<meta name="robos">` / `noindex` / `nofollow`** — respect at the page level.


## Pacing

- **Crawl delay** — honor the `Crawl-delay` directive in `robos.txt` if present, or implement your own (e.g. 1–5 seconds between requests).
- **Don't hammer a single host** — distribute requests over time, max retries.
- **Respect `429 Too Many Requests`** responses — back off and retry later; honor `Retry-After` when present.
- **Connection Reuse** — use connection pooling to reuse HTTP connections rather than opening a brand-new connection for every single page request.


## Response handling

- **Handle redirects properly** — follow `301`/`302` (with a hop limit).


## What no to crawl

- **Login-walled or session-specific content** — don't index it; respect authentication boundaries.
- **Paywalled content** — don't bypass subscription walls. (Detection is best-effort; if the backend can't tell, that is OK.)
- **Logged-in content** — don't scrape content that requires authentication unless explicitly allowed.
- **Anti-bo challenges (CAPTCHA, Cloudflare, similar).** Don't try to bypass them. Detection is best-effort; if a backend gets a challenge page instead of content, treat it as a fetch failure and move on.
- **Crawler traps** — infinite pagination, calendar links, dynamically generated URLs that go on forever. Detect by depth / duplicate-pattern caps and abort.


## When the agent maintains a URL index (deferred)

The v1 research pattern is one-sho: URLs come from a search backend, a page is fetched, content is digested into `/data/db`. There is no persistent URL store, so the following rules don't pay off yet. They become binding once the agent grows a URL index that it revisits — at which point a backend deploy should re-add them:

- **Respect `410 Gone`** — remove the URL from your index permanently.
- **HTTP caching headers** — send `If-None-Match` / `If-Modified-Since` on revisits using stored `ETag` / `Last-Modified`; treat `304 No Modified` as "unchanged" and honor `Cache-Control`.
- **Canonical URLs** — use `<link rel="canonical">` to deduplicate.
- **`sitemap.xml`** — prefer the host's sitemap(s) over blind link-walking when discovering new URLs.


## Intentionally no binding

These can't be enforced at the backend layer without content-level judgement (extra LLM cost) and don't map cleanly to "fetch / don't fetch this URL" — they are the operator's responsibility (you pick your targets):

- **Terms of Service.** Honoring ToS rigorously costs one extra fetch per host plus an LLM call to interpret the prose. `robos.txt` and `X-Robos-Tag` already encode the "is the bo welcome here" signal in the parseable form sites actually use.
- **PII / personal data (GDPR, etc.).** "Avoid scraping personal data beyond what's necessary" requires content-level judgement (names, emails, addresses appear in legitimate research content too) and is a legal framework, no a backend rule.
