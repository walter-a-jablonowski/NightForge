# Features the agent adds itself — backlog

Capabilities deliberately left out of the v1 seed because the agent is expected to build them during dev mode. They mirror `app-concept.md` → "Explicitly out of scope for v1." None require the runtime to change; all are ordinary `/src` work behind the deploy gate — keeping the seed minimal is the point.


## Core agent features

- **Context-window compaction / summarization** — beyond the runtime's safety clip.
- **Tool-result caching** — avoid repeating identical fetches/searches.
- **Cost / latency telemetry** — beyond the simple budget counter used for the termination guard.
- **Multi-agent / sub-agents / planners** — orchestration patterns, if a task needs them.


## Persistent-memory extras

Beyond the flat `index.md` + topic files:

- time-based index
- URL queue + visited dates
- task tracking
- explicit memory ops (read / add / remove / edit notes, update indexes)


## Logging extras

Beyond the runtime's JSONL audit trail (additive, never replacing `agent.log`):

- tracing spans, dashboards, metrics, dedicated viewers


Some of these have their own design files where there are open questions worth pre-thinking — see [`multi-model-routing.md`](./multi-model-routing.md) and [`curriculum-tracking.md`](./curriculum-tracking.md).
