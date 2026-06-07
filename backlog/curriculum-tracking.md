# Curriculum / progress tracking — v2 backlog

A richer version of the v1 dev-mode target. **Not in v1.**

v1 ships the minimum that stops thrashing: a **capability checklist in the dev `systemPrompt`** (the target) plus a free-form `/data/db/roadmap.md` the agent maintains (its progress notes). See `app-concept.md` → Dev mode → "The dev-mode target." That's enough to give the open-ended "improve until state-of-the-art" loop a destination. This file is about turning that loose checklist into something the system can *measure progress against*.


## Why v2

The v1 setup has a target but no **forward metric**. The capability floor only answers "did this deploy get worse?" (regression). The roadmap is prose the agent writes and could drift from, ignore, or mark done prematurely. Nothing scores *how far along* the build is or flags a stalled session (many deploys, no checklist items closed). For long unattended dev runs, an operator wants a progress signal, not just a non-regression guarantee.


## What v2 adds

- **Structured curriculum.** The checklist becomes machine-readable items (id, description, acceptance signal, status), seeded from the systemPrompt/`devInstructions` and tracked in a runtime-owned record (not agent-writable, so "done" can't be self-declared without evidence).
- **Acceptance signals per item.** An item closes when an objective signal fires — a new capability-floor case passes, a specific test exists and is green, a target file/feature is present — not just because the agent says so.
- **Forward score + stall detection.** A monotone "fraction of curriculum satisfied" alongside the regression score; flag a stall (N deploys with no item closed and no score gain) so a human can intervene or the session can halt.
- **Specialization curricula.** `devInstructions` can swap in a domain curriculum (coding agent vs. research assistant vs. ops bot) so "done" tracks the operator's actual target.
- **Graduation criterion.** "Ready for production" becomes "curriculum satisfied + no open blockers," a firmer version of v1's heuristic self-assessment (the user still decides).


## Open questions (resolve before building)

- **Who authors acceptance signals?** Operator-written signals are trustworthy but laborious; agent-proposed signals are cheap but gameable (it can write a trivially-passing test and call the item done). Likely operator-owned signals for core items, agent-proposed for sub-tasks.
- **Curriculum vs. emergence.** Too rigid a curriculum fights the "agent figures out what it needs" premise; too loose and it adds nothing over v1's prose roadmap. Where's the balance?
- **Gaming the forward score.** Same Goodhart risk as the capability floor — optimizing the metric instead of real capability. Hidden/rotated acceptance criteria, as with the floor.
- **Interaction with `max_deploys`.** A stall-halt and the cumulative deploy cap are both "stop" signals; define precedence and messaging so they don't fight.


## Out of scope (even for v2)

Gantt charts, burndown dashboards, project-management UIs. If the operator wants those, they read the structured record with their own tooling; the trusted layer is just the curriculum + acceptance signals.
