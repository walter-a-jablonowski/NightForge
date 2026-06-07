
*Python edition of `idea.md`. The design is identical — only the language-specific parts differ: file extensions (`.py`), the dependency model (pip + PyPI + a virtualenv), and concrete Python tooling named where the base doc says "depends on language."*

I am making an AI Agent that doesn't only self-improve but also makes most of its implementation itself.

Starting with a minimal agent implementation, the agent first runs in "dev mode". While in dev mode its first task is to fill in missing features and improve its own implementation (it edits its own code).

**dev-config.yml**

```yml
mode: dev                # dev | production

llm:                     # initial LLM for dev mode; API keys in .env
  provider: openrouter   # openrouter (default) | ollama | gemini | ...
  model: anthropic/claude-sonnet-4   # provider-specific model string
  # provider-specific extras go here, e.g.:
  # base_url: http://localhost:11434   # for ollama / self-hosted

limits:
  max_steps: 50          # hard step cap per run
  max_cost: 5.0          # hard $ cap per run
  max_cost_sum: 50.0     # cumulative $ cap across deploys (whole session)
  max_deploys: 30        # cap on self-deploy iterations per session

tools:
  web_search: tavily     # tavily (primary) | exa (secondary) | serper (Google, no credit card)
  web_fetch:  jina       # jina | firecrawl | trafilatura (local)

web:                     # outbound HTTP etiquette + self-build switch
  user_agent: "NightForge"             # name shown to remote hosts
  contact:    "mailto:you@example.com" # contact method; runtime composes the UA as "<user_agent> (+<contact>)"
  allow_self_built_backends: true      # may the agent add & use new /src/tools/search & /fetch backends?

systemPrompt: |          # agent's role, reasoning format, finishing criterion
  ...

devInstructions: |       # optional: specialization / focus areas for dev mode
  ...
```

For dev mode it draws on state-of-the-art knowledge about how to build a good AI agent from three layers: (1) the durable engineering *principles* in its dev system prompt (the kind of guidance in this document), which age slowly; (2) current best practice it gathers at runtime via `web_search` / `web_fetch`, treated as **untrusted** (see Security) — it may *inform* design, but anything it produces is still code that must pass the deploy gate, sandbox, and audit log before it can run; and (3) `devInstructions`, the trusted channel where the user points it at specific sources or a specialization.


### Design principles

- **Implementation:** The initial agent implementation is intentionally minimalistic. It includes only the most needed features and files.
- **Security:** The agent runs inside a runtime-enforced sandbox (capability-based tool registry, scoped filesystem, network egress allowlist). We don't delegate security to the agent.
- **Readability:** We keep the implementation structured but minimal so humans can read it easily.


### Directory structure

```
/agent
  dev-config.yml         # dev-mode config (agent must never edit)
  user-config.yml        # user config (agent must never edit)
  AGENT.md               # production system prompt (agent must never edit)
  .env                   # API keys (LLM, web tools); never committed
  agent.log              # structured JSONL audit trail; survives /dist swaps
  .venv/                 # Python virtualenv; the `install` target, runtime-managed (outside the agent's fs_write scope)

  /dist                  # active agent code (swapped on deploy)
    config.yml           # optional, written by the agent itself
    production-ready     # empty file, set by the agent when done
  /dist.prev             # previous /dist, kept for one-step rollback

  /src                   # next version of itself; the only writable area
    registry.py          # central name→adapter registry (tools, providers, backends); off-limits under improve:tools
    pyproject.toml       # pinned dependency manifest; updated by `install`, rides the deploy
    /providers           # one file per LLM provider (openrouter.py, ollama.py, ...)
    /tools               # agent tool backends (the model calls these)
      /search            #   one file per web_search backend (tavily.py, exa.py, ...)
      /fetch             #   one file per web_fetch  backend (jina.py, firecrawl.py, ...)
    /tests               # agent-written tests (pytest); run by the deploy gate

  /data                  # persistent memory; written directly, survives deploys
    /db                  # Agent's long term memory, markdown
      index.md           # hierarchical table of contents
      roadmap.md         # dev-mode progress against the systemPrompt's target checklist
      <topic>.md         # one file per topic / source

  /tools                 # deploy tool + smoke floor + capability floor (agent can't edit this)
  /.git                  # optional: enables git-based rollback + diff review
```

**Initial state.** At first launch the seed populates **both** `/dist` (the code the supervisor actually runs) and `/src` (an identical working copy — the only area the agent edits). The agent improves `/src` and deploys it over `/dist`, so the first deploy ships an *improved* seed, never an empty tree; `/src` is never bare. `/dist.prev` and `/data/db` start empty (the latter with just an `index.md` stub).


### Basic agent implementation

Rule of thumb: if a feature isn't required to (a) reason, (b) call a tool safely, (c) read/write its own files, or (d) stop — leave it out. The agent adds the rest itself during dev mode.

**user-config.yml**

```yml
improve: tools           # off | tools | full  (production-only)
                         #   off   = no self-modification
                         #   tools = repair existing tool/adapter files only (default)
                         #   full  = unrestricted edits inside /src

llm:                     # default LLM(s); API keys in .env
  provider: openrouter
  model: anthropic/claude-sonnet-4

limits:
  max_steps: 50
  max_cost: 5.0
  max_cost_sum: 50.0
  max_deploys: 30

web:                     # outbound HTTP etiquette (same shape as dev-config)
  user_agent: "NightForge"
  contact:    "mailto:you@example.com"
  # adding new backends in production is governed by `improve` (full only), not a flag

# systemPrompt lives in AGENT.md (production system prompt)

prodInstructions: |      # optional self-improvement instructions for production
  ...
```

**AGENT.md** — the production system prompt (agent role, reasoning format, finishing criterion; may contain the user's goal(s)) lives here as markdown instead of inline YAML — long prompts are easier to edit and diff this way. User-owned: the agent must never edit it (it sits outside the `/src` + `/data` write scope), and the runtime loads it as the `system` message in production. Dev mode keeps its `systemPrompt` inline in `dev-config.yml`.

**config.yml** — the agent's own settings file, authored as `/src/config.yml`, so it lands in `/dist` on the next swap (config changes are deploy-gated) and applies in production (dev mode is driven by `dev-config.yml`). It is **not** an override channel for the operator's governance knobs: `llm`, `limits`, `improve`, and `web` are owned by the operator's config alone (`dev-config.yml` in dev, `user-config.yml` in production) — the runtime takes them only from the operator's file and ignores them if they appear in `config.yml`. So the agent can't switch its own model, lift its own cost / deploy ceilings, widen its own `improve` level, or change the outbound identity it presents. `config.yml` is instead where the agent keeps **its own new settings** — flags for features it builds for itself:

```yml
# Written by the agent as /src/config.yml; active after the next deploy.
# llm / limits / improve / web are ignored here — they stay operator-owned.
compaction:
  trigger_tokens: 6000     # agent-added: when its own summarization kicks in
fetch_cache:
  ttl_seconds: 3600        # agent-added: lifetime for a result cache it built
```

**.env** — secrets, never committed. Only the keys for the providers you actually use are required:

```env
OPENROUTER_API_KEY=...   # default LLM provider
TAVILY_API_KEY=...       # default web_search backend (primary)
# OPENAI_API_KEY=...     # only if llm.provider = openai (direct)
# ANTHROPIC_API_KEY=...  # only if llm.provider = anthropic (direct)
# GEMINI_API_KEY=...     # only if llm.provider = gemini
# EXA_API_KEY=...        # only if tools.web_search = exa (secondary)
# SERPER_API_KEY=...     # only if tools.web_search = serper (Google results, no credit card)
# FIRECRAWL_API_KEY=...  # only if tools.web_fetch  = firecrawl
# (ollama, jina, trafilatura need no key)
```


**Agentic loop**

Standard ReAct/tool-calling loop. Parsing and JSON-schema validation are delegated to the LLM SDK's native tool-calling API (the official `openai` / `anthropic` Python SDKs and the like) — no custom parser needed.

```
FUNCTION run_agent(user_goal, tools, limits):
  memory = resume_after_deploy() OR [    # after a deploy-respawn, rebuild from agent.log;
    { role: "system",  content: systemPrompt },   # or: start a fresh session
    { role: "user",    content: user_goal },
  ]
  steps = 0
  cost  = 0
  WHILE steps < limits.max_steps AND cost < limits.max_cost:
    steps += 1
    response = llm.call(memory, tools=tool_specs(tools))   # SDK validates schema;
                                                           # retry/backoff lives in the adapter
    cost += response.cost                                  # accumulate $ for the guard + log

    IF response.tool_calls is empty:
      RETURN response.content OR "done"                    # final answer (guard empty content)

    # `deploy` is terminal: it kills the process mid-loop. Force it to run alone *before*
    # recording the turn, so no sibling call is logged without a tool response — otherwise
    # the respawned agent replays an assistant turn with an unanswered tool_call and the
    # provider API rejects it.
    IF "deploy" IN [ c.name FOR c IN response.tool_calls ]:
      response.tool_calls = [ the deploy call ]            # drop siblings (model can re-issue them)

    memory.append({ role: "assistant", ...response })      # keep thought + (trimmed) tool_calls

    FOR call IN response.tool_calls:
      IF call.name ! IN tools:
        observation = "unknown tool: " + call.name     # corrective, non-fatal
      ELSE:
        TRY:
          observation = execute_tool(call.name, call.params)   # deploy may never return
        CATCH err:
          observation = "tool error: " + str(err)    # fed back, no crash

      memory.append({
        role: "tool",
        tool_call_id: call.id,
        name: call.name,
        content: observation,
      })

  RETURN "stopped: step/cost limit reached"
```

Comments:

- Self-modification happens via the normal tool flow: the agent writes to `/src` (`fs_write`), runs tests (`run_tests`), and calls the `deploy` tool — see Dev mode for the swap-and-respawn details.
- **Resume after deploy:** `deploy` respawns the process, losing in-memory history. Terms: a **run** is one process life (a fresh `run_id` per respawn — see Logging); a **session** spans every run from entering `mode: dev` until `production-ready` (see Run lifecycle). `resume_after_deploy()` rebuilds `memory` from `agent.log` by replaying **the whole session** — every prior `run_id`, not just the last, since each run logs only its own new steps. Each step replays as its thought, tool calls, and full observations (matched to each call by `id`). The respawning `deploy` call has no stored `tool` result (the process died first), so resume synthesizes one (e.g. `"deployed: /src→/dist @ <ref>"`); otherwise the replayed assistant turn carries a `tool_call` with no response and the provider API rejects it. (Durable progress also survives independently of the transcript: the advanced `/src` and the comments in `/data`.)
- **Terminal tools:** `deploy` is the only tool that ends the process, so the loop forces it to run alone; any different batch of tool calls runs in full.
- **Termination guard:** `max_steps` and `max_cost` (token/$ budget) are hard, **per-run** limits — configurable in `dev-config.yml` / `user-config.yml` with conservative defaults. Because each deploy spawns a *fresh* run, these reset on every respawn; so the runtime also enforces a **cumulative** ceiling across a session (`max_cost_sum`, `max_deploys`) — checked before each respawn — so a self-deploying agent can't run indefinitely under per-run caps.


**Runtime ↔ agent interface (frozen)**

The runtime (`/tools`, not agent-editable) and the agent code (`/src`, editable) meet at one small contract the agent must **never change** — it lives in `/src` but is off-limits even under `improve: full`, and the smoke floor verifies it before any swap:

- **Entrypoint** — a fixed function the runtime starts and respawns, e.g. `main(config, llm=None)`. It builds the run and drives the loop; the loop calls `resume_after_deploy()` when continuing after a respawn.
- **Config object** — the runtime parses config (merged `dev-config.yml` / `user-config.yml` + `config.yml`, taking `llm` / `limits` / `improve` / `web` only from the operator's file) and passes it in; the agent doesn't re-read the config files itself.
- **LLM injection** — the loop resolves its LLM through the passed-in client, not a hardcoded import, so the floor can inject a **stub** (no network) for its one-step liveness check while real runs get the configured adapter.
- **Secret injection** — adapters never read `.env` or the process environment themselves. The runtime loads secrets and hands each adapter only the key(s) it needs: the configured LLM client arrives pre-built (above), and web backends get their key through the same channel. A self-built backend requests a **named** secret by the convention `<BACKEND>_API_KEY`; supplying a brand-new credential is a human `.env` step (capability frontier). Critically, the runtime **scrubs secrets from the environment** before the agent's code runs, so the `fs_read` `.env` exclusion can't be sidestepped via `os.environ`.

The agent may rewrite everything *behind* this interface (loop body, providers, tools, memory layout). If a deploy changes the signature anyway, the floor fails it — an un-bootable agent never reaches a swap.


**Run lifecycle (supervisor)**

`run_agent` handles *one* run; the runtime wraps it in a supervisor so work continues across runs:

```
FUNCTION main(config, llm=None):       # the frozen entrypoint
  WHILE not done(config):
    run_agent(...)                     # one run (resumes from agent.log if just respawned)
    IF config.mode == production:                        break   # batch: serve the goal(s) once, exit
    IF /dist/production-ready exists:                    break   # dev: agent signalled ready
    IF cumulative caps hit (max_cost_sum / max_deploys): break
  # a `deploy` inside run_agent replaces the process; the new process
  # re-enters main() and the next run_agent resumes the chain.
```

- **Dev mode** is multi-run: a run ending on a final answer or a per-run step/cost stop is *not* the end — the supervisor starts the next run until the agent sets `production-ready` or a cumulative cap trips.
- **Deploy** is the cross-process case: it ends the process; the respawned `main()` resumes the chain.
- **Production** runs the same way under `user-config.yml`, but as a **batch**: the supervisor serves the goal(s) from `AGENT.md`, and `done(config)` returns true once they're served (a final answer with no pending tool calls), so the process **exits** rather than re-running a static goal. Accepting new tasks at runtime (a long-running service with an input channel) is deferred — see `/backlog/production-service-mode.md`.
- **Cumulative caps survive restarts** — the running totals (session `$` and deploy count) are derived from `agent.log`, which the agent can't write, so a restart can't reset them. A *session* runs from entering `mode: dev` until `production-ready` is set (or the user resets); promoting to production clears the dev counters.
- A cumulative-cap stop or a fatal error **halts for the user** — it doesn't silently retry.


**LLM provider**

`llm.call(...)` in the loop is a thin dispatch over a **provider adapter**. One file per provider lives in `/src/providers/<name>.py`; the registry maps `llm.provider: <name>` to its adapter. v1 ships with **openrouter** only — since OpenRouter itself proxies most major models, this already covers most users. (The shipped `openrouter.py` wraps the official `openai` Python SDK pointed at OpenRouter's OpenAI-compatible endpoint; a direct Anthropic/Gemini adapter would wrap that provider's Python SDK, and a self-built one can fall back to raw `httpx`.)

Every adapter implements the same minimal interface:

```
FUNCTION call(messages, tools, model, **extras) -> {
  content: str | null,             # assistant text (may be empty when tool calls exist)
  tool_calls: [ {id, name, params} ],
  tokens:    { in: int, out: int },
  cost:      float,                # in USD; 0 for local/self-hosted
}
```

The adapter's job is to translate between this normalized shape and the provider's native format (especially the tool-call schema, which differs between OpenAI, Anthropic, Gemini, ...). Everything above this layer — the loop, memory, logging — only sees the normalized shape.

Two more pieces the runtime needs from the adapter, both for the memory **safety clip** (see Memory): a **`context_window`** (the model's max input tokens) and a **`count_tokens(messages)`** estimate, so the runtime can tell *before* a call whether the next request would overflow. For OpenRouter these come from its model metadata; a local/self-hosted provider can hardcode or query them.

Adding a new provider = one new file in `/src/providers/` (~50 lines) exposing `call(...)`, plus one line in the central `registry` mapping `<name>` → that adapter. Registration lives in that one file, not scattered self-registration in each adapter. No different code changes.


**Web backends**

Same pattern as LLM providers, applied to the two web tools. `tools.web_search` and `tools.web_fetch` each name a backend; one file per backend lives in `/src/tools/search/<name>.py` and `/src/tools/fetch/<name>.py`. v1 ships with **tavily** (search) and **jina** (fetch) only. (An adapter wraps the backend's Python client where one exists — e.g. `tavily-python`, `exa-py` — or calls the HTTP API with `httpx`; `jina` is just a URL prefix and the local `trafilatura` fetcher needs no API client beyond the fetch itself.)

Minimal interfaces:

```
FUNCTION search(query, max_results=5, **extras) -> [
  { title: str, url: str, snippet: str, score: float | null }
]

FUNCTION fetch(url, **extras) -> {
  content:      str,            # extracted text, ideally markdown
  content_type: str,            # "markdown" | "html" | "text"
  status:       int,
}
```

Adapters translate between these shapes and the backend's native API. Adding a backend = one new file (~30 lines) + one line in the central `registry`. No different code changes.

**Self-built backends in dev mode.** The agent may write entirely new search / fetch backends in `/src/tools/search/` and `/src/tools/fetch/` and wire them into the registry (replacing the existing dispatch or adding parallel tools) — a useful speedup when the shipped backends are slow or rate-limited for the agent's research patterns. Setting `web.allow_self_built_backends: false` in `dev-config.yml` locks the registry to the shipped backend files only; the smoke floor enforces it at deploy against a shipped-backend manifest baked into `/tools` (non-editable), failing the swap on any added file. In production the same lock is governed by `improve` (`tools` allows repairs to existing backend files, `full` allows new ones).

**Etiquette (binding on every backend).** Any backend — shipped or self-built — must respect outbound HTTP etiquette: identify itself via the runtime-injected `User-Agent` (composed from `web.user_agent` + `web.contact`), honor `robots.txt` (incl. `Crawl-delay`), `X-Robots-Tag`, and `<meta name="robots">`; back off on `429` (honor `Retry-After`); follow redirects sanely; use conditional requests on revisit (`ETag` / `Last-Modified`); prefer `sitemap.xml` over blind link-walking; and skip login-walled / paywalled / CAPTCHA-gated content and crawler traps. The full list lives in `web.md` and is part of the code-review surface for every backend that lands via deploy. The runtime independently fails any outbound request that breaches the egress scope — an off-allowlist host, or a mutating method (`POST` / `PUT` / …) on the open web — regardless of what a backend does (see Security → Network egress).


**Memory**

Two distinct stores, deliberately simple:

1. **Session memory** — the `memory` list above: typed turns (`system` / `user` / `assistant` / `tool`) matching the LLM SDK's chat format, each tool call and observation as separate entries. Rich compaction/summarization is the agent's job, but to avoid a dead-end the runtime applies a **safety clip**: when the next request would exceed a safe fraction (e.g. 75%) of the model's context window — measured via the adapter's `count_tokens` and `context_window` (see LLM provider) — it elides the oldest `tool` observations — keeping the `system` message, the `user` goal, and the most recent turns — and leaves a `[older context elided — see agent.log]` text. This guarantees a step can always run, including when `resume_after_deploy()` rebuilds an over-long session from the log, until the agent ships smarter compaction.

2. **Persistent memory** — flat markdown files under `/agent/data/db/` with `index.md` as entry point. Lives outside `/dist` to survive deploys. Initial schema is intentionally bare:

   ```
   /data
     /db
       index.md          # hierarchical table of contents, maintained by the agent
       roadmap.md        # dev-mode progress vs. the systemPrompt target checklist
       <topic>.md        # one file per topic / source
   ```

   Anything richer (time-based index, URL queue, task tracking, ...) is the agent's job.

   `/data` is written **directly** via `fs_write`/`fs_delete` (it is memory, no code) — no deploy needed, and it stays writable in production regardless of `improve`. This is the agent's long-term store from day one: in dev mode it captures the state-of-the-art knowledge it researches on the web. The deploy swap never touches `/data` — it is preserved as-is and **never auto-migrated**.

   **Changing the memory format.** The agent migrates its own memory with the tools it already has — no runtime orchestration. If it decides on a better layout it rewrites the files under `/data` itself (`fs_write` / `fs_delete`) *before* deploying code that expects the new shape. Migrations should be **additive and idempotent** (don't destroy the old fields until the new code reads cleanly), which keeps the gap between old code and reshaped data harmless. Atomic, snapshot-paired migration is deliberately left out of v1 — the agent can add it (a snapshot dir + a migration step) once memory grows structured enough to need it; flat markdown doesn't.


**Tool definitions given to the model**

A small built-in registry. Each tool has a name, description, and JSON-schema for its parameters; the list is passed to `llm.call(...)` as the SDK's `tools` argument. The model can only pick from this set.

Initial tools (dev mode, see Security section for the runtime-enforced scope):

- `web_search`, `web_fetch` — read-only web access; results tagged untrusted
- `fs_read`, `fs_list` — read inside `/agent` except `.env`, the config files, and the runtime's own files
- `fs_write`, `fs_delete` — write inside `/agent/src` (code) and `/agent/data` (memory), plus the file `/agent/dist/production-ready`
- `run_tests` — run the agent's `/src/tests` suite (pytest) against `/agent/src` (sandboxed subprocess); the deploy gate runs it automatically too
- `install` — install a package from PyPI into the agent's virtualenv via pip (a bounded capability, not a shell). Default-allow for ordinary PyPI packages; replacing the installer/package manager itself, system-level installs, and any index other than the configured PyPI need human approval (see Security). The dependency set is pinned in `pyproject.toml` and recorded and validated through the deploy gate.
- `deploy` — invoke the deploy tool: run the gate, swap `/src` → `/dist`, respawn. The swap never touches `/data` (memory migration, if any, is something the agent does directly beforehand — see Memory).

The agent may add new tools by adding the implementation under `/src` and an entry in the central `registry` file (`/src/registry.py`), then redeploying. Until they pass the next deploy and the runtime's sandbox check, they aren't callable.


**Validation of tool calls**

Done by the SDK against the JSON schemas above. Anything the SDK rejects, or any unknown tool name, comes back to the model as a `tool` message with an error string — never crashes the loop.


**Error handling**

Two layers.

*Loop-level* errors funnel back into `memory` as `tool` observations so the model can recover:

- **Schema / unknown tool** — handled in the loop (see pseudocode).
- **Tool execution failure** — caught around `execute_tool`, error message returned. Resource-limit hits (per-write size cap, disk quota) surface here too.
- **LLM / network failure** — retry with exponential backoff up to N times, then abort the run with a clear error.

*Deploy-layer* errors happen in the deploy tool, outside any single run, and are handled by the runtime (not fed to the model) — they can otherwise leave the system with no running agent or corrupted memory:

- **Failed swap / respawn** — the gate passed but the fresh agent doesn't come up healthy (a bad import the floor missed, a startup crash, a disk error mid-swap). The deploy tool auto-restores `/dist.prev`, respawns the previous version, and logs the failure.
- **Startup config error** — a malformed `dev-config.yml` / `user-config.yml`, or a provider / search / fetch name with no adapter, is caught at startup (the floor only guards deploys, not first launch): fail fast with a clear message instead of crashing mid-loop.


**Explicitly out of scope for v1** — the agent adds these if it sees the need:

- Context-window compaction / summarization (beyond the runtime safety clip)
- Caching of repeated tool results
- Cost / latency telemetry beyond the simple budget counter used for the termination guard
- Multi-agent orchestration, sub-agents, planners


### Dev mode

The agent self-modifies by writing to `/src`, calling `run_tests`, then calling the `deploy` tool. The deploy tool kills the agent process, swaps `/src` → `/dist` (keeping the previous as `/dist.prev`), and starts a fresh agent. The new agent picks up where the old one left off. The swap never touches `/data` — memory is migrated by the agent directly, ahead of the deploy, if a format change calls for it (see Memory).

**The dev-mode target.** "Improve until state-of-the-art" needs a destination, or the agent thrashes — endlessly rewriting the loop while never building the features that matter. The destination is a **capability checklist in the dev `systemPrompt`** (operator-owned, the agent can't edit it): the target features it should grow into — e.g. context compaction, result caching, a richer memory index, the specific providers/backends it needs. The capability floor is only a *regression* gate (don't get worse); this checklist supplies the *forward* gradient — what "better" means. The agent tracks its own progress against the checklist in `/data/db/roadmap.md`, a working file it maintains (distinct from the immutable target in the prompt). `devInstructions` can extend or specialize the checklist for a given build.

**The deploy gate.** Before swapping, the deploy tool runs three test layers and aborts the swap — leaving `/dist` and the running agent untouched — if any fails, returning the output as the tool observation so the agent can fix and retry:

- **Smoke floor** — a fixed liveness check that lives in `/tools` (the deploy logic), *outside* `/src`, so the agent can't weaken or delete it. It asserts that the new `/src` imports with no errors, that config parses and the configured provider / search / fetch names resolve to adapter files that exist, that the tool registry builds with valid schemas, that the new adapters load under the sandbox (and the resolved provider adapter exposes `context_window` + `count_tokens`, which the memory safety clip relies on), and that one loop step runs end-to-end against a stubbed LLM (no network). This guarantees a deploy never respawns an agent that can't even startup. Beyond liveness, when `web.allow_self_built_backends` is off (see Web backends) the floor enforces the backend lock — comparing the deployed backends against the shipped manifest and rejecting any addition. The production `improve: tools` scope needs no such check: its restriction is structural (the registry sits outside the writable dirs — see Production).
- **Agent tests** — the agent's own suite under `/src/tests`, which it writes and expands as it adds features; these cover behaviour and correctness, instead of just liveness. Deterministic unit tests are the baseline; the agent is expected to grow this layer as it matures — that growth is its job, not the seed's.
- **Capability floor** — a tiny fixed set of *end-to-end* task cases in `/tools` (non-editable, like the smoke floor), checking **behaviour**, not liveness. v1 ships just **2–3 objective cases** with deterministic checks (e.g. fetch a known page and extract a specific value; return a search hit whose URL contains an expected string) — **no LLM judge**. It runs the candidate `/src` against each goal and acts as a **regression gate**: the candidate must score **≥ the currently deployed `/dist`** (the runtime records each deploy's score in that deploy's `agent.log` step record — see Logging → `deploy` — which the agent can't write, so the bar can't be gamed). On the **first deploy** there is no prior `/dist` score to beat; the candidate must instead clear a fixed minimum on the objective cases (the **cold-start bar**), after which every later deploy is judged against the last. To avoid crying wolf during rapid iteration, the comparison allows a **small tolerance** and **re-runs a single failing case once** before blocking — a tiny suite shouldn't let one flaky fetch veto an otherwise-good deploy. This catches the one thing the agent's own tests can't — a deploy that boots *and* passes its self-written tests yet is actually *worse* at real tasks. Bounded by design: a handful of cases, only at deploy, cached by `/src` hash. Its end-to-end runs make real LLM calls; that spend is **runtime overhead** — recorded as a `floor_cost` (on the deploy step record, or on the failed-deploy log entry when the gate aborts the swap) and **not** charged against the agent's `max_cost` / `max_cost_sum` (those bound the agent's own runs, not the gate that judges them). Richer behavioural evals (LLM-as-judge with a fixed rubric, larger and held-out suites) are deferred — see `/backlog/capability-floor.md`.

The `run_tests` tool runs the agent-test layer on demand, so the agent can check its work mid-iteration; the gate runs all three layers automatically at deploy. The order across a full deploy is: gate (smoke floor → agent tests → capability floor, against `/src`) → swap → respawn.

**No human approval gate.** A self-implementing agent that pauses for approval on every change defeats the point. Safety is provided instead by:

- the deploy gate — smoke floor + agent tests + capability floor — before each deploy,
- the hard `max_steps` / `max_cost` limits per run,
- the sandboxed write scope (see Security),
- structured observability + cheap rollback (see Logging).

**Rollback.** The deploy tool keeps the previous `/dist` as `/dist.prev` so a bad deploy can be reverted in one step. For deeper history the deploy tool uses git: if `/agent` isn't already a repo it **auto-initializes one** (when the `git` binary is available) and commits every swap with the iteration's log id — so multi-step rollback and diff review work without the user ever having to use git; absent git, rollback is the single `/dist.prev` step. Rollback reverts code only; `/data` is the agent's live memory and is never snapshotted per swap, so a revert leaves memory as-is — additive, idempotent format changes (see Memory) keep old code able to read it.


### Logging

The runtime writes structured JSONL to `agent.log` in dev and production. Each run starts with a **header record**, then one **step record** per iteration.

Header (once per run):

```json
{ "ts": "...", "run_id": "r-42", "kind": "header",
  "model": "...", "limits": {"max_steps": 50, "max_cost": 5.0},
  "system_prompt_hash": "sha256:...", "tools": ["web_search", "fs_write", ...] }
```

Step (per iteration):

```json
{ "ts": "...", "run_id": "r-42", "step": 12,
  "thought": "I need to add a retry around llm.call ...",
  "calls": [
    { "id": "call_1", "tool": "fs_write", "params": {...},
      "result": "wrote /src/providers/openrouter.py (1.8 KB)", "ok": true }
  ],
  "tokens": {"in": 1820, "out": 94}, "cost": 0.003,
  "deploy": null }
```

Field rationale:

- `run_id` — groups steps from one invocation; each deploy spawns a fresh run, so you see the chain.
- `thought` — the assistant message's text *before* the tool call. Captures the LLM's reasoning. Without this you can audit actions but no decisions.
- `calls` — the turn's tool calls **in order**, each with its `id`, `tool`, `params`, the **full** observation (`result` — the exact `tool`-message content), and an `ok` flag. A single turn may carry several (the loop runs them all), so this is a *list*, not one field — that is what makes `agent.log` a faithful, replayable transcript and what `resume_after_deploy()` reads to rebuild `memory`, matching each `result` back to its call by `id`. Observations past a size cap are elided with a highlighting element (the safety clip applies on replay too).
- `ok` (per call) — explicit success flag so errors are filterable (`jq 'select(.calls[]|.ok==false)'`).
- `tokens` / `cost` — budget and reproducibility.
- `deploy` — on deploy steps, reference to the previous `/dist` snapshot or git commit hash, plus the candidate's **capability-floor score** and **`floor_cost`** (the $ the floor's end-to-end runs spent — runtime overhead, not charged to the agent's budget; see Dev mode → deploy gate). Enables one-step rollback, diff review, and the floor's ≥-comparison.

Model / prompt / tool registry live in the header so step records stay lean. `jq` + `tail -f` are the only viewers needed in v1.

`agent.log` continues into production unchanged — the runtime keeps writing it in all modes. In addition, the agent may write its own enriched/application logs to `/agent/data/logs/`; these are additive, never a replacement.

*Tracing spans, dashboards, metrics, dedicated viewers — out of scope for v1; the agent adds these if it sees the need.*


### Security

**Threat model.** A self-modifying agent that reads the web can be tricked (prompt injection) or can damage its environment. Defense is layered and enforced by the runtime — never left to the agent's "good behavior".

**Capability sandbox.** The agent affects the world only through the tool registry. No shell, no `eval` / `exec`, no direct network, and **no ambient secrets** — the environment is scrubbed and credentials reach adapters only through the runtime's secret injection (see Runtime ↔ agent interface), so `/src` code can't read `.env` out of `os.environ`. New adapters dropped into `/src` are loaded only after passing the same sandbox checks on next deploy.

**Enforcement boundary.** These guarantees are real only at an **OS-level boundary** — the agent's code runs inside an isolated process/container, with the filesystem mounted to scope and *all* outbound traffic forced through the egress allowlist (a proxy or network namespace). This matters because the agent writes and runs its own code: any in-language attempt to "block" shell, network, or `eval`/`exec` is **defense-in-depth, not the boundary** — Python code running with the process's privileges can reach around in-process guards (`ctypes`, `__import__`, C extensions), so isolation has to sit below the language. On Windows this means Docker Desktop / WSL2 (there is no `seccomp` equivalent for a bare process). The seed therefore assumes it is launched inside such a boundary; providing or tightening it is an operator/deployment concern the runtime relies on but the agent cannot grant itself (it sits on the capability frontier below).

**Capability frontier.** The agent freely improves its *implementation* and adds tools that compose existing capabilities, but it can't grant itself *new* capabilities — those are human-extended. New **full-method** egress hosts (beyond the read-only open-web fetch scope below), filesystem scope beyond `/src` + `/data`, system-level access, and off-PyPI-index / system package installs all sit on this frontier: the agent may write code that wants them, but the runtime keeps the gate shut until a human widens it. This is deliberate — an agent that reads untrusted web content must not be able to escalate its own *reach* (e.g. open a write/`POST` channel to an exfiltration host, or widen its filesystem scope) from something it "learned" online. Read-only web fetch is already a granted capability, so it isn't on the frontier.

**Untrusted content.** Results of `web_search` and `web_fetch` are wrapped in `<untrusted source="...">`; the system prompt instructs the model to treat their contents as data, instead of commands. This matters most in dev mode, where the agent researches how to build itself: a poisoned page can sway a design choice but can't escape the sandbox or skip the test gate, and the resulting change is logged and (with git) diff-reviewable for after-the-fact rollback. One residual path remains: when the agent distills untrusted findings into `/data` comments, a later `fs_read` returns them as ordinary memory, *not* `<untrusted>`-wrapped — so a poisoned source can launder an instruction into trusted context one hop later. The same containment (sandbox, gate, egress) still bounds the *effect*; carrying the untrusted flag through `/data` (provenance-tagged memory) is a v2 item — see `/backlog/provenance-tagged-memory.md`.

**Filesystem scope** (runtime-enforced):

- `fs_read`  — `/agent` *except* `.env`, `dev-config.yml`, `user-config.yml`, and the runtime's own files; `agent.log` *is* readable, so the agent can review its own traces for self-reflection
- `fs_write` — `/src` (code) and `/data` (memory), plus the single file `/dist/production-ready`
- `improve` (production) narrows only the **`/src`** portion of `fs_write`: `off` disables `/src` writes, `tools` restricts them to existing files in `/src/providers/` and `/src/tools/`, `full` matches dev mode. Writes to `/data` are memory, no self-modification, and stay available in all modes.

**Network egress allowlist.** Outbound HTTP is scoped by host *and* method:

- **Configured hosts** — the hosts of currently configured providers/backends plus PyPI (e.g. `openrouter.ai`, `api.tavily.com`, `r.jina.ai`, and `pypi.org` / `files.pythonhosted.org`). Full request methods, so a proxy backend may `POST` its query here. Adding a host to this set is a capability-frontier change (human-extended).
- **Open web** — arbitrary hosts, available to `web_fetch` backends only and **read-only**: `GET` / `HEAD` with no request body. This lets a direct fetcher (`trafilatura`) or a self-built fetch backend pull any page, while the runtime rejects mutating methods (`POST` / `PUT` / `PATCH` / `DELETE`) and any body — fetch can *read* a site, never *act* on it (submit a form, log in, post).

Everything else is blocked. Every outbound request also carries the runtime-injected `User-Agent` composed from `web.user_agent` + `web.contact` (see Web backends → Etiquette), so the agent can't anonymize or browser-spoof itself.

**Dependencies.** The agent may install packages to build itself, exposed as a bounded `install` capability (not a shell). Packages come from **PyPI** via **pip**, installed into the agent's **virtualenv** (`/agent/.venv`) so they stay isolated from the system Python. Installs are **default-allow** from PyPI (its hosts — `pypi.org` / `files.pythonhosted.org` — are the egress addition for installs); each is logged, **pins the version into the dependency manifest** (`/src/pyproject.toml`), and rides a **deploy**, so the dependency set is test-gated and reproducible; a rollback reverts the *manifest* (already-installed wheels may linger in the venv, harmlessly — the reverted code simply won't import them). The **restricted set** needs human approval (it crosses the capability frontier): installing or replacing the installer / package manager itself (pip, uv, poetry), system-level / OS-package installs (`apt` / `brew`, or anything needing a compiler / build toolchain beyond a prebuilt wheel), and any index other than the configured PyPI (`--index-url` / `--extra-index-url`, or direct VCS / URL / local-path installs). Packages widen what the agent can *build*, not what its code may *do* — the sandbox still governs that. In production, dependency changes follow `improve` (full only).

**Sandboxed tests.** The smoke floor and the agent's `/src/tests` (pytest) run in a subprocess with the same filesystem + network restrictions.

**Resource limits.** In addition to `max_steps` / `max_cost`: per-write file size cap and sum of disk quota under `/src`.

**Audit trail.** Every tool call + result lands in `agent.log` (see Logging).

**Tools available in dev mode:**

- `web_search`, `web_fetch` — see Web backends; results tagged untrusted
- `fs_read`, `fs_list`, `fs_write`, `fs_delete` — scopes above
- `run_tests` — sandboxed subprocess (pytest)
- `install` — install a dependency from PyPI via pip (bounded; package-manager / system / off-PyPI-index installs need approval — see Security)
- `deploy` — invokes the deploy tool


### Production ready

The agent transitions from dev to production in one of two ways:

1. **User-driven.** The user flips `mode: dev → production` in `dev-config.yml` and restarts. Allowed at any time, including before any dev iterations.
2. **Agent-signalled.** When the agent judges itself ready, it creates the empty file `/dist/production-ready` and shuts down. This **doesn't** flip the mode (the agent can't edit `dev-config.yml`); the user sees production-ready and promotes manually.

The agent considers itself ready when:

- It is confident its implementation reflects current best practice, *and*
- (if set) all `devInstructions` are satisfied.

These are heuristics — the user remains the ultimate decider.


### Production

The same agentic loop runs, but driven by `user-config.yml` instead of `dev-config.yml`. The system prompt (loaded from `AGENT.md`) defines the agent's role and may list one or more goals; the agent works through them under the configured `limits` (per run). Production is **batch**: once the goal(s) are served the supervisor exits — it does not idle for new tasks. A service mode that accepts tasks at runtime (input channel + per-task budgeting) is deferred to `/backlog/production-service-mode.md`.

The `improve` setting controls what self-modification is allowed in production:

- `off` — no `/src` writes, so no self-modification; the agent only serves tasks. (`improve` governs code only — `/data` memory stays writable in all modes.)
- `tools` *(default)* — the agent may repair existing files under `/src/providers/` and `/src/tools/` (`search/`, `fetch/`, ...). It can't create new files, and the central `registry` (`/src/registry.py`) sits *outside* those directories, so this scope can't edit it either. Since registration is centralized there — adapters don't self-register — editing an allowed file can change a capability's *behaviour* but can never add a new tool or backend. The capability set stays fixed **by construction**, with no diff or extra gate check needed. This keeps the agent self-healing for real-world tool-layer issues (auth, format drift, rate limits) without behavioural drift in the main loop.
- `full` — the agent may edit anything in `/src` and re-deploy itself, using the same machinery as dev mode: the deploy gate, `/dist.prev` rollback, sandbox, audit log.
