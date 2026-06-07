# py-1 — build plan (handoff)

Implementation runway for the **Python seed** described in `app-concept-py.md`. Written so a fresh session can start coding without re-deriving scope or decisions.

## Read first (the complete inputs)

- `app-concept-py.md` — the spec. Authoritative for interfaces, loop/supervisor pseudocode, log shapes, deploy gate, config governance.
- `resources/web.md` — outbound HTTP etiquette every search/fetch backend must honor (robots, 429/Retry-After, conditional requests, User-Agent, etc.).
- `backlog/01 security MOV.md` — threat-model background.

## What this is (and isn't)

This is the **minimal bootable seed**, not the finished agent. The seed must boot, run one ReAct loop step, use its tools safely, write its own files, log, and deploy itself — then **dev mode** grows the rest (compaction, caching, richer memory, more backends). Rule of thumb from the spec: if a feature isn't required to (a) reason, (b) call a tool safely, (c) read/write its own files, or (d) stop — leave it out.

Seed scope (what to actually build):

- Frozen entrypoint `main(config, llm=None)` + supervisor loop (`app-concept-py.md` → Run lifecycle).
- `run_agent` ReAct/tool-calling loop (→ Agentic loop pseudocode), incl. the deploy-runs-alone rule and `resume_after_deploy()`.
- Provider adapter: **openrouter** only, wrapping the `openai` Python SDK at OpenRouter's endpoint; expose `call(...)`, `context_window`, `count_tokens(messages)`.
- Web backends: **tavily** (search) + **jina** (fetch) only.
- `registry.py` — central name→adapter map (providers, search, fetch, tools).
- Config parsing: merge `dev-config.yml`/`user-config.yml` + `/src/config.yml`, taking `llm`/`limits`/`improve`/`web` **only** from the operator file (governance lock).
- Secret injection + **env scrubbing** (adapters never read `.env`/`os.environ`).
- Memory: session list + **safety clip** (~75% context window); flat-markdown `/data/db` with `index.md` + `roadmap.md` stubs.
- Logging: JSONL `agent.log` — header record + per-step record (exact shapes in spec).
- Tools: `web_search`, `web_fetch`, `fs_read`, `fs_list`, `fs_write`, `fs_delete`, `run_tests`, `install`, `deploy`.
- Deploy tool + gate: smoke floor → agent tests → capability floor → swap `/src`→`/dist` → respawn; `/dist.prev` rollback; git auto-init.
- Runtime/agent split on disk: `/tools` (deploy tool + smoke floor + capability floor, **non-editable**) vs `/src` (agent-editable).
- Security enforcement: capability sandbox, scoped fs, host+method egress allowlist, `<untrusted>` wrapping, sandboxed test subprocess, resource limits.

Explicitly **out of seed** (agent adds in dev mode): compaction beyond the safety clip, result caching, extra telemetry, multi-agent/sub-agents, extra providers/backends, service mode.

## Open decisions — settle before the relevant stage

1. **Sandbox model — RESOLVED in spec (posture decided).** `app-concept-py.md` → Security → *Enforcement boundary* now mandates it: the real boundary is **OS-level** (isolated process/container; fs scoped via mounts; *all* egress forced through the allowlist). In-language guards (blocking `eval`/`exec`/`subprocess`/`socket`) are **defense-in-depth, not the boundary** — Python code with process privileges can reach around them (`ctypes`, `__import__`, C extensions). The **seed assumes it is launched inside an operator-provided container** (Docker Desktop / WSL2 on Windows) and does **not** build that isolation itself. So the seed's job (Stage 6) is to enforce the egress allowlist + fs scope + env scrub + in-language guards **and document the container-launch requirement** (a run note) — not to implement OS isolation. No fork left here; the only residual is the mechanism in #2.
2. **Egress enforcement point (open).** Forced HTTP proxy vs. network namespace vs. socket-level wrapper — the mechanism for the host+method allowlist inside the boundary. Proxy/namespace preferred (language-agnostic, harder to bypass); the socket wrapper is in-language and weakest.
3. **`count_tokens` / `context_window` source for OpenRouter** — model-metadata fetch vs. a small static table for the seed model.
4. **Capability-floor cases (author 2–3 concrete ones).** e.g. fetch a known-stable page and extract a fixed value; a search whose top hit URL contains an expected string. Pick durable targets.
5. **Dependency/install plumbing.** pip into `/agent/.venv`, pin into `/src/pyproject.toml`; restricted set (installer swap, system/OS installs, non-PyPI index) needs human approval.

## Stages (implementation sequencing, not redesign)

1. **Scaffold** — dir layout (`/tools`, `/src`, `/dist`, `/dist.prev`, `/data`, `.venv`), `pyproject.toml`, `.env.sample`, config loader + governance lock, dev/user config samples.
2. **Runtime core** — entrypoint, supervisor, `run_agent` loop, logging (header+step), `resume_after_deploy()` (replay whole session from `agent.log`).
3. **Adapters** — openrouter provider (+ `context_window`/`count_tokens`), tavily search, jina fetch, `registry.py`.
4. **Tools** — fs_* (scoped), run_tests (subprocess), install (bounded), deploy (stub the swap first).
5. **Deploy gate** — smoke floor (imports, config resolves, registry/schemas, adapters load, one stubbed-LLM step, backend lock), agent tests, capability floor (regression ≥ deployed, cold-start bar, tolerance + one re-run, `floor_cost`); then swap + respawn + `/dist.prev` + git commit.
6. **Security enforcement** — in-language guards + scoped fs, egress allowlist (host+method, mechanism per #2), `<untrusted>` wrapping, env scrub, resource limits; **plus a run note documenting the container-launch requirement** (the OS boundary is operator-provided — see decision #1 / spec *Enforcement boundary*).
7. **Seed content + boot check** — seed `/data/db` stubs, a starter `/src/tests` suite, dev `systemPrompt` with the capability checklist; verify a cold first-deploy passes the cold-start bar and the supervisor resumes after respawn.

## Done = the seed can

Boot from the seed → run a loop step against the real OpenRouter model → use web_search/web_fetch under the egress rules → write `/src` and `/data` → pass the deploy gate (cold-start) → swap and respawn → resume the session from `agent.log`. After that, dev mode takes over.
