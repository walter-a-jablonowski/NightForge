# Self-rewrite of language & runtime — backlog

Open question from the backlog: *may the agent change its own implementation language and execution environment?* **Not in v1.**

v1 picks one language for the seed (TBD) and the agent builds itself within it, pulling libraries through the bounded `install` capability. It does **not** change its own language or swap its runtime.


## Why it's deferred (and genuinely hard)

- The runtime (`/tools`: deploy tool, smoke floor, capability floor, sandbox, egress) is written against the seed's language and process model. A language change means the trusted harness can no longer load, smoke-test, or sandbox `/src` the same way — i.e. the part that must stay fixed would itself have to change.
- The frozen runtime↔agent interface (entrypoint signature, config object, LLM/secret injection) is language-specific. Crossing languages breaks the contract the smoke floor verifies.
- A new interpreter/runtime is a system-level install — already a capability-frontier (human-approved) action, not something the agent self-grants.


## What a later version might allow

- **Polyglot tools, single core.** Keep the trusted core in one language; let the agent add tool *backends* in another via subprocess (still inside the sandbox + egress rules). Cheap, and covers most of the real need ("I want a library that only exists in X").
- **Operator-driven re-seed.** Treat "switch language" as re-running a *different* seed (a fresh build-from-source), not an in-place self-migration — consistent with the "recipe, not a binary" framing.


## Open questions

- Who owns the runtime after a language change — is there even a trusted harness in the new language?
- How do cross-language deploy/rollback and capability-floor scoring stay comparable?
- Is the need real, or does "add a subprocess tool in language X" already cover it?


## Out of scope

In-place autonomous rewrite of the agent's own runtime/interpreter. That dissolves the fixed trusted base the whole safety model rests on.
