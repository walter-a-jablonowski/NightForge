# NightForge — self-implementing agent (Python seed)

A minimal bootable seed for a self-improving agent. It boots, runs a ReAct
tool-calling loop against an LLM, uses web search/fetch under an egress
allowlist, writes its own code (`/src`) and memory (`/data`), passes a deploy
gate, swaps itself over `/dist`, respawns, and resumes from `agent.log`. From
there, **dev mode** grows the rest (compaction, caching, richer memory, more
backends). See `app-concept-py.md` for the full design and `BUILD.md` for scope.

## Layout

```
tools/   runtime (non-editable): boot, config + governance lock, secret scrub,
         security guards, deploy tool, smoke floor, capability floor, audit log
src/     agent-editable code (the candidate); imports are relative so the same
         source works whether loaded as `src` (gate) or `dist` (active)
dist/    active code the supervisor runs (swapped on deploy)
dist.prev/  previous /dist, kept for one-step rollback
data/db/ long-term markdown memory (survives deploys)
```

## Run

1. `python -m venv .venv` and install deps:
   `.venv/Scripts/python -m pip install pyyaml httpx openai pytest`
2. Copy `.env.sample` to `.env` and fill in `OPENROUTER_API_KEY` and
   `TAVILY_API_KEY`.
3. Pick the mode in `dev-config.yml` (`mode: dev` to grow the agent).
4. Launch: `.venv/Scripts/python -m tools.boot .`

The supervisor drives runs; a `deploy` swaps `/src`→`/dist` and respawns the
process, which resumes the session from `agent.log`.

### Offline self-test (no keys)

`AGENT_STUB_LLM=1 .venv/Scripts/python -m tools.boot .` exercises the whole
chain — loop step → deploy gate (smoke floor + agent tests + capability floor) →
swap → respawn → resume → stop — with a deterministic stub, no network. Use it to
verify the machinery; production always uses the real provider.

## Run note: container requirement (the security boundary)

**The in-language guards in `tools/sandbox.py` are defense-in-depth, not the
boundary.** The agent writes and runs its own code, and Python running with the
process's privileges can reach around any in-process guard (`ctypes`,
`__import__`, C extensions). The real boundary must be **OS-level**:

- run the seed inside an **isolated process/container** — on Windows, Docker
  Desktop or WSL2 (there is no `seccomp` equivalent for a bare process);
- mount the filesystem so only `/agent` is reachable, and `/agent/.venv`,
  `/agent/tools`, the config files, and `.env` are protected as the runtime
  expects;
- force **all** outbound traffic through the egress allowlist (a proxy or network
  namespace), so an off-allowlist host or a mutating method on the open web is
  blocked below the language.

Providing and tightening this boundary is an operator/deployment concern the
runtime relies on but the agent cannot grant itself (it sits on the capability
frontier). Without the container, the guards still apply but a sufficiently
adversarial change to `/src` could bypass them.
