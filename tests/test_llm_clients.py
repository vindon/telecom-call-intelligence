"""
Tests for pipeline/llm_clients.py — the single seam for constructing
Anthropic/Gemini/NVIDIA clients. Verifies the missing-API-key contract
(raise OSError) and that the timeout/max_retries policy is actually
applied, without making real network calls.
"""

import pytest

from pipeline import llm_clients


class TestGetAnthropicClient:
    def test_missing_key_raises_oserror(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(OSError, match="ANTHROPIC_API_KEY"):
            llm_clients.get_anthropic_client(60)

    def test_applies_timeout_and_max_retries(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-dummy")
        client = llm_clients.get_anthropic_client(42)
        assert client.timeout == 42
        assert client.max_retries == 1


class TestGetGeminiClient:
    def test_missing_key_raises_oserror(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(OSError, match="GEMINI_API_KEY"):
            llm_clients.get_gemini_client(60)

    def test_constructs_with_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-dummy")
        client = llm_clients.get_gemini_client(30)
        assert client is not None


class TestGetNvidiaClient:
    def test_missing_key_raises_oserror(self, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        with pytest.raises(OSError, match="NVIDIA_API_KEY"):
            llm_clients.get_nvidia_client(45)

    def test_applies_timeout_max_retries_and_base_url(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "test-key-dummy")
        client = llm_clients.get_nvidia_client(45)
        assert client.timeout == 45
        assert client.max_retries == 1
        assert str(client.base_url).startswith("https://integrate.api.nvidia.com")
