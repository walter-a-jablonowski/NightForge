# Optional human-approval mode — v2 backlog

An opt-in checkpoint for high-blast-radius changes. **Not in v1.**

v1's stance is deliberate: **no human approval gate** on deploys (it would defeat a self-implementing agent), with safety supplied instead by the deploy gate, per-run caps, the sandbox, and cheap rollback. See `app-concept.md` → Dev mode → "No human approval gate." The only thing that already pauses for a human is the **capability frontier** (new egress hosts, filesystem scope, system/off-registry installs). This item keeps the autonomous default and adds an *optional* knob for operators who want a tighter leash on the riskiest self-modifications.

*Origin: an always-on `requiresApproval` gate existed in an early design and was removed in favour of observability + cheap rollback (it defeated the self-implementing premise). This file is the deliberate **revisit** of that decision as an opt-in checkpoint — not a return to mandatory approval.*


## Why v2

The frontier covers *new capabilities* but not *large rewrites within existing capabilities*. Under `improve: full`, the agent can rewrite the agentic loop, the supervisor, or the secret-injection seam — changes that pass the gate yet carry real blast radius if subtly wrong. A cautious operator (running in production, or on a sensitive deployment) may want to review those before they swap, without giving up autonomy for routine edits.


## What v2 adds

- **An approval policy, off by default.** A config knob (operator-owned) sets *when* a deploy pauses for human sign-off — e.g. `approval: off | risky | all`, where `risky` triggers on changes touching the frozen interface, the loop/supervisor, or `config.yml` governance-adjacent areas, and leaves ordinary tool/backend edits autonomous.
- **A clean pause/resume.** On a gated deploy the tool blocks *after* the gate passes but *before* the swap, writes the candidate diff + gate/floor results somewhere reviewable, and waits. Approve → swap + respawn; reject → discard `/src` change, feed the rejection back as a tool observation so the agent revises.
- **Risk classification.** Reuse the diff surface that already exists (git auto-commit + `agent.log`): classify a candidate by *what it touches*, not by guessing intent.
- **Timeout behavior.** A pending approval that no human answers must fail safe (stay on current `/dist`, don't auto-approve) and surface loudly.


## Open questions (resolve before building)

- **Pause mechanism for an autonomous loop.** The agent runs unattended; a blocking approval needs an out-of-band channel (a flag file the operator touches, a CLI, a notification) and a defined "what does the process do while waiting" (idle? exit and resume on restart, like a deploy?).
- **Risk classifier accuracy.** Too eager ⇒ it pauses on everything and the operator rubber-stamps (approval theater); too lax ⇒ the risky change it was meant to catch slips through. Needs tuning + an audit of false negatives.
- **Interaction with cumulative caps.** Time spent awaiting approval shouldn't burn `max_cost`/wall-clock budgets; define how a paused deploy accounts.
- **Production vs. dev.** Is this mainly a *production* `improve: full` safeguard, or also useful in dev? (Dev's whole point is speed; approval there may negate it.)


## Out of scope (even for v2)

Per-step approval, mandatory review of every deploy, or a multi-reviewer workflow. The default stays autonomous; this is one opt-in checkpoint for the highest-risk class of change, not a return to human-in-the-loop development.
