# Multi-model routing — v2 backlog

Cost/latency lever for a self-deploying agent. **Not in v1** — v1 uses a single configured model for every step.


## Why v2

A self-implementing agent burns its `max_cost_sum` on a long tail of cheap, mechanical steps (file edits, test runs, log reads, boilerplate) interleaved with a few expensive, high-stakes ones (architecture decisions, debugging a subtle failure, judging "am I state-of-the-art yet?"). Paying frontier-model rates for the mechanical majority is the dominant waste in a dev session. Routing the easy steps to a cheap/fast model and reserving the strong model for the hard ones can cut dev-session cost substantially without hurting the decisions that matter.

v1 deliberately skips this: one model, one adapter, no routing logic — simplest thing that works, and the agent can build routing for itself once it exists.


## What v2 adds

- **A model tier in config.** `llm` grows from one model to a small set with roles, e.g. `cheap` / `default` / `strong` (still under the operator-owned `llm` key — the agent can't add tiers or pick models to dodge cost caps).
- **A routing policy.** A step's tier is chosen by a cheap signal: step kind (edit/test/read vs. design/debug), recent failure (escalate after a gate failure or a confused step), explicit self-request ("this is a hard call — use `strong`"), or a small classifier. Start rule-based; a learned router is later.
- **Cost accounting stays unified.** All tiers bill into the same `max_cost` / `max_cost_sum` — routing changes the *spend rate*, never the *ceiling*.
- **Provider-aware.** Tiers may span providers (cheap local + strong hosted); each tier resolves through the normal provider-adapter layer, so no new interface.


## Open questions (resolve before building)

- **Who routes — runtime or agent?** Routing inside `/src` lets the agent tune it (good) but means a bug can route every step to the cheapest model and quietly tank quality (the capability floor would catch a big regression, not a slow drift). Routing in the runtime is safer but less flexible. Likely: agent proposes, capability floor guards.
- **Escalation loops.** A cheap model that keeps failing a step and escalating to strong can cost *more* than going strong first. Need a cap on escalation hops per step.
- **Mid-session model identity.** `resume_after_deploy()` replays a transcript that mixed tiers; does replay need to know which model produced which turn? (Probably not — turns are model-agnostic in the normalized shape — but verify.)
- **Floor scoring.** If the capability floor runs the candidate with routing on, a routing change can move the score for reasons unrelated to capability. Consider scoring at a fixed tier.


## Out of scope (even for v2)

Speculative/parallel multi-model ensembles, debate, or self-consistency voting. Those are application-level techniques the agent can build in `/src`; this backlog item is only about per-step tier selection to control cost.
