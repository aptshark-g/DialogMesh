"""P5: ChromaDB vector query integration test."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

def test_chromadb_add_search():
    """Verify ChromaDB can add and search semantic objects."""
    from core.agent.event.pluggable import ChromaBridge
    import tempfile
    tmp = tempfile.mkdtemp()
    try:
        cb = ChromaBridge(persist_dir=tmp)
        if not cb.available:
            return

        assert cb.add("obj_1", "JWT认证是一种无状态的身份验证方案")
        assert cb.add("obj_2", "OAuth2授权框架支持第三方登录")
        assert cb.add("obj_3", "PostgreSQL数据库使用事务保证ACID")

        results = cb.search("认证", limit=2)
        assert len(results) > 0, "No results for '认证'"
        assert any("JWT" in str(r) for r in results)

        assert cb.count() >= 3
        cb.close()
    finally:
        import shutil
        try: shutil.rmtree(tmp)
        except: pass


def test_chromadb_count():
    """Verify count returns real number."""
    from core.agent.event.pluggable import ChromaBridge
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        cb = ChromaBridge(persist_dir=tmp)
        assert cb.count() >= 0  # 0 if empty, >0 if previous test ran


def test_nats_bridge_graceful():
    """Verify NATS bridge gracefully handles unavailable server."""
    from core.agent.event.pluggable import NATSBridge
    nb = NATSBridge()
    # Should not crash — just report unavailable
    assert isinstance(nb.available, bool)
    # bridge methods should return False/None without crashing
    import asyncio
    async def _test():
        ok = await nb.connect()
        assert ok is False  # No server running
        pub = await nb.publish("test", {})
        assert pub is False
    asyncio.run(_test())


def test_otel_bridge_graceful():
    """Verify OTel bridge doesn't crash when dependencies missing."""
    from core.agent.event.pluggable import OTelBridge
    ob = OTelBridge()
    span = ob.start_span("test")
    # May be None if not installed, or a valid span if installed
    assert span is None or hasattr(span, 'set_attribute')
    ob.record_trace("test", 10.0, True)  # Should not crash
