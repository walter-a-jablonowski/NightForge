![alt text](misc/logo_2.png)

> Why write the agent? Let the agent write itself.

A minimal AI agent that writes most of its own implementation. You start it with a tiny seed; it spends "dev mode" reading state-of-the-art knowledge about agent design and components that the agent must have. It edits its own code until it's a competent agentic system. Then it switches to production and does whatever you set it to — optionally still improving itself along the way.

| File/Dir | Description |
|---|---|
| app-concept.md | Reusable app concept |
| app-concept-py.md | Specialized app concept for Python |
| overview.md | System overview |
| /py-1 | First python implementation |

## State

*** DANGER *** DANGER *** DANGER *** DANGER *** DANGER ***

Started Python reference implementation (`py-1/`). No testing. I will do minimal testing when I can find the time or tokens for that.

**Help wanted:** Testing help and contributions are welcome. \
**MIT License (see below):** USE AT YOUR OWN RISK ONLY --

*** DANGER *** DANGER *** DANGER *** DANGER *** DANGER ***


## Why

Most "self-improving" agents only tune prompts or skills. NightForge goes one level deeper: the agent edits its own source code, adds its own features, picks its own libraries, and re-deploys itself.

- **No large codebase to maintain.** The seed is tiny on purpose.
- **Always current.** When best practice changes, throw away `/dist`, restart dev mode, get a fresh state-of-the-art agent.
- **Specialisable.** `devInstructions` lets you bias what the agent grows into (research assistant, coding agent, ...).


## How it works

```
   ┌──────────┐  edits /src,        ┌──────────┐
   │ dev mode │  runs tests,        │ deploy   │  swap /src → /dist
   │  (loop)  │ ───────────────────▶│  tool    │ ────────────────────┐
   └──────────┘   calls deploy      └──────────┘                     │
        ▲                                                            │
        │  fresh agent picks up                                      │
        └────────────────────────────────────────────────────────────┘

                 ── user flips mode ──▶  production
```

1. **Seed.** A minimal agent ships with a ReAct-style tool-calling loop, a handful of built-in tools, and three config files. That's it.
2. **Dev mode.** The agent's only task is to improve itself: it reads the web, edits files in `/src`, runs its own tests, and calls the `deploy` tool to swap the new code into `/dist`. Repeat.
3. **Ready.** When the user (or the agent) decides it's ready, the user flips `mode: production` in `dev-config.yml`. The agent now serves real tasks.
4. **Production.** Same loop, driven by `user-config.yml`: the agent serves the goal(s) in `AGENT.md` as a batch, then exits. The `improve` setting controls how much self-modification is still allowed: `off`, `tools` (default — fix broken adapters but freeze main), or `full`.


## Requirements

The reference implementation targets **Python**. Known so far:

- **Python 3.x + pip**, with the agent working inside a virtualenv (`/agent/.venv`) — the agent installs packages during dev mode to build itself.
- **An OS-level isolation boundary** to run inside — a container (Docker Desktop / WSL2 on Windows). The runtime's sandbox guarantees (no shell/network, scoped fs, egress allowlist) are only real at this boundary; in-language guards are defense-in-depth, no boundary. See [`app-concept-py.md`](./app-concept-py.md) → Security → *Enforcement boundary*.
- **API keys** in `.env` for the providers you use — at minimum the LLM provider (OpenRouter by default), plus web-search/fetch keys depending on the chosen backends (Tavily needs a key; Jina and local backends don't).
- **Outbound network access** to the configured provider/backend hosts and the package registry. The runtime blocks everything else via the egress allowlist.
- **git** *(optional, recommended)* — if present, the deploy tool auto-initializes a repo and commits every swap, giving multi-step rollback and diff review for free. Without it you still get one-step `/dist.prev` rollback. git is a prerequisite; the agent doesn't install it.


## Configuration

Three YAML files, `AGENT.md`, plus `.env` (full schemas in [`app-concept.md`](./app-concept.md)):

| File | Owner | Purpose |
|---|---|---|
| `dev-config.yml`  | user  | Dev-mode LLM, prompt, limits, tool choices |
| `user-config.yml` | user  | Production LLM, limits, `improve`, `web` |
| `AGENT.md`        | user  | Production system prompt (agent role + goal(s)), as markdown |
| `config.yml`      | agent | The agent's own settings (can't override `llm` / `limits` / `improve` / `web`) |
| `.env`            | user  | API keys (LLM provider, web search, ...) |

LLM access defaults to **OpenRouter** (one key, most major models). Web search defaults to **Tavily**, fetch to **Jina Reader**. All three are swappable — add a new file in `/src/providers/`, `/src/tools/search/`, or `/src/tools/fetch/` plus a one-line entry in the central registry. (A backend that needs a brand-new host is a one-time, human-approved step — see the capability frontier.)


## Architecture at a glance

```
/agent
  dev-config.yml    # dev-mode config (immutable to the agent)
  user-config.yml   # production config (immutable to the agent)
  AGENT.md          # production system prompt (immutable to the agent)
  .env              # API keys
  agent.log         # runtime-owned JSONL trail; survives /dist swaps

  /dist             # active agent (swapped on deploy)
  /dist.prev        # previous /dist — one-step rollback
  /src              # next version; the only writable area
    registry.<ext>  # central name→adapter registry (tools, providers, backends)
    /providers      # one file per LLM provider (openrouter, ollama, ...)
    /tools          # tool backends the model calls
      /search       #   web_search backends (tavily, exa, ...)
      /fetch        #   web_fetch  backends (jina, firecrawl, ...)
    /tests          # agent-written tests; run by the deploy gate
  /data/db          # persistent memory; written directly, survives deploys
  /tools            # deploy tool + smoke floor + capability floor (non agent-editable)
```

See [`app-concept.md`](./app-concept.md) for the full spec including the agentic loop pseudocode, adapter interfaces, and security model.


## Safety

NightForge is a self-modifying agent that reads the web — each of which are dangerous. The runtime, **instead of the agent**, enforces all safety — and that enforcement is only real at an **OS-level boundary**: the agent runs inside an isolated container, with the filesystem scoped via mounts and all egress forced through the allowlist. In-language guards (blocking shell/`eval`/network) are defense-in-depth, no boundary, since the agent's own code runs with the process's privileges. The seed assumes it is launched inside such a container.

- **Capability sandbox.** The agent affects the world only through the tool registry. No shell, no `eval`, no direct network, and no ambient secrets — `.env` is injected to adapters key-by-key and scrubbed from the environment, so the agent can't read it even via `os.environ`.
- **Capability frontier.** The agent freely improves its code and adds tools that compose existing capabilities, but new capabilities — egress hosts, system installs, filesystem scope — are human-extended, never self-granted.
- **Filesystem scope.** `fs_read` excludes `.env`, the config files, and the runtime's own files; `fs_write` covers `/src` (code) and `/data` (memory), with `improve` narrowing only the `/src` part in production.
- **Network egress allowlist.** Outbound HTTP only to hosts of currently configured providers/backends and the package registry (full methods); `web_fetch` backends additionally get read-only (`GET`/`HEAD`) access to the open web, so a direct fetcher can read any page but never act on a site.
- **Deploy gate.** Every deploy must pass three layers before the swap — a runtime smoke floor (the new code starts), the agent's own tests, and a runtime capability floor (a few fixed end-to-end cases the new code can't regress on); a failure aborts the swap untouched.
- **Sandboxed tests.** The smoke floor and `run_tests` run in a subprocess with the same restrictions.
- **Untrusted-content tagging.** Web results are wrapped in `<untrusted source="...">` so the model treats them as data, no instructions.
- **Trail.** Every tool call lands in `agent.log`. Always-on, runtime-owned, all modes.
- **Cheap rollback.** The deploy tool keeps `/dist.prev` (one step) and, when git is available, auto-commits each swap for deeper rollback.


## License

[MIT license](LICENSE). Use at you own risk.
