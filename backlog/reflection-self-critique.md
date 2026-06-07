# Reflection / self-critique steps — backlog

Explicit reflect / self-critique steps in the loop (the agent reviews its own plan or output before acting or finishing). **Not in v1** — and mostly something the agent can add to its own loop during dev mode under `improve: full`.


## Why it's not in the seed

The v1 loop is a plain ReAct tool-loop, intentionally minimal. Reflection (self-critique, plan-then-execute, verify-before-finish) is a well-known quality technique, but it's *behaviour the agent can build into its own loop body* — not something the trusted runtime needs to own.


## What an agent-built version could add

- A **critique pass** before `deploy` or before a final answer: re-read the diff/answer against the goal and the dev checklist, revise if weak.
- **Plan → act → reflect** structure rather than flat ReAct, for multi-step tasks.


## The important caveat

Self-critique is *agent-judged*, so it is gameable and prone to "reflection theatre" — a model critiquing itself with the same blind spots rarely catches them. It **complements but never replaces** the runtime-owned capability floor: self-critique improves the candidate (generation side); the floor decides whether it actually got better (verification side). See [`capability-floor.md`](./capability-floor.md) and [`curriculum-tracking.md`](./curriculum-tracking.md).


## Open questions

- Cost/latency: reflection multiplies LLM calls per step — worth it only where it measurably helps.
- Does it live in the loop (runtime-visible) or purely inside the agent's prompt strategy?
