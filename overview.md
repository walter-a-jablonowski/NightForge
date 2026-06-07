# NightForge — Overview

A one-page map of the system for fast review. Full detail lives in [`app-concept.md`](./app-concept.md); section names below match it. v2 backlog lives in [`/backlog`](./backlog).


## 1. The idea in 5 lines

A **self-implementing** agent. You ship a tiny seed; in **dev mode** its only job is to research best practice and rewrite its own code until it's a competent agent, redeploying itself each iteration. When ready, you flip it to **production** to do real work — optionally still improving itself.

> Thesis: the agent you ship is ~600 lines; a non-editable runtime (~1,400 lines) is the trusted harness that makes letting it rewrite itself safe.


## 2. End-to-end lifecycle

```
                 ┌─────────────────────── dev mode (multi-run) ───────────────────────┐
                 │                                                                     │
   seed ─────▶  /src  ──edit──▶ run_tests ──▶ deploy ──▶ [GATE] ──▶ swap /src→/dist ──▶ respawn
 (fills /dist                                              │  fail                  │
  and /src)      ▲                                         └──── fix & retry ◀───────┘
                 │                                                                     │
                 └───────────────── new process resumes the session ◀─────────────────┘
                                                  │
                          agent writes /dist/production-ready  (signals "ready")
                                                  │
                                user flips mode: dev → production, restarts
                                                  ▼
                        production: serve AGENT.md goal(s) once (batch) → exit
                                    (improve = off | tools | full)
```


## 3. Process model (the vocabulary everything uses)

```
 session  ├─────────────────────────────────────────────────────────────┤  (dev → production-ready)
 runs      run r-1        │ run r-2          │ run r-3
           ●──steps──▶ deploy ●──steps──▶ deploy ●──steps──▶ final answer
                       (kills      (kills
                        proc)       proc)
                          └ respawn ──┘ resume_after_deploy() rebuilds memory from agent.log
```

| Term | Meaning |
|------|---------|
| **run** | one process life; fresh `run_id` each respawn; per-run caps (`max_steps`, `max_cost`) reset here |
| **session** | every run from entering `mode: dev` until `production-ready`; cumulative caps (`max_cost_sum`, `max_deploys`) span this |
| **respawn / resume** | `deploy` kills the process; the new one replays the **whole session** from `agent.log` to rebuild in-memory history |


## 4. The agentic loop (ReAct)

```
loop while steps < max_steps and cost < max_cost:
  1. llm.call(memory, tools)         → SDK validates tool schemas
  2. no tool calls?                  → RETURN final answer
  3. deploy among the calls?         → drop siblings, run deploy ALONE (it's terminal)
  4. execute each call → append observation to memory (errors fed back, never crash)
```

- **`deploy` is the only terminal tool** — it ends the process, so the loop forces it to run alone (or the respawn replays an assistant turn with an unanswered tool call).
- Schema errors / unknown tools / tool failures all return as a `tool` message the model can recover from.
- **Stops** on: final answer, per-run cap, or (cross-run) cumulative cap / `production-ready`.


## 5. Deploy cycle & the gate

```
deploy ─▶  [ smoke floor → agent tests → capability floor ]  ─▶ swap /src→/dist ─▶ respawn
              any layer fails ⇒ abort swap, /dist untouched, gate output returned to agent
```

| Gate layer | Lives in | Checks | Catches |
|------------|----------|--------|---------|
| **Smoke floor** | `/tools` (non-editable) | imports OK, config parses, provider/search/fetch names resolve, registry builds, adapters load under sandbox, **adapter exposes `context_window`+`count_tokens`**, one stubbed-LLM step runs; enforces backend-lock when self-built backends are off | an agent that can't even start |
| **Agent tests** | `/src/tests` (agent-written) | behaviour/correctness unit tests | functional regressions it can foresee |
| **Capability floor** | `/tools` (non-editable) | 2–3 **objective** end-to-end cases (real LLM); candidate must score **≥ deployed `/dist`** (first deploy: clear a cold-start bar); small tolerance + one re-run; cost = `floor_cost`, no charge to agent | a deploy that starts & passes its own tests but is **worse** at real tasks |

*Order across a deploy: `gate → swap → respawn`. `run_tests` runs the agent-test layer on demand mid-iteration. LLM-as-judge floor is v2.*


## 6. Directory layout & ownership

```
/agent
  dev-config.yml   user-config.yml   AGENT.md   .env        ← user-owned (agent never edits)
  agent.log                                                 ← runtime-owned (trce; survives swaps)
  /dist            active code (runs)        /dist.prev     ← swapped by deploy; one-step rollback
    config.yml (agent's own)  production-ready
  /src             next version — ONLY writable code area
    registry.<ext> providers/ tools/{search,fetch}/ tests/
  /data/db         persistent memory (flat markdown)        ← survives swaps, never auto-migrated
  /tools           deploy tool + smoke floor + capability floor   ← runtime, agent CAN'T edit
  /.git            optional: deeper rollback + diff review
```

| Area | Who writes | Deploy-gated? | Survives swap |
|------|-----------|---------------|---------------|
| `/src` | agent (`fs_write`) | yes — via `deploy` | becomes `/dist` |
| `/data` | agent, **directly** | no | yes (untouched) |
| `/dist`, `/dist.prev`, `agent.log` | runtime only | — | yes |
| configs, `AGENT.md`, `.env`, `/tools` | user / runtime | — | yes |

*Initial state: seed populates `/dist` **and** `/src`; `/data/db` starts with an `index.md` stub.*


## 7. Config files

| File | Owner | Mode | Holds | Agent-editable |
|------|-------|------|-------|----------------|
| `dev-config.yml` | user | dev | LLM, prompt, limits, tool choices, `web` | ✗ |
| `user-config.yml` | user | production | LLM, limits, `improve`, `web` | ✗ |
| `AGENT.md` | user | production | system prompt + goal(s) (markdown) | ✗ |
| `config.yml` | **agent** | production | the agent's **own** new feature flags | ✓ (lands via deploy) |
| `.env` | user | all | API keys | ✗ (non-readable) |

> **Governance lock:** `llm` · `limits` · `improve` · `web` are taken **only** from the user's file — ignored if they appear in the agent's `config.yml`. So the agent can't change its model, raise its own caps, widen its own `improve` level, or alter the identity it presents.


## 8. Runtime ↔ agent frozen interface

The one contract the agent must never change (off-limits even under `improve: full`; verified by the smoke floor).

| Piece | What it guarantees |
|-------|--------------------|
| **Entrypoint** | fixed `main(config, llm=None)` the runtime starts & respawns |
| **Config object** | runtime parses/merges config and passes it in (enforces the governance lock) |
| **LLM injection** | loop uses the passed-in client → floor can inject a no-network **stub** |
| **Secret injection** | adapters never read `.env`/env; runtime hands each only its key; **env is scrubbed** so `os.environ` can't leak secrets |


## 9. Built-in tools

| Tool | Scope / behaviour |
|------|-------------------|
| `web_search`, `web_fetch` | read-only web; results wrapped `<untrusted>` |
| `fs_read`, `fs_list` | read `/agent` except `.env`, config files, runtime files (`agent.log` *is* readable) |
| `fs_write`, `fs_delete` | write `/src` (code) + `/data` (memory) + the single file `/dist/production-ready` |
| `run_tests` | run `/src/tests` in a sandboxed subprocess |
| `install` | bounded package install from the configured registry (no shell); rides a deploy |
| `deploy` | run gate → swap → respawn (terminal) |

*New tools = implementation in `/src` + one line in the central `registry`, callable only after the next deploy + sandbox check.*


## 10. Memory

| Store | Where | Written | Survives swap | Comments |
|-------|-------|---------|---------------|-------|
| **Session** | in-process `memory` list | by the loop | no (replayed from log) | runtime **safety clip** elides oldest observations at ~75% of context window (via adapter `count_tokens`/`context_window`) so a step can always run |
| **Persistent** | `/data/db/*.md` | `fs_write` directly | yes | flat markdown; `index.md` + `roadmap.md` seeded; agent migrates its own format (additive/idempoent), never auto-migrated |


## 11. Security model *(review centerpiece)*

**Layered defense (all runtime-enforced, never the agent's "good behaviour"):**
`capability sandbox` · `capability frontier` · `untrusted-content tagging` · `filesystem scope` · `egress allowlist` · `secret injection` · `sandboxed tests` · `resource limits` · `trce log`.

**Network egress** — scoped by host **and** method:

```
                       configured hosts                 open web (arbitrary hosts)
                       (openrouter, tavily, jina,
                        package registry)
  web_fetch backends   full methods (e.g. POST query)   GET / HEAD only, NO body  (read, never act)
  package install      registry host only               blocked
  anything else        blocked                           blocked
```
*Every request carries the runtime-injected `User-Agent` (`web.user_agent` + `contact`) — no spoofing. Adding a full-method host is a human (frontier) step.*

**Filesystem scope:**

| Op | Scope | `improve` effect (production) |
|----|-------|-------------------------------|
| `fs_read` | `/agent` minus `.env`, configs, runtime files | — |
| `fs_write` | `/src` + `/data` + `/dist/production-ready` | `off`: no `/src` · `tools`: only existing files in `providers/`+`tools/` · `full`: all of `/src`. `/data` always writable. |

**Capability frontier** — what the agent may do freely vs. what only a human can grant:

| Free (self-extended) | Human-gated (frontier) |
|----------------------|------------------------|
| improve its own code | new full-method egress hosts |
| add tools composing existing capabilities | filesystem scope beyond `/src`+`/data` |
| read-only open-web fetch | system-level access |
| install ordinary registry packages | replace package manager / system / off-registry installs |

**Untrusted content:** web results are tagged `<untrusted>` and treated as data. *Residual:* comments distilled into `/data` lose the tag on re-read (laundering one hop) — contained by sandbox/gate/egress; provenance-tagging is v2.


## 12. Limits & caps

| Cap | Scope | Resets | Enforced by |
|-----|-------|--------|-------------|
| `max_steps` | per run | every respawn | loop guard |
| `max_cost` | per run ($) | every respawn | loop guard |
| `max_cost_sum` | per session ($) | on promoion to production | runtime (from `agent.log`) |
| `max_deploys` | per session | on promoion | runtime (from `agent.log`) |
| per-write size cap, `/src` disk quo | always | — | runtime |

*Capability-floor LLM spend is logged as `floor_cost` and **un**charged to these. A cumulative-cap stop or fatal error halts for the user — no silent retry.*


## 13. v1 scope vs v2 backlog

| Capability | v1 | Deferred to |
|------------|----|-------------|
| Provider adapters | openrouter only | — (agent adds more) |
| Web backends | tavily (search), jina (fetch) | — |
| Capability floor | 2–3 objective cases, no judge | [`capability-floor.md`](./backlog/capability-floor.md) (LLM-as-judge) |
| Memory | flat markdown, no provenance | [`provenance-tagged-memory.md`](./backlog/provenance-tagged-memory.md) |
| LLM use | single model | [`multi-model-routing.md`](./backlog/multi-model-routing.md) |
| Dev target | prose checklist + `roadmap.md` | [`curriculum-tracking.md`](./backlog/curriculum-tracking.md) |
| Deploy approval | none (autonomous) | [`human-approval-mode.md`](./backlog/human-approval-mode.md) |
| Production | batch (serve goal, exit) | [`production-service-mode.md`](./backlog/production-service-mode.md) |
| Also out of v1 | compaction (beyond clip), result caching, telemetry, multi-agent | agent builds for itself |


## 14. Key invariants (what the agent *can't* do)

- [ ] Edit `dev-config.yml`, `user-config.yml`, `AGENT.md`, `.env`, or `/tools` (runtime).
- [ ] Read `.env` — neither via `fs_read` nor `os.environ` (env is scrubbed).
- [ ] Raise its own caps, change its model, widen its own `improve`, or change its `User-Agent` (governance lock).
- [ ] Grant itself a new egress host, wider filesystem scope, or a system install (capability frontier).
- [ ] `POST`/mutate on the open web — fetch is read-only (`GET`/`HEAD`, no body).
- [ ] Deploy code that can't start, regresses the capability floor, or fails its tests (deploy gate).
- [ ] Run shell / `eval` / direct network — only the tool registry acts on the world.
- [ ] Tamper with `agent.log` or the cumulative caps derived from it.
- [ ] Skip the tril — every tool call is logged, all modes.
