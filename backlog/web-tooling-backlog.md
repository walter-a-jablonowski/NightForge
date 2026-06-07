# Web tooling — backlog

Deferred web search/fetch enhancements. v1 keeps web tooling deliberately simple (tavily search + jina fetch; etiquette rules in `web.md`) — most of these are later additions the agent can build itself in dev mode.


## Token-saving page filter

A **pre-filter tool** that trims fetched pages before they reach the model — strip boilerplate/nav, keep the relevant spans — to save tokens on large pages (only if it measurably helps). It composes existing capabilities (no new reach), so it's an in-scope agent-built tool, not a frontier change.

*Open question: does a filter pay for itself versus just fetching less / better extraction at the backend?*


## Crawler rules intentionally kept out of v1

v1 fetches URLs handed back by search backends — no discovery walk, no persistent URL store — so several etiquette rules don't yet apply. They're documented in `web.md` for when the agent maintains its own URL index:

- `sitemap.xml` discovery, `410 Gone` handling, HTTP caching (`ETag` / `Last-Modified` / `304` / `Cache-Control`), canonical URLs (`<link rel="canonical">`).

These unlock once the agent builds a URL index (queue + visited dates + dedup) — see [`agent-self-added-features.md`](./agent-self-added-features.md).


## Not fetch-time rules (operator responsibility)

- **Terms of Service** — intentionally dropped (content/legal judgement, plus a crawling-cost concern), per `web.md`.
- **PII / personal data (GDPR)** — same shape: content/legal judgement, not a fetch-time rule; remains the operator's responsibility (`web.md`).
