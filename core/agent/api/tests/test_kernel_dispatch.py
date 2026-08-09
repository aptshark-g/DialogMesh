"""M8 B4-5 测试 — 命令内核（CLI/REST 共用）+ REST 对齐。

验证:
  1. kernel_* 函数返回真实数据（无硬编码假值）。
  2. stubs_api 端点转发内核（无 stub 假数据）。
  3. CLI 假执行点已消（decider/eventlog/memory/format 等）。
"""

import json
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def engine():
    from core.agent.cli.engine import start_engine, stop_engine
    r = start_engine(provider_type="mock")
    assert r["status"] == "running"
    yield
    stop_engine()


@pytest.fixture()
def client():
    # 每个测试独立会话 — 避开服务中间件 anonymous 桶 burst=20 限流
    from fastapi.testclient import TestClient
    from core.agent.api.v6_app import app
    return TestClient(app, headers={"X-Session-Id": f"test-{uuid.uuid4().hex[:12]}"})


# ── 1. 内核函数真实数据 ─────────────────────────────────────── #

class TestKernelReal:
    def test_engine_status(self, engine):
        from core.agent.kernel import kernel_engine_status
        st = kernel_engine_status()
        assert st.get("running") is True
        assert st.get("subsystems_loaded", 0) >= 32

    def test_profile_real(self, engine):
        from core.agent.kernel import kernel_profile
        p = kernel_profile()
        assert "oceAN_dims" in p
        assert isinstance(p["oceAN_dims"], dict)
        assert p["oceAN_dims"]  # 真实维度，非空
        assert isinstance(p["turn_count"], int)

    def test_mind_real(self, engine):
        from core.agent.kernel import kernel_mind
        m = kernel_mind()
        assert "modules_available" in m
        assert len(m["modules_available"]) >= 5
        assert "current_phase" in m

    def test_pipeline_real(self, engine):
        from core.agent.kernel import kernel_pipeline
        p = kernel_pipeline()
        assert p.get("running") is True
        assert "phases" in p

    def test_metrics_real(self, engine):
        from core.agent.kernel import kernel_metrics
        m = kernel_metrics()
        assert m["subsystems_loaded"] > 0
        assert m["subsystems_total"] > 0

    def test_graph_real(self, engine):
        from core.agent.kernel import kernel_graph
        g = kernel_graph()
        assert "nodes" in g and "edges" in g
        assert isinstance(g["nodes"], list)

    def test_relations_no_fake(self, engine):
        from core.agent.kernel import kernel_relations
        r = kernel_relations()
        # 之前硬编码 "patterns" 固定值保留，但 edge_count 必须是数字且无 "stub"
        assert "edge_count" in r
        assert isinstance(r["edge_count"], int)

    def test_decider_execute_real(self, engine):
        from core.agent.kernel import kernel_decider_execute
        r = kernel_decider_execute("test execute")
        assert r.get("executed") is True
        assert "phases" in r or "result" in r

    def test_eventlog_stats(self, engine):
        from core.agent.kernel import kernel_eventlog_stats
        s = kernel_eventlog_stats()
        assert "total" in s and "by_kind" in s

    def test_memory_stats(self, engine):
        from core.agent.kernel import kernel_memory_stats
        s = kernel_memory_stats()
        assert set(s.keys()) >= {"hot", "warm", "cold"}

    def test_format_encode(self, engine):
        from core.agent.kernel import kernel_format_encode
        r = kernel_format_encode({"a": 1})
        assert r["encoded"]
        assert r["tokens"] >= 0


# ── 2. REST 端点转发内核（消假数据）─────────────────────────── #

class TestRestAligned:
    def test_profile_endpoint(self, client, engine):
        r = client.get("/v6/profile")
        assert r.status_code == 200
        data = r.json()
        assert "oceAN_dims" in data
        assert data["oceAN_dims"]

    def test_trace_endpoint(self, client, engine):
        r = client.get("/v6/trace")
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) >= {"reason_distribution", "avg_confidence", "total"}

    def test_rules_endpoint(self, client, engine):
        r = client.get("/v6/rules")
        assert r.status_code == 200
        data = r.json()
        assert "rules" in data and "total" in data
        assert isinstance(data["rules"], list)

    def test_relations_endpoint(self, client, engine):
        r = client.get("/v6/relations")
        assert r.status_code == 200
        assert "edge_count" in r.json()

    def test_behavior_endpoint(self, client, engine):
        r = client.get("/v6/behavior")
        assert r.status_code == 200
        data = r.json()
        assert "edge_count" in data

    def test_engineering_modules_endpoint(self, client, engine):
        r = client.get("/v6/engineering/modules")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data.get("modules"), list)
        assert data.get("total", 0) > 0

    def test_pipeline_endpoint(self, client, engine):
        r = client.get("/v6/pipeline")
        assert r.status_code == 200
        data = r.json()
        assert data.get("running") is True
        assert "phases" in data

    def test_metrics_endpoint(self, client, engine):
        r = client.get("/v6/metrics")
        assert r.status_code == 200
        data = r.json()
        assert data["subsystems_loaded"] > 0

    def test_meta_stats_endpoint(self, client, engine):
        r = client.get("/v6/meta/stats")
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) >= {"queue_size", "pending", "reviewed"}

    def test_sessions_endpoint(self, client, engine):
        r = client.get("/v6/sessions")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_parameters_endpoint_real(self, client, engine):
        r = client.get("/v6/parameters")
        assert r.status_code == 200
        data = r.json()
        # 之前 pipeline_api 返回 {"parameters": {}, "namespaces": []}
        # 内核版本返回 V6ParameterItem 结构
        assert "parameters" in data
        assert "total" in data

    def test_context_endpoint_real(self, client, engine):
        r = client.get("/v6/context")
        assert r.status_code == 200
        data = r.json()
        # 之前 pipeline_api 硬编码 {"context": {"assembler": "active"...}}
        # 内核版本返回 {"intent_category": ..., "entries": [...]}
        assert "entries" in data

    def test_annotate_endpoint_real(self, client, engine):
        r = client.get("/v6/annotate")
        assert r.status_code == 200
        data = r.json()
        assert "annotations" in data

    def test_annotate_stats_contract(self, client, engine):
        r = client.get("/v6/annotate/stats")
        assert r.status_code == 200
        data = r.json()
        # 前端契约: by_author / by_date 必须存在
        assert "by_author" in data
        assert "by_date" in data

    def test_gateway_providers_no_fake(self, client, engine):
        r = client.get("/v6/gateway/providers")
        assert r.status_code == 200
        data = r.json()
        # api_gateway 真实代理: 返回 providers 列表（含 builtin 兜底）
        assert "providers" in data
        assert isinstance(data["providers"], list)

    # ── B4-5-P2 缺口补齐端点 ──────────────────────────────── #

    def test_behavior_feedback_endpoint(self, client, engine):
        r = client.post("/v6/behavior/feedback",
                        json={"pattern_id": "__test__", "correct": True})
        assert r.status_code == 200
        assert "updated" in r.json()

    def test_causal_chain_endpoint(self, client, engine):
        r = client.get("/v6/causal-chain")
        assert r.status_code == 200
        data = r.json()
        assert "chain" in data and "avg_chain_length" in data

    def test_context_config_endpoint(self, client, engine):
        r = client.put("/v6/context/config", json={"token_budget": 4000})
        assert r.status_code == 200
        data = r.json()
        assert "updated" in data and "count" in data

    def test_engineering_constraints_endpoint(self, client, engine):
        r = client.put("/v6/engineering/constraints",
                       json={"name": "test", "action": "add_constraint",
                             "constraint": "must be safe"})
        assert r.status_code == 200
        data = r.json()
        assert "updated" in data

    def test_meta_scan_endpoint(self, client, engine):
        r = client.post("/v6/meta/scan")
        assert r.status_code == 200
        assert "triggered" in r.json()

    def test_meta_retrospect_endpoint(self, client, engine):
        r = client.post("/v6/meta/retrospect", params={"target": "parameters"})
        assert r.status_code == 200
        data = r.json()
        assert "delta" in data and "verdict" in data

    def test_ocean_params_endpoint(self, client, engine):
        r = client.post("/v6/ocean/params")
        assert r.status_code == 200
        data = r.json()
        assert "applied" in data and "ocean" in data

    def test_profile_corrections_review_endpoint(self, client, engine):
        r = client.post("/v6/profile/corrections/review", json=[])
        assert r.status_code == 200
        assert "reviewed" in r.json()

    def test_providers_test_endpoint(self, client, engine):
        r = client.post("/v6/providers/test")
        assert r.status_code == 200
        data = r.json()
        assert "healthy" in data and "latency_ms" in data

    def test_sync_endpoint(self, client, engine):
        r = client.get("/v6/sync")
        assert r.status_code == 200
        assert "status" in r.json()

    def test_ttl_tick_endpoint(self, client, engine):
        r = client.post("/v6/ttl/tick")
        assert r.status_code == 200
        data = r.json()
        assert "promoted" in data and "demoted" in data

    def test_versions_rollback_endpoint(self, client, engine):
        r = client.post("/v6/versions/profile/rollback",
                        json={"commit_id": "__none__"})
        assert r.status_code == 200
        assert "rolled_back" in r.json()

    def test_versions_by_category_endpoint(self, client, engine):
        r = client.get("/v6/versions/profile")
        assert r.status_code == 200
        data = r.json()
        assert "commits" in data and "target" in data

    def test_v1_health_endpoint(self, client, engine):
        r = client.get("/v1/health")
        assert r.status_code == 200
        assert "status" in r.json()

    def test_v4_status_endpoint(self, client, engine):
        r = client.get("/v4/status")
        assert r.status_code == 200
        assert "running" in r.json()

    def test_v4_checkpoint_endpoint(self, client, engine):
        r = client.post("/v4/checkpoint")
        assert r.status_code == 200
        assert "status" in r.json()

    def test_v4_inspect_endpoint(self, client, engine):
        r = client.get("/v4/inspect/context")
        assert r.status_code == 200
        assert "module" in r.json()


# ── 3. CLI 假执行点已消 ─────────────────────────────────────── #

class TestCliNoFake:
    def _capture(self, fn, args):
        import io as _io
        from contextlib import redirect_stdout
        buf = _io.StringIO()
        with redirect_stdout(buf):
            fn(args)
        return json.loads(buf.getvalue())

    def test_decider_execute_real(self, engine):
        from core.agent.cli.commands.blueprint_cmd import cmd_decider_execute
        from argparse import Namespace
        r = self._capture(cmd_decider_execute, Namespace(text=["hello"]))
        assert r.get("executed") is True
        assert "phases" in r

    def test_format_encode_real(self, engine):
        from core.agent.cli.commands.p9_cmd import cmd_format_encode
        from argparse import Namespace
        r = self._capture(cmd_format_encode, Namespace(data={"x": 1}, fmt=None))
        assert r.get("encoded")
        assert "not yet implemented" not in str(r)

    def test_eventlog_stats_real(self, engine):
        from core.agent.cli.commands.p9_cmd import cmd_eventlog_stats
        from argparse import Namespace
        r = self._capture(cmd_eventlog_stats, Namespace())
        assert "total" in r
        assert "not yet implemented" not in str(r)

    def test_memory_stats_real(self, engine):
        from core.agent.cli.commands.p9_cmd import cmd_memory_stats
        from argparse import Namespace
        r = self._capture(cmd_memory_stats, Namespace())
        assert set(r.keys()) >= {"hot", "warm", "cold"}

    def test_discourse_compress_real(self, engine):
        from core.agent.cli.commands.p9_cmd import cmd_discourse_compress
        from argparse import Namespace
        r = self._capture(cmd_discourse_compress, Namespace())
        assert "not yet implemented" not in str(r)

    def test_rules_delete_real(self, engine):
        from core.agent.cli.commands.p5_cmd import cmd_rules_delete
        from argparse import Namespace
        r = self._capture(cmd_rules_delete, Namespace(rule_id="__nonexistent__"))
        # 真实路径返回 deleted False（找不到），不再是 "deletion queued"
        assert "deleted" in r
        assert "queued" not in str(r)
