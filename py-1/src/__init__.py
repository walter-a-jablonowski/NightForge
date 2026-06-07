"""Agent-editable code (the candidate version of the agent).

Loaded by the runtime as the ``src`` package (the deploy gate evaluates it) and,
after a swap, as the ``dist`` package (the active version the supervisor runs).
The same source must work under either package name, so **all imports within
this package are relative** (``from . import registry``). Runtime services are
imported absolutely from the stable ``tools`` package (``from tools import ...``).

Everything here is behind the frozen runtime<->agent interface and may be
rewritten by the agent — except the ``main`` signature in ``agent.py`` and the
``registry`` location, which the smoke floor verifies before any swap.
"""
