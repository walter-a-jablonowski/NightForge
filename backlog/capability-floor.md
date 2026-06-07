# Capability floor — v2 backlog (LLM-as-judge)

Backlog for a richer behavioural verification layer. **Not in v1.** v1 ships a deliberately tiny capability floor: 2–3 objective, deterministic end-to-end cases in `/tools`, run as a regression gate at deploy (candidate `/src` must score ≥ the deployed `/dist`). See `app-concept.md` → Dev mode → deploy gate.

This file collects what a v2 would add and the open questions that have to be answered first. Keep the v1 trust posture in everything below: the floor lives in `/tools`, is **non-editable by the agent**, and its scores are written to runtime-owned `agent.log` deploy records (the agent can't write them, so the bar can't be gamed).

> **The principle behind this layer:** make *verification* as strong as the generation and safety sides. NightForge's safety (sandbox, gate, caps) and generation (the agent rewriting itself) are both solid; the standing weakness is *did it actually get better?* — which the agent's own tests can't answer because it wrote them. The capability floor is the verification leg: v1 proves the bar can't be gamed and that a deploy doesn't regress; v2 (below) makes it judge open-ended quality too. Self-critique (see [`reflection-self-critique.md`](./reflection-self-critique.md)) improves the candidate but doesn't count as verification — only a runtime-owned check the agent can't weaken does.


## Why v2

v1's objective checks only cover tasks with a verifiable answer (extract a known value, return a URL containing X). They can't score **open-ended** output — quality of a written summary, soundness of a design decision, helpfulness of an answer — which is most of what a general agent does. v2 adds judged evaluation so "better" can mean better at open-ended work, not just at the handful of things that happen to be checkable.


## What v2 adds

- **LLM-as-judge for open-ended cases.** A case whose output can't be checked programmatically is scored by a judge model against a **fixed rubric** that lives in `/tools` and the agent can't edit.
- **Judge ≠ candidate.** Judge with a *different* model than the one under test (and ideally a different provider), so the agent can't win by grading itself favorably. Pin the judge model/version so scores stay comparable across deploys.
- **Larger, mixed suite.** Objective cases (kept from v1) + judged cases, weighted. Score is a weighted aggregate; the regression-gate comparison stays the same shape (candidate ≥ deployed, within tolerance).
- **Held-out subset.** A portion of cases is never surfaced in `agent.log` or tool output, so the agent can't overfit to / game the cases it can observe.
- **Operator + specialization suites.** Operator can drop in their own cases; `devInstructions` can point the floor at a specialization suite so "better" tracks what the operator actually cares about.
- **Score history + drift detection.** Persist per-deploy scores in the header; flag slow multi-deploy regressions that any single ≥-comparison would miss.
- **Cost tiering.** Cheap subset every deploy; full suite less often (e.g. every N deploys or on demand). Cache by `/src` hash so an unchanged candidate isn't re-judged.


## Open questions (resolve before building)

- **Judge reliability.** LLM judges are noisy and biased (length, verbosity, self-style). How much noise is tolerable before the gate does more harm than good? Need calibration cases with known-good/known-bad outputs.
- **Nondeterminism / flakiness.** A judged run can fail by luck. Re-run policy? Score by median of k runs? This raises cost.
- **Gaming.** Even with a hidden subset, an agent optimizing hard against a fixed rubric can Goodhart it. How often should rubric/cases rotate, and who rotates them (operator, not agent)?
- **Cost & latency.** Judged suites mean extra real LLM calls per deploy. Does that count against `max_cost_sum`, or is it runtime overhead outside the agent's budget? (Leaning: runtime overhead, logged separately.)
- **Baseline bootstrap.** The very first deploy has no prior `/dist` score to beat — define the cold-start bar (e.g. must clear a fixed minimum on objective cases only).
- **Judge as attack surface.** The judge reads candidate output, which may include text derived from untrusted web content. Keep the judge sandboxed and treat its input as data, same as everywhere else.


## Explicitly still out of scope (even for v2)

Dashboards, full eval frameworks, human-in-the-loop scoring UIs, continuous benchmark tracking. If the agent wants those it can build them in `/src` as application-level tooling — they are not part of the trusted floor.
