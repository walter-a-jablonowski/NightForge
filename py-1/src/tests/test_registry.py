"""Registry wiring, tool schemas, and the provider interface."""

from pathlib import Path

from tools.config import Config

from .. import registry
from ..providers import openrouter


def _config():
    return Config(
        agent_root=Path("."), code_dir=Path("./dist"), mode="dev",
        llm={"provider": "openrouter", "model": "anthropic/claude-sonnet-4"},
        limits={"max_steps": 50, "max_cost": 5.0, "max_cost_sum": 50.0, "max_deploys": 30},
        improve="full", web={}, tools={"web_search": "tavily", "web_fetch": "jina"},
        system_prompt="sys", instructions="",
    )


def test_tool_specs_valid():
    specs = registry.tool_specs()
    names = set()
    for s in specs:
        assert s["type"] == "function"
        f = s["function"]
        assert f["name"] and f["parameters"]["type"] == "object"
        names.add(f["name"])
    assert {"web_search", "web_fetch", "fs_read", "fs_write", "deploy"} <= names


def test_build_tool_impls_names():
    impls = registry.build_tool_impls(_config())
    assert {"fs_read", "fs_list", "fs_write", "fs_delete",
            "web_search", "web_fetch", "run_tests", "install"} <= set(impls)
    assert "deploy" not in impls  # deploy is driven by the loop, not dispatched


def test_provider_interface():
    llm = registry.build_llm(_config(), api_key=None)
    # context_window is a property (so the smoke floor can check it without a call)
    assert isinstance(type(llm).context_window, property)
    n = llm.count_tokens([{"role": "user", "content": "hello world"}])
    assert isinstance(n, int) and n > 0


def test_count_tokens_estimate_grows_with_content():
    llm = openrouter.OpenRouterProvider("m", api_key=None)
    small = llm.count_tokens([{"role": "user", "content": "hi"}])
    large = llm.count_tokens([{"role": "user", "content": "hi" * 1000}])
    assert large > small
