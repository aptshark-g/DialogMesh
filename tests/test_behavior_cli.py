"""Behavior chain CLI white-box (A19): dm behavior / dm commitment."""
import argparse
import io
import json
from contextlib import redirect_stdout

import pytest

from core.agent.behavior.brain import BehaviorBrain
from core.agent.behavior.graph_store import BehaviorGraph
from core.agent.behavior.models import BehaviorStep


class _StubEngine:
    def __init__(self):
        g = BehaviorGraph()
        s1 = BehaviorStep("c1", "write code", "code")
        s2 = BehaviorStep("c2", "run tests", "test")
        g.add_step(s1)
        g.add_step(s2)
        for _ in range(5):
            g.record_edge(s1, s2, success=True)
        self._behavior_brain = BehaviorBrain(graph=g, llm_provider=None)


@pytest.fixture(autouse=True)
def _stub_engine(monkeypatch):
    import core.agent.cli.engine as ce
    import core.agent.cli.commands.behavior_cmd as bc
    engine = _StubEngine()
    monkeypatch.setattr(ce, "get_engine", lambda: engine)
    # behavior_cmd binds get_engine at module import time — patch it too so
    # each test gets its own isolated engine.
    monkeypatch.setattr(bc, "get_engine", lambda: engine)
    return engine


def _run_cmd(fn, **kwargs):
    args = argparse.Namespace(**kwargs)
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(args)
    return json.loads(buf.getvalue())


def test_behavior_show():
    from core.agent.cli.commands.behavior_cmd import cmd_behavior
    out = _run_cmd(cmd_behavior, subcommand="show")
    assert out["ready"] is True
    assert out["graph"]["nodes"] == 2


def test_behavior_predict():
    from core.agent.cli.commands.behavior_cmd import cmd_behavior
    out = _run_cmd(cmd_behavior, subcommand="predict")
    assert out["predicted_top1"] == "run tests"
    assert "scheduler" in out


def test_behavior_graph():
    from core.agent.cli.commands.behavior_cmd import cmd_behavior
    out = _run_cmd(cmd_behavior, subcommand="graph")
    assert out["nodes"] == 2
    assert out["edges"] == 1
    assert out["recent_chain"][0]["action"] == "write code"


def test_behavior_config_list_and_set():
    from core.agent.cli.commands.behavior_cmd import cmd_behavior
    out = _run_cmd(cmd_behavior, subcommand="config", key=None, value=None)
    assert "behavior.scheduler_ci_converged" in out
    set_out = _run_cmd(
        cmd_behavior, subcommand="config",
        key="behavior.scheduler_ci_converged", value="0.2",
    )
    assert set_out["set"] == "behavior.scheduler_ci_converged"
    assert set_out["value"] == 0.2


def test_commitment_add_list_match(_stub_engine):
    from core.agent.cli.commands.behavior_cmd import cmd_commitment
    add = _run_cmd(
        cmd_commitment, subcommand="add",
        when="when user says deploy", should="run tests first",
        rather_than="", because="",
    )
    assert add["status"] == "ok"
    cid = add["added"]["id"]
    lst = _run_cmd(cmd_commitment, subcommand="list", status=None)
    assert lst["stats"]["total"] == 1
    match = _run_cmd(
        cmd_commitment, subcommand="match", text="user says deploy now",
    )
    assert len(match["blocks"]) == 1
    assert match["blocks"][0]["commitment_id"] == cid


def test_commitment_lifecycle_cmds(_stub_engine):
    from core.agent.cli.commands.behavior_cmd import cmd_commitment
    add = _run_cmd(
        cmd_commitment, subcommand="add",
        when="w1", should="s1", rather_than="", because="",
    )
    cid = add["added"]["id"]
    for sub in ("arm", "fire", "complete"):
        out = _run_cmd(cmd_commitment, subcommand=sub, id=cid)
        assert out["status"] == "ok"
    assert _stub_engine._behavior_brain.commitments.get(cid).status == "done"


def test_behavior_distill(_stub_engine):
    from core.agent.cli.commands.behavior_cmd import cmd_behavior
    out = _run_cmd(
        cmd_behavior, subcommand="distill",
        min_sample=3, min_success=0.7,
    )
    assert len(out["distilled"]) >= 1
    assert out["distilled"][0]["source"] == "distilled"
    assert out["distilled"][0]["should"] == "run tests"


def test_cli_registration():
    from core.agent.cli.commands import register_all
    parser = argparse.ArgumentParser()
    sp = parser.add_subparsers()
    register_all(sp)
    names = sorted(sp.choices.keys())
    assert "behavior" in names
    assert "commitment" in names
