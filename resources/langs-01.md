
#### Language recommendation (added 2026-05-30, best first)

What actually matters for *this* system: (a) the LLM must write it reliably — it rewrites itself; (b) interpreted/no heavy build step so a deploy is just swap-and-respawn; (c) mature LLM + web SDKs; (d) easy to sandbox.

1. **Python — recommended.** Best LLM tooling by far (every provider SDK, native tool-calling), and the language LLMs write most reliably (largest training mass). Interpreted → the agent edits `/src` and respawns with no compile step. Web stack already matches the spec (`exa-py`, `tavily`, `trafilatura`, `requests/httpx`). Trade-off: sandboxing takes work (no built-in capability model — must enforce the no-shell/no-eval/scoped-fs rules in the runtime) and packaging/venvs are fiddly. The fit is still strong enough that the cons are engineering, not blockers.

2. **TypeScript / Node — strong second.** Excellent provider SDKs, async-native (good for the web-heavy loop), single-package deploy. LLMs write it well (second-largest mass). `tsx`/`ts-node` keep it effectively interpreted so self-rewrite stays cheap. Pick this over Python if you want one language for runtime + agent code and a cleaner dependency story.

3. **Deno (TS) — best fit for the sandbox.** Same TS upside, but with a built-in **permission model** (`--allow-net=host`, `--allow-read`, `--allow-write`) that maps almost 1:1 onto the capability sandbox and egress scope in app-concept.md — the runtime gets OS-enforced isolation for free instead of hand-rolling it. Single executable, URL imports. Cons: smaller ecosystem than Node, slightly less training mass, some npm-compat edges.

4. **Go — for the runtime, ins of agent code.** Compiles to a single static binary → an exceptionally clean swap-and-respawn and strong process control. But the compile step adds friction to every self-rewrite, and LLMs write Go less fluently than Python/TS. Best as a *split*: trusted runtime/supervisor in Go, agent-written `/src` in Python or TS. Adds complexity (two languages, an IPC seam) — only worth it if you want the runtime hardened.

- Skip for v1: Rust (compile + LLMs write it least reliably — wrong layer to optimize while the agent is rewriting itself), JVM/.NET (heavy, build-step, weaker fit).
- **Net:** Python if you optimize for LLM-writability and ecosystem; Deno if you optimize for getting the sandbox right with the least runtime code. Either keeps the language decision consistent with the "minimal seed, interpreted, self-rewriting" premise.
- Allow-list comment (from the deps task above): per-language default-allow registries — Python = PyPI, TS/Node = npm, Deno = JSR/npm — with the same "block dangerous, human-gate system/off-registry" rule regardless of language.
