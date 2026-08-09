"""GatewayLLMProvider tests (B8-4 gateway main path)."""

from __future__ import annotations

import json
from unittest import mock

import pytest

from core.agent.llm_providers.gateway_provider import GatewayLLMProvider
from core.agent.llm_providers.base import GenerateRequest


class FakeResp:
    def __init__(self, status=200, data=None):
        self.status = status
        self._data = data or {}

    def json(self):
        return self._data

    def read(self):
        return json.dumps(self._data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def _no_env_key(monkeypatch):
    monkeypatch.delenv("SWITCH_GATEWAY_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


class TestConstruction:
    def test_config_path(self):
        p = GatewayLLMProvider("gw", {
            "base_url": "http://gw:8080",
            "default_provider": "deepseek",
            "default_model": "deepseek-chat",
        })
        assert p._base_url == "http://gw:8080"
        assert p._default_provider == "deepseek"
        assert p._default_model == "deepseek-chat"

    def test_kwargs_path(self):
        p = GatewayLLMProvider(base_url="http://127.0.0.1:8080")
        assert p._base_url == "http://127.0.0.1:8080"

    def test_default_api_key_dm_client(self):
        p = GatewayLLMProvider(base_url="http://127.0.0.1:8080")
        assert p._api_key == "dm-client"

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("SWITCH_GATEWAY_KEY", "prod-dm")
        p = GatewayLLMProvider(base_url="http://127.0.0.1:8080")
        assert p._api_key == "prod-dm"


class TestHealthCheck:
    def test_healthy(self):
        p = GatewayLLMProvider(base_url="http://127.0.0.1:8080")
        with mock.patch.object(p, "_get", return_value={"status": "healthy"}):
            assert p.health_check() is True

    def test_degraded_still_healthy(self):
        p = GatewayLLMProvider(base_url="http://127.0.0.1:8080")
        with mock.patch.object(p, "_get", return_value={"status": "degraded"}):
            assert p.health_check() is True

    def test_down(self):
        p = GatewayLLMProvider(base_url="http://127.0.0.1:8080")
        with mock.patch.object(p, "_get", side_effect=RuntimeError("conn refused")):
            assert p.health_check() is False

    def test_urllib_fallback_path(self):
        p = GatewayLLMProvider(base_url="http://127.0.0.1:8080")
        p._client = None
        with mock.patch.object(p, "_ensure_client", side_effect=lambda: None):
            with mock.patch("urllib.request.urlopen",
                            return_value=FakeResp(200, {"status": "healthy"})) as m:
                assert p.health_check() is True
                req = m.call_args.args[0]
                assert req.full_url == "http://127.0.0.1:8080/v1/health"


class TestGenerate:
    def _provider(self, **kw):
        cfg = {"base_url": "http://127.0.0.1:8080",
               "default_provider": "deepseek",
               "default_model": "deepseek-chat"}
        cfg.update(kw)
        return GatewayLLMProvider("gw", cfg)

    def test_generate_success(self):
        p = self._provider()
        resp = {
            "choices": [{"message": {"content": "hello from dialogmesh"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "model": "deepseek-chat",
        }
        with mock.patch.object(p, "_post", return_value=resp) as m:
            result = p.generate(GenerateRequest(prompt="hi"))
            assert result.metrics.success is True
            assert "dialogmesh" in result.text
            assert result.metrics.provider_name == "deepseek"
            assert result.metrics.model_id == "deepseek-chat"
            args, _ = m.call_args
            assert args[0] == "/v1/chat/completions"
            assert args[2] == "deepseek"

    def test_generate_reasoning_fallback(self):
        p = self._provider()
        resp = {
            "choices": [{"message": {"reasoning_content": "thinking...",
                                     "content": ""}}],
            "usage": {},
        }
        with mock.patch.object(p, "_post", return_value=resp):
            result = p.generate(GenerateRequest(prompt="deep question"))
            assert "thinking" in result.text

    def test_generate_error(self):
        p = self._provider()
        with mock.patch.object(p, "_post", side_effect=RuntimeError("upstream 500")):
            result = p.generate(GenerateRequest(prompt="hi"))
            assert result.metrics.success is False
            assert "[Gateway Error" in result.text

    def test_generate_json_format(self):
        p = self._provider()
        resp = {"choices": [{"message": {"content": '{"ok": true}'}}], "usage": {}}
        with mock.patch.object(p, "_post", return_value=resp) as m:
            p.generate(GenerateRequest(prompt="json pls", response_format="json"))
            args, _ = m.call_args
            body = args[1]
            assert body["response_format"] == {"type": "json_object"}


class TestListProviders:
    def test_list(self):
        p = GatewayLLMProvider(base_url="http://127.0.0.1:8080")
        providers = [{"name": "deepseek"}, {"name": "lmstudio"}]
        with mock.patch.object(p, "_get", return_value={"providers": providers}):
            assert p.list_providers() == providers

    def test_list_error_returns_empty(self):
        p = GatewayLLMProvider(base_url="http://127.0.0.1:8080")
        with mock.patch.object(p, "_get", side_effect=RuntimeError("down")):
            assert p.list_providers() == []
