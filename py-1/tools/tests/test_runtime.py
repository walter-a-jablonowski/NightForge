"""Runtime security + invariant tests (the non-editable layer)."""

import os
from pathlib import Path

import pytest

from tools import audit, installer, sandbox, secrets
from tools.config import Config, load_config


# --- fixtures ---------------------------------------------------------------

def _cfg(root, mode="dev", improve="full"):
    return Config(
        agent_root=Path(root), code_dir=Path(root) / "dist", mode=mode,
        llm={"provider": "openrouter", "model": "anthropic/claude-sonnet-4"},
        limits={"max_steps": 50, "max_cost": 5.0, "max_cost_sum": 50.0, "max_deploys": 30},
        improve=improve, web={"user_agent": "T", "contact": "mailto:a@b.c"},
        tools={"web_search": "tavily", "web_fetch": "jina"},
        system_prompt="sys", instructions="",
    )


@pytest.fixture
def configured(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "dist").mkdir()
    (tmp_path / ".env").write_text("X=1", encoding="utf-8")
    sandbox.configure(_cfg(tmp_path))
    return tmp_path


# --- egress allowlist -------------------------------------------------------

def test_egress_blocks_off_allowlist_host(configured):
    with pytest.raises(sandbox.SecurityError):
        sandbox.http_request("GET", "https://evil.example.com/x")


def test_egress_blocks_open_web_without_flag(configured):
    with pytest.raises(sandbox.SecurityError):
        sandbox.http_request("GET", "https://random.org/page")  # allow_open_web=False


def test_egress_blocks_mutating_method_on_open_web(configured):
    with pytest.raises(sandbox.SecurityError):
        sandbox.http_request("POST", "https://random.org/x", allow_open_web=True, json={"a": 1})


def test_configured_host_classification(configured):
    # openrouter.ai + api.tavily.com + r.jina.ai + PyPI are configured.
    for h in ("openrouter.ai", "api.tavily.com", "r.jina.ai", "pypi.org", "files.pythonhosted.org"):
        assert h in sandbox._S.configured_hosts


# --- filesystem scope -------------------------------------------------------

def test_fs_write_scope(configured):
    sandbox.check_write("src/x.py")          # allowed (dev/full)
    sandbox.check_write("data/db/note.md")   # allowed (memory)
    with pytest.raises(sandbox.SecurityError):
        sandbox.check_write(".env")          # outside scope
    with pytest.raises(sandbox.SecurityError):
        sandbox.check_write("../escape.txt")  # traversal outside /agent


def test_fs_read_excludes_secrets(configured):
    with pytest.raises(sandbox.SecurityError):
        sandbox.check_read(".env")
    with pytest.raises(sandbox.SecurityError):
        sandbox.check_read("tools/sandbox.py")  # runtime's own files


def test_improve_tools_narrows_src(tmp_path):
    (tmp_path / "src" / "providers").mkdir(parents=True)
    (tmp_path / "src" / "providers" / "openrouter.py").write_text("x", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "dist").mkdir()
    sandbox.configure(_cfg(tmp_path, mode="production", improve="tools"))
    sandbox.check_write("src/providers/openrouter.py")  # existing tool file: ok
    with pytest.raises(sandbox.SecurityError):
        sandbox.check_write("src/agent.py")             # outside providers/tools
    with pytest.raises(sandbox.SecurityError):
        sandbox.check_write("src/providers/new.py")     # cannot create new files
    sandbox.check_write("data/x.md")                    # memory always writable


# --- secret scrub -----------------------------------------------------------

def test_secret_scrub_removes_env_but_keeps_channel(tmp_path, monkeypatch):
    monkeypatch.setenv("FOO_API_KEY", "secret123")
    secrets.load(tmp_path)
    secrets.scrub()
    assert "FOO_API_KEY" not in os.environ          # scrubbed from environment
    assert secrets.get_key("foo") == "secret123"    # still reachable via the channel


# --- installer bounds -------------------------------------------------------

def test_installer_validation():
    assert installer._validate("requests") is None
    assert installer._validate("httpx>=0.27") is None
    assert "approval" in installer._validate("pip")            # restricted set
    assert "approval" in installer._validate("git+https://e/x")  # VCS
    assert installer._validate("-e .")                          # flags rejected
    assert installer._validate("../local")                      # path rejected


# --- governance lock --------------------------------------------------------

def test_governance_lock(tmp_path):
    (tmp_path / "dev-config.yml").write_text(
        "mode: dev\n"
        "llm: {provider: openrouter, model: real/model}\n"
        "limits: {max_steps: 10}\n"
        "tools: {web_search: tavily, web_fetch: jina}\n"
        "web: {user_agent: UA, contact: c}\n"
        "systemPrompt: hi\n", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    # config.yml tries to override governance keys + add its own setting
    (dist / "config.yml").write_text(
        "llm: {provider: HACKED, model: HACKED}\n"
        "limits: {max_cost: 9999}\n"
        "improve: full\n"
        "compaction: {trigger_tokens: 6000}\n", encoding="utf-8")
    cfg = load_config(tmp_path, code_dir=dist)
    assert cfg.llm["provider"] == "openrouter"      # operator wins
    assert cfg.llm["model"] == "real/model"
    assert cfg.limits["max_steps"] == 10
    assert "compaction" in cfg.agent_settings       # agent's own setting kept
    assert "llm" not in cfg.agent_settings          # governance stripped
    assert "limits" not in cfg.agent_settings


# --- audit replay / totals --------------------------------------------------

def test_audit_replay_and_totals(tmp_path):
    log = tmp_path / "agent.log"
    audit.write_header(log, "r-1", "m", {}, "sha256:x", ["fs_write"])
    audit.write_step(log, "r-1", 1, "thinking", [
        {"id": "a1", "tool": "fs_write", "params": {"path": "data/x"}, "result": "wrote", "ok": True}
    ], {"in": 5, "out": 2}, 0.01)
    audit.write_step(log, "r-1", 2, "deploying", [
        {"id": "a2", "tool": "deploy", "params": {}, "result": "deployed: /src→/dist @ abc", "ok": True}
    ], {"in": 1, "out": 1}, 0.02, deploy={"ref": "abc", "score": 2.0, "floor_cost": 0.5})

    totals = audit.session_totals(log)
    assert abs(totals["cost_sum"] - 0.03) < 1e-9
    assert totals["deploys"] == 1
    assert audit.last_deploy_score(log) == 2.0
    assert audit.has_history(log)

    mem = audit.replay_memory(log, "SYS", "GOAL")
    assert mem[0]["content"] == "SYS" and mem[1]["content"] == "GOAL"
    # assistant turn + paired tool reply reconstructed, matched by id
    assert mem[2]["role"] == "assistant" and mem[2]["tool_calls"][0]["id"] == "a1"
    assert mem[3]["role"] == "tool" and mem[3]["tool_call_id"] == "a1"
    # the synthesized deploy observation survives replay (no orphaned tool_call)
    assert any(t.get("content", "").startswith("deployed:") for t in mem if t["role"] == "tool")
