# Provenance-tagged memory — v2 backlog

Closes the trust-laundering path noted in `app-concept.md` → Security → Untrusted content. **Not in v1.**


## The problem

`web_search` / `web_fetch` results are wrapped in `<untrusted source="...">` so the model treats them as data, not commands. But the agent distills those findings into `/data/db/*.md` notes, and a later `fs_read` returns them as **ordinary, trusted memory** — the untrusted marker is gone. So a poisoned page can launder an instruction into trusted context one hop later (page → note → re-read as fact).

In v1 the *effect* is still contained — the sandbox, deploy gate, and egress allowlist mean a laundered instruction can sway a design choice but can't escape, exfiltrate, or skip the gate. v2 narrows the *input* itself so untrusted-derived text stays marked wherever it travels.


## What v2 adds

- **Provenance metadata on memory writes.** `fs_write` to `/data` records, per file (or per section), where the content came from: `source: authored | web | mixed`, plus the originating URL(s) when `web`. Cheapest form is a frontmatter block the runtime stamps; richer is a sidecar index.
- **Tag preserved on read.** When `fs_read` returns content whose provenance is `web`/`mixed`, the runtime re-wraps it in `<untrusted source="...">`, exactly as a live fetch would — so the laundering hop no longer strips the marker.
- **Propagation rule.** A note synthesized from untrusted material inherits `web`/`mixed`; only content the agent writes from its own reasoning (no untrusted span quoted) is `authored`. Conservative default: if unsure, mark `mixed`.
- **Operator view.** Surface provenance in `agent.log` and any future review UI, so a human auditing a design decision can see which inputs were untrusted.


## Open questions (resolve before building)

- **Granularity.** Per-file is cheap but coarse (one untrusted quote taints the whole topic file); per-section/per-line is precise but needs the agent to cooperate in marking spans. Where's the line?
- **Who stamps provenance?** If the *agent* self-reports the source on each write, a compromised agent can lie. If the *runtime* infers it (e.g. "this write happened within N steps of a fetch"), it's tamper-resistant but noisy. Likely a runtime-enforced floor (write-after-fetch ⇒ at least `mixed`) plus optional agent refinement.
- **Trust decay.** Does provenance ever "graduate" to trusted (e.g. after human review, or corroboration by K independent sources)? Or is `web` permanent?
- **Context cost.** Re-wrapping large recalled notes in untrusted markers eats context and re-triggers the model's data-not-commands handling on every recall. Tune against the safety clip.


## Out of scope (even for v2)

Full information-flow tracking / taint analysis across arbitrary computation. This is a pragmatic marker that survives the store→recall hop, not a formal IFC system.
