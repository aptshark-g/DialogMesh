# -*- coding: utf-8 -*-
"""PCR stanza 离线回归（2026-08-16 修）:

原 `_get_stanza` 调 `stanza.download('zh')` —— 网络受限时无 CPU 挂起
（实测 faulthandler 40s 杀进程; 与 170s 卡死同源）。修复后 download_method
=None（只读缓存, 缺失快速失败）, 单元降级走下一确定性单元。
"""

from __future__ import annotations

import time
import unittest

from core.agent.pcr_router_v2 import PCRRouterV2


class TestPCRStanzaOffline(unittest.TestCase):
    def test_get_stanza_never_downloads(self):
        """回归: stanza.download 绝不允许被调用（离线挂网源）。"""
        orig_download = None
        try:
            import stanza
            orig_download = stanza.download

            def _boom(*a, **k):
                raise AssertionError(
                    "stanza.download must not be called (offline hang source)")
            stanza.download = _boom
        except ImportError:
            pass
        try:
            key = "zz_never_cached"
            t0 = time.time()
            nlp = PCRRouterV2._get_stanza(key)
            self.assertIsNone(nlp)  # 缺失模型快速失败, 不联网
            self.assertLess(time.time() - t0, 5)
        finally:
            if orig_download is not None:
                import stanza
                stanza.download = orig_download
            if hasattr(PCRRouterV2, f"_stanza_nlp_{key}"):
                delattr(PCRRouterV2, f"_stanza_nlp_{key}")

    def test_svo_nomic_degrades_fast(self):
        """SVO 单元在无 stanza 模型时快速返回 None（不阻塞 x 轴）。"""
        # 用 None sf → 首行直接返回（不触发 stanza）; 验证路径安全
        t0 = time.time()
        v = PCRRouterV2._distance_svo_nomic("Hello world", None)
        self.assertLess(time.time() - t0, 5)
        self.assertIsNone(v)


if __name__ == "__main__":
    unittest.main()
