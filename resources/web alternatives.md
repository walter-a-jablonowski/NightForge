
2605 all from overview with LLM suggestions

#### Web tool alternatives (review — added 2026-05-30)

Reminder of the v1 shape: two tool *interfaces* (`web_search`, `web_fetch`), each with swappable *backends*. The list below is candidate backends, not new tools. Filter = free / low-cost, generous free tier, **no credit card to start**.

**Search backends — recommended (free, no CC)**

- **Tavily** — built for agents, ~1,000 free credits/mo, no CC. Already the default. Keep as primary.
- **Exa** — neural/semantic search, free starter credit, no CC. You have a key. Good for "find me things like X" and research; also does `/contents` extraction. Keep as secondary.
- **Serper.dev** — Google SERP via API, free credits to start (no CC), then very cheap (~$0.30/1k). Best drop-in if you want plain Google-quality results without Brave's CC wall.
- **SearXNG** (self-host) — open-source meta-search, aggregates many engines, no key, zero cost. Good zero-dependency fallback if you can run it; results quality varies.
- **DuckDuckGo** (keyless) — no signup, but rate-limited and weaker for deep web results. Fine as a free no-key *fallback*, not a primary.

**Search backends — evaluate**

- **Linkup** (in your list) — EU AI-search API with a free tier; worth a quick trial vs Tavily.
- **Google Programmable Search / Custom Search JSON** — 100 queries/day free, no CC, but capped and setup-heavy. Only if you want Google specifically and free.
- **Marginalia / Mojeek** — independent indexes, good for non-SEO/text content; Marginalia has a free non-commercial API. Niche, not a primary.

**Search — avoid / drop from the list (not API backends for this agent)**

- **Brave API** (in list) — now requires a credit card (your blocker). Drop as default; keep only if you later add a card.
- **Bing Web Search API** — being retired by Microsoft; don't build on it.
- **Sakana Marlin, Perplexity, Gemini Deep R, OpenAI Deep R, MS Research, GPT Researcher, Perplexica, explorer.globe** (all in list) — these are deep-research *agents/products*, not search backends. They overlap with what NightForge itself does; wiring them in would be paying another agent to do our job. Skip.
- **Google AI Studio** (in list) — LLM playground, not a search API. Skip.
- **Cowork "Enterprise Search" plugin** (in list) — a Claude plugin, not a programmatic backend for this runtime. Skip.
- **Serp** (in list) — flagged "only with phone" (phone verification); friction, and Serper covers the same need cleaner.

**Fetch / extract backends — recommended (free, no CC)**

- **Jina Reader** (`r.jina.ai`) — prepend the URL, get clean Markdown. Generous free tier, keyless mode works too. Already in use. Keep as primary.
- **Trafilatura** — open-source local extractor (HTML→clean text/Markdown). Zero cost, no network beyond the fetch itself, no key. Best default for a read-only GET fetcher; already named as a backend in app-concept.md.
- **Firecrawl** (in list) — 500 free credits/mo, no CC, great Markdown + main-content extraction for messy pages. Keep for the hard pages Trafilatura/Jina choke on.
- **Crawl4AI** (in list) — open-source, local, strong Firecrawl rival; can pre-filter page content before it hits the model (token savings). Good zero-cost option.
- **MS MarkItDown** (in list) — local HTML→Markdown converter; cheap complement to a raw fetch.

**Fetch — defer / skip for v1**

- **Scrapfly, Apify, Bright Data, ScrapeGraphAI** (in list, "Paid") — proxy/anti-bot scraping for hard or gated sites; overkill for v1's read-only GET/HEAD fetch. Park as "add if we hit JS-heavy/blocked sites."
- **Prospeo** (in list) — email-finding tool, not relevant to research fetching. Drop.
- **Browserbase, agent-browser, OpenBrowser MCP, Browser-use, nextbrowser** (in list) — browser *automation*; v1 fetch is non-interactive read-only (no form-submit/login by design). Out of scope now; revisit only if we need rendered-JS pages.

**Net suggestion**

- Search: **Tavily (primary) + Exa (secondary)**, add **Serper.dev** as the no-CC Google option to replace Brave.
- Fetch: **Jina + Trafilatura** as defaults, **Firecrawl** for the messy/blocked pages.
- Everything else above is either a research-agent product (skip), needs a credit card (skip), or is paid scraping/browser automation (defer). Most of the "Search" half of `search.md` is products, not backends — that's the main cleanup.
