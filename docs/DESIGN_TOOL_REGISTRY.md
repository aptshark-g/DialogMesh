# Tool Registry — 动态工具发现与注册

> v2.0 | 2026-07-28 | 状态: 设计评审
> 三级自主: 直接调 → 自动装 → 自写工具。task_graph 记录真实执行轨迹

---

## 一、定位

```
当前: Pipeline(pcr→intent→profile→llm_reply) — LLM 只在最后一环出现
目标: LLM 作为协调者，自选工具，自判不足，自动扩容
```

对比行业成熟方案:

| | OpenAI Function Calling | LangChain Tools | CrewAI Tools | **我们的** |
|---|---|---|---|---|
| 工具注册 | 手动 `tools=[...]` | 手动 `@tool` | 手动 `@tool` | **自动发现 + 懒加载** |
| LLM 选工具 | ✅ | ✅ | ✅ | ✅ |
| 缺失工具 | ❌ 报错 | ❌ 报错 | ❌ 报错 | **自动 pip install + 注册** |
| 执行记录 | 无 | callback | callback | **task_graph 记录** |
| 注册方式 | 代码 | 装饰器 | 装饰器 | **Skill 描述 + 3 行注册** |

---

## 二、三级自主能力

**真正的 agent 不是"调工具"，是"工具不够自己写"**。

```
Level 1: 工具已注册 → 直接调用
         arxiv_search ✓ → execute()
         耗时: < 1s

Level 2: 工具不存在 → 自动安装
         ocr_extract ✗ → pip install paddleocr → 注册 → execute()
         耗时: ~30s

Level 3: 不存在且装不了 → LLM 自写工具
         web_fetch 被 403 → "我来写一个绕过反爬的爬虫"
         → 生成 Python ToolAdapter 代码
         → sandbox 编译检查
         → 注册 → execute()
         → 如果成功: 持久化为可重用 Skill + 规则
         → 如果失败: 告知用户 "需要你帮忙写 X 工具"
         耗时: ~60s (LLM 生成代码 + 测试)
```

### Level 3 流程详解

```
用户: "帮我从这个网站爬取表格数据 www.example.com/data"
  ↓
web_fetch("www.example.com/data") → 失败: 403, 疑似反爬
  ↓
LLM 诊断: "该站点有 Cloudflare 保护, 通用爬虫无法抓取。我来写专用提取器。"
  ↓
LLM 生成代码:
  ```python
  class ExampleExtractor(ToolAdapter):
      name = "example_table_extractor"
      description = "绕过 www.example.com 反爬保护, 提取表格数据"
      category = "web"
      dependencies = ["requests", "beautifulsoup4"]
      input_schema = {"url": "string"}

      def execute(self, url, **kwargs):
          import requests, re
          from bs4 import BeautifulSoup
          session = requests.Session()
          session.headers.update({
              "User-Agent": "Mozilla/5.0 ...",
              "Accept": "text/html,application/xhtml+xml",
              "Referer": "https://www.google.com/"
          })
          # 先访问首页获取 cookie
          session.get("https://www.example.com")
          # 再请求目标页面
          resp = session.get(url, timeout=15)
          soup = BeautifulSoup(resp.text, "html.parser")
          tables = []
          for table in soup.find_all("table"):
              rows = [[td.get_text(strip=True) for td in row.find_all(["td","th"])]
                      for row in table.find_all("tr")]
              tables.append(rows)
          return ToolResult(tool_name=self.name, success=True, data=tables, ...)
  ```
  ↓
Sandbox 验证:
  1. ast.parse() 语法检查 ✓
  2. 无禁止 import (os.system, subprocess, ...) ✓
  3. 静态分析: 无死循环/递归 ✓
  4. 注册到 ToolRegistry
  ↓
execute("www.example.com/data") → 成功返回表格数据 ✓
  ↓
持久化:
  ├── tools/generated/example_table_extractor.py  (可重用)
  └── TriggerRule(domain="example.com", action="blocked",
                   fallback="example_table_extractor")
  ↓
task_graph 记录:
  {"id":"2", "name":"自写爬虫绕过反爬",
   "tool":"example_table_extractor",
   "status":"completed",
   "custom_code": true, "lines": 47, "latency_ms": 3200}
```

### 与用户交互

```
LLM 无法自写时:
  "我无法自动处理 www.example.com 的数据抓取:
   1. 网站使用了自定义 Canvas 渲染, 无法用静态解析
   2. 需要的解决方案: Puppeteer + 用户登录态
   
   建议: 你可以写一个 getExampleData() 函数, 我来帮你注册为工具。
   格式: class YourTool(ToolAdapter): name=... description=... def execute(...)"
```

---

## 三、架构

```
┌─────────────────────────────────────────────────────────┐
│                    LLM (协调者)                           │
│  "查 arxiv 最新 RLHF 论文, 下载 PDF, 提取摘要"           │
│         ↓ 自检工具箱                                     │
│  arxiv_search ✓   pdf_download ✗   ocr_extract ✗       │
│         ↓                        ↓ 自动安装              │
│  直接调用              pip install arxiv pymupdf          │
│         ↓                    ↓ ToolRegistry.register()  │
│  ToolResult → context                    ↓               │
│         ↓                          直接调用              │
│  LLM 汇总 → reply + task_graph ─────────────────→ 前端  │
└─────────────────────────────────────────────────────────┘

ToolRegistry
  ├── discover(query) → [匹配的工具列表]
  ├── resolve(name)  → 工具实例 (不存在则自动发现+安装)
  ├── execute(name, args) → ToolResult
  ├── status()       → 所有已注册工具
  └── map: str → ToolAdapter
```

---

## 三、ToolAdapter — 工具抽象

```python
@dataclass
class ToolAdapter:
    name: str                    # "arxiv_search"
    description: str             # LLM 用来判断是否匹配的自然语言描述
    category: str                # "search" | "file" | "parse" | "compute" | "code"
    dependencies: List[str]      # Python 包名 (自动 pip install)
    handler: Callable            # 实际执行函数
    input_schema: dict           # JSON Schema (给 LLM 看)
    enabled: bool = True
    auto_install: bool = True    # 缺失时自动安装依赖

    def execute(self, **kwargs) -> ToolResult:
        """执行工具, 返回结构化结果 + 是否成功 + 耗时"""

@dataclass 
class ToolResult:
    tool_name: str
    success: bool
    data: Any                    # 工具返回的实际数据
    error: Optional[str]
    latency_ms: float
    artifact_path: Optional[str] # 产生的文件路径 (如果产出文件)
```

---

## 四、注册方式 — 3 行代码

```python
# core/agent/tools/arxiv_tool.py

class ArxivTool(ToolAdapter):
    name = "arxiv_search"
    description = "Search arxiv for academic papers by keyword, author, category. Returns title, abstract, PDF URL."
    category = "search"
    dependencies = ["arxiv"]  # auto pip install if missing
    input_schema = {
        "query": "string",
        "max_results": "int (default 5)",
        "category": "string (optional, e.g. cs.AI)"
    }
    
    def execute(self, query="", max_results=5, **kwargs):
        import arxiv
        results = arxiv.Search(query=query, max_results=max_results)
        papers = [{"title": r.title, "abstract": r.summary[:300], "url": r.pdf_url}
                  for r in results.results()]
        return ToolResult(tool_name=self.name, success=True, data=papers, latency_ms=...)

# 注册 — 放在 __init__.py 里即可:
ToolRegistry.register(ArxivTool)
```

LLM 看到的就是每个工具的 `description` + `input_schema`，自己决定匹配哪个。

---

## 五、ToolRegistry — 核心

```python
class ToolRegistry:
    _tools: Dict[str, ToolAdapter] = {}
    
    @classmethod
    def register(cls, tool: ToolAdapter):
        """注册工具 (3 行即可)"""
    
    @classmethod  
    def discover(cls, query: str) -> List[ToolAdapter]:
        """LLM 询问: "有没有搜论文的工具？"
        返回匹配的工具列表 (按描述语义匹配)
        """
    
    @classmethod
    def resolve(cls, name: str) -> ToolAdapter:
        """获取工具实例。如果依赖缺失 → pip install → 重试"""
    
    @classmethod
    def execute(cls, name: str, **kwargs) -> ToolResult:
        """执行工具, 返回 ToolResult"""
```

### 动态安装流程

```
resolve("pdf_extract")
  → 查找 ToolRegistry._tools → 找到 PDFExtractTool
  → 检查依赖 ["pymupdf"] → 已安装 ✓
  → 返回 ToolAdapter 实例

resolve("ocr_extract")  
  → 查找 ToolRegistry._tools → 找到 OCRTool
  → 检查依赖 ["paddleocr", "paddlepaddle"] → 缺失!
  → subprocess: pip install paddleocr paddlepaddle (with user prompt?)
  → 安装成功 → 动态 import → 返回 ToolAdapter 实例
  → 安装失败 → 返回 AutoInstallError
```

---

## 六、LLM 工具调用协议

系统提示词中加入所有已注册工具的 `description` + `input_schema`:

```
可用工具:
  arxiv_search: 搜索 arxiv 论文。参数: query(str), max_results(int)
  pdf_extract:  从 PDF 提取文本。参数: url(str), pages(list)
  web_fetch:    抓取网页内容。参数: url(str), format(str: "markdown"|"text")
  code_exec:    执行 Python 代码。参数: code(str), timeout(int)
  file_write:   写入文件。参数: path(str), content(str)

当你需要调用工具时，输出:
<tool_call name="arxiv_search">
  {"query": "RLHF alignment 2024", "max_results": 5}
</tool_call>
```

LLM 回复解析:
```python
def parse_tool_calls(text: str) -> List[ToolCall]:
    """提取 <tool_call> 标签, 执行后把结果注入 LLM 上下文"""
    pattern = r'<tool_call name="([^"]+)">\s*(.*?)\s*</tool_call>'
    ...
```

---

## 七、task_graph 映射 — 记录真实执行

```
LLM 规划: task_graph = [
  {"id":"1", "name":"搜索 RLHF 论文",  "tool":"arxiv_search"},
  {"id":"2", "name":"下载并解析 PDF",  "tool":"pdf_extract",  "deps":["1"]},
  {"id":"3", "name":"提取 OCR 文本",   "tool":"ocr_extract",  "deps":["2"]},
  {"id":"4", "name":"生成综述报告",    "tool":"code_exec",    "deps":["3"]},
]

执行后:
  1 ✅ arxiv_search → 返回 5 篇论文 (1.2s)
  2 ✅ pdf_extract  → 成功提取 3 篇 (4.5s)  
  3 ✅ ocr_extract  → 1 篇扫描件 OCR (8.3s)
  4 ✅ code_exec    → 生成报告 (0.3s)

前端展示: 4 个任务节点, 每个标注了执行的工具和耗时
不再是 pcr/intent/profile 这种无意义的管线名
```

---

## 八、与现有系统集成

```
SubsystemRegistry                  ToolRegistry
├── event_bus                      ├── arxiv_search
├── pcr_router                     ├── pdf_extract
├── discourse_tree                 ├── web_fetch
├── blueprint_engine               ├── code_exec
├── decider                        ├── ocr_extract
├── ... 所有引擎子系统             ├── file_write
│                                  ├── db_query
└── 引擎内部, 不可见                ├── ... 自动发现
                                   │
                                   └── LLM 可见, 可调用
```

两者不冲突——`SubsystemRegistry` 管理引擎内部模块，`ToolRegistry` 管理 LLM 可调用的外部工具。BlueprintEngine 拿到 LLM 的工具调用计划后，通过 Decider/EventBus 编排执行。

---

## 九、实现路径

| Phase | 内容 | 预估 |
|-------|------|:---:|
| T1 | ToolAdapter + ToolRegistry 核心 (注册/发现/执行) | 200行 |
| T2 | LLM 工具调用协议 (系统提示词 + `<tool_call>` 解析) | 150行 |
| T3 | arxiv_search + web_fetch + pdf_extract 首批工具 | 300行 |
| T4 | Level 2 动态安装 + 自动注册 | 100行 |
| T5 | **Level 3 Sandbox** (ast.parse + import 白名单 + 静态分析 + 沙箱执行) | 250行 |
| T6 | task_graph 记录工具执行轨迹 + 自写工具节点 | 200行 |
| T7 | TriggerRule 生成 + 持久化自写工具 | 150行 |
| T8 | BlueprintEngine 集成 (LLM 工具计划 → DAG 执行) | 200行 |

---

## 十、与竞品差异

| 能力 | OpenAI | LangChain | **我们** |
|------|--------|-----------|----------|
| 工具调用 | ✅ | ✅ | ✅ |
| 工具发现 (LLM 自检) | ❌ | ❌ | ✅ |
| 缺失工具自动安装 | ❌ | ❌ | ✅ |
| 执行轨迹 task_graph | ❌ | 回调 | ✅ |
| 注册成本 | 10行+ | 装饰器 | **3行** |
