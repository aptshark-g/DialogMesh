# 根因分析

Gateway 500 只有两个可能:
1. routing pool empty → `getRoutingProvider()` returns ""
2. `manager.Generate()` throws → `err != nil` → route 500 path

**不会去查日志就不会解决问题。加监控。**
