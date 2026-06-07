"""Runtime layer (non-editable by the agent).

Holds the deploy tool, the deploy gate (smoke floor + capability floor), config
parsing + governance lock, secret injection + env scrub, and the in-language
security guards (egress allowlist, fs scope, resource limits).

This package is imported by agent code as ``tools.<module>`` (a stable name).
The agent's own code lives in the ``src`` / ``dist`` packages and must never
edit anything here; the deploy gate runs from here so the agent cannot weaken
the checks that judge it.
"""
