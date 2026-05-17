"""
Tests for pipeline/tools.py — Tool definition and ToolRegistry.
Does not invoke tools that make real API or HuggingFace calls.
"""

import pytest

from pipeline.tools import Tool, ToolRegistry


def _default_func(**kwargs):
    return {"status": "ok", **kwargs}


def _make_tool(name: str = "test_tool", func=None) -> Tool:
    if func is None:
        func = _default_func
    return Tool(
        name          = name,
        description   = f"Test tool: {name}",
        agent         = "TestAgent",
        input_schema  = {"type": "object", "properties": {"x": {"type": "integer"}}},
        output_schema = {"type": "object", "properties": {"status": {"type": "string"}}},
        func          = func,
    )


class TestTool:
    def test_invoke_calls_func(self):
        tool = _make_tool(func=lambda x: {"doubled": x * 2})
        result = tool.invoke(x=5)
        assert result == {"doubled": 10}

    def test_invoke_propagates_exception(self):
        def bad_func():
            raise ValueError("intentional failure")
        tool = _make_tool(func=bad_func)
        with pytest.raises(ValueError, match="intentional failure"):
            tool.invoke()

    def test_invoke_with_audit_log_on_success(self):
        from pipeline.governance import AuditLog
        audit = AuditLog()
        tool = _make_tool(func=lambda x: {"result": x})
        tool.invoke(audit_log=audit, x=1)
        assert audit.summary()["by_type"].get("tool_call", 0) == 1

    def test_invoke_with_audit_log_on_failure(self):
        from pipeline.governance import AuditLog
        audit = AuditLog()
        tool = _make_tool(func=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        with pytest.raises(RuntimeError):
            tool.invoke(audit_log=audit)
        assert audit.summary()["by_type"].get("tool_call", 0) == 1

    def test_invoke_without_audit_log_still_works(self):
        tool = _make_tool(func=lambda: {"ok": True})
        result = tool.invoke()
        assert result == {"ok": True}


class TestToolRegistry:
    def test_empty_registry_list(self):
        registry = ToolRegistry()
        assert registry.list() == []

    def test_register_and_list(self):
        registry = ToolRegistry()
        registry.register(_make_tool("tool_a"))
        registry.register(_make_tool("tool_b"))
        assert set(registry.list()) == {"tool_a", "tool_b"}

    def test_get_registered_tool(self):
        registry = ToolRegistry()
        tool = _make_tool("my_tool")
        registry.register(tool)
        assert registry.get("my_tool") is tool

    def test_get_unknown_raises_key_error(self):
        registry = ToolRegistry()
        with pytest.raises(KeyError, match="not found"):
            registry.get("nonexistent")

    def test_invoke_calls_registered_tool(self):
        registry = ToolRegistry()
        registry.register(_make_tool("doubler", func=lambda x: {"result": x * 2}))
        result = registry.invoke("doubler", x=7)
        assert result == {"result": 14}

    def test_invoke_unknown_raises_key_error(self):
        registry = ToolRegistry()
        with pytest.raises(KeyError):
            registry.invoke("nonexistent")

    def test_manifest_structure(self):
        registry = ToolRegistry()
        registry.register(_make_tool("tool_a"))
        registry.register(_make_tool("tool_b"))
        manifest = registry.manifest()
        assert len(manifest) == 2
        for entry in manifest:
            assert "name"          in entry
            assert "description"   in entry
            assert "agent"         in entry
            assert "input_schema"  in entry
            assert "output_schema" in entry

    def test_manifest_contains_all_registered(self):
        registry = ToolRegistry()
        names = ["alpha", "beta", "gamma"]
        for name in names:
            registry.register(_make_tool(name))
        manifest_names = {t["name"] for t in registry.manifest()}
        assert set(names) == manifest_names

    def test_register_overwrites_same_name(self):
        registry = ToolRegistry()
        registry.register(_make_tool("tool", func=lambda: {"v": 1}))
        registry.register(_make_tool("tool", func=lambda: {"v": 2}))
        result = registry.invoke("tool")
        assert result == {"v": 2}


class TestGlobalRegistry:
    """Verify the module-level REGISTRY singleton has all expected tools pre-registered."""

    def test_global_registry_has_fetch_transcripts(self):
        from pipeline.tools import REGISTRY
        assert "fetch_transcripts" in REGISTRY.list()

    def test_global_registry_has_score_extraction(self):
        from pipeline.tools import REGISTRY
        assert "score_extraction" in REGISTRY.list()

    def test_global_registry_has_compute_kpis(self):
        from pipeline.tools import REGISTRY
        assert "compute_kpis" in REGISTRY.list()

    def test_global_registry_has_generate_insights(self):
        from pipeline.tools import REGISTRY
        assert "generate_insights" in REGISTRY.list()

    def test_global_registry_has_export_results(self):
        from pipeline.tools import REGISTRY
        assert "export_results" in REGISTRY.list()

    def test_global_registry_manifest_is_llm_discoverable(self):
        from pipeline.tools import REGISTRY
        manifest = REGISTRY.manifest()
        # Every tool must have a description and JSON Schema for LLM discoverability
        for tool in manifest:
            assert len(tool["description"]) > 10, f"Tool {tool['name']} needs a description"
            assert "type" in tool["input_schema"], f"Tool {tool['name']} needs a typed input_schema"
