# Production service mode — v2 backlog

A long-running production agent that accepts tasks at runtime. **Not in v1.**

v1 production is **batch**: the supervisor serves the goal(s) in `AGENT.md` and exits once they're done (`done(config)` true). See `app-concept.md` → Production. There is no input channel — the goal is static, loaded once as the system prompt. This file describes what a *service* mode would add and the questions it raises.


## Why v2

Batch covers "run this defined job, then stop." It doesn't cover "stay up and handle requests as they arrive" — an ops bot taking alerts, a research assistant answering ad-hoc questions, an agent behind an API. For those, the agent has to live past a single goal and take new work without a restart. That's a genuinely different lifecycle, not a config tweak, so it's deferred rather than half-built.


## What v2 adds

- **An input channel.** Some way for a task to arrive at a running agent — the realistic options, simplest first: a watched task file / directory queue (`/data/inbox/`), a line-oriented stdin/CLI loop, or an HTTP endpoint. v1's batch path is the degenerate case (one task, from `AGENT.md`).
- **A task loop in the supervisor.** `done(config)` changes meaning: instead of "goal served ⇒ exit," it's "no shutdown signal ⇒ block for the next task." Each arriving task seeds a fresh `run_agent` (its own `run_id`), with persistent `/data` carrying context across tasks.
- **Per-task budgeting.** Today `max_cost` / `max_steps` are per *run* and `max_cost_sum` is per *session*. A service needs a **per-task** budget (so one expensive request can't starve the rest) plus an optional global rate/spend ceiling over a rolling window — distinct from the dev-session cumulative caps.
- **Clean shutdown.** A drain/stop signal that finishes the in-flight task, flushes `/data` and `agent.log`, and exits — versus batch's "exit when the goal is done."
- **Concurrency decision.** Strictly serial (one task at a time, simplest, matches the single-process model) or concurrent workers (needs locking on `/data` and `agent.log`, and a story for `improve`-time deploys while tasks are in flight).


## Open questions (resolve before building)

- **Deploy while serving.** Under `improve: full`, a production agent can still self-deploy (respawn). How does that interact with an in-flight task or a queue? Drain first, then swap? Reject deploys while busy? The batch model sidesteps this entirely.
- **Auth / trust on the input channel.** An open endpoint that feeds the agent goals is a prompt-injection front door — every incoming task is effectively untrusted input. Who is allowed to submit, and how is a task body treated relative to the `<untrusted>` tagging used for web content?
- **Backpressure & overload.** Queue bounds, timeouts, what happens when tasks arrive faster than they drain.
- **Idle cost.** A blocked, waiting agent should cost nothing (no polling LLM calls); confirm the loop truly idles rather than spins.
- **Cross-task memory hygiene.** `/data` persists across tasks by design, but some tasks shouldn't share context (different users/tenants). Namespacing or per-task scratch space?


## Out of scope (even for v2)

Multi-tenant orchestration, autoscaling, a job scheduler, or a web UI. Those are deployment concerns the operator wraps around the agent; this item is only about the agent itself accepting more than one task in a process lifetime.
