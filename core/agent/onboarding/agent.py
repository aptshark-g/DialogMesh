# core/agent/onboarding/agent.py
"""Onboarding Agent — 引导系统核心。

职责：
1. 使用 DiscoursePipeline 管理自身对话上下文（dogfooding）
2. 通过 LLM API（OpenAI 兼容格式）生成智能回复
3. 支持工具调用：health_check、preload_models、download_model、get_config、update_config、show_example
4. 如果 LLM 不可用，使用规则回退回复

配置来源：
- 首选：~/.config/memorygraph/llm.yaml
- 次选：环境变量（LMSTUDIO_HOST、OPENAI_API_KEY 等）
- 默认：本地 LMStudio http://localhost:1234/v1
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 路径设置 ─────────────────────────────────────────────────────

project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ── 延迟导入（避免启动时依赖未安装）──────────────────────────────

try:
    from core.agent.v3_common.discourse_integration import DiscoursePipeline
except ImportError as e:
    DiscoursePipeline = None  # type: ignore
    logger.debug(f"DiscoursePipeline not available: {e}")

try:
    from core.agent.v3_common.health_check import HealthChecker, HealthStatus
except ImportError as e:
    HealthChecker = None  # type: ignore
    HealthStatus = None  # type: ignore
    logger.debug(f"HealthChecker not available: {e}")

try:
    from core.agent.config.discourse_config import (
        get_discourse_config,
        reload_discourse_config,
        ConfigLoader,
    )
except ImportError as e:
    get_discourse_config = None  # type: ignore
    reload_discourse_config = None  # type: ignore
    ConfigLoader = None  # type: ignore
    logger.debug(f"Discourse config not available: {e}")

try:
    from core.agent.onboarding.prompts import format_system_prompt, get_rule_fallback
except ImportError:
    from prompts import format_system_prompt, get_rule_fallback  # type: ignore


# ── LLM 配置加载 ─────────────────────────────────────────────────

LLM_CONFIG_PATH = Path.home() / ".config" / "memorygraph" / "llm.yaml"
DEFAULT_LLM_CONFIG = {
    "provider": "openai_compatible",
    "base_url": "http://localhost:1234/v1",
    "api_key": "lmstudio",
    "model": "qwen2.5-1.5b",
    "timeout_s": 30,
    "max_tokens": 512,
    "temperature": 0.7,
}


def _load_llm_config() -> Dict[str, Any]:
    """加载 LLM 配置（YAML → 环境变量 → 默认）。"""
    config = dict(DEFAULT_LLM_CONFIG)

    # 1. 尝试 YAML
    if LLM_CONFIG_PATH.exists():
        try:
            import yaml
            with open(LLM_CONFIG_PATH, "r", encoding="utf-8") as f:
                yaml_cfg = yaml.safe_load(f)
            if yaml_cfg and isinstance(yaml_cfg, dict):
                config.update(yaml_cfg)
                logger.info(f"Loaded LLM config from {LLM_CONFIG_PATH}")
        except ImportError:
            logger.debug("PyYAML not installed, skipping YAML config")
        except Exception as e:
            logger.warning(f"Failed to load LLM YAML config: {e}")

    # 2. 环境变量覆盖
    env_mappings = {
        "MEMORYGRAPH_LLM_BASE_URL": "base_url",
        "MEMORYGRAPH_LLM_API_KEY": "api_key",
        "MEMORYGRAPH_LLM_MODEL": "model",
        "OPENAI_API_KEY": "api_key",
        "LMSTUDIO_HOST": "base_url",  # e.g. http://localhost:1234
    }
    for env_key, cfg_key in env_mappings.items():
        val = os.environ.get(env_key)
        if val:
            if cfg_key == "base_url" and not val.endswith("/v1"):
                val = val.rstrip("/") + "/v1"
            config[cfg_key] = val

    return config


# ── LLM 客户端 ─────────────────────────────────────────────────

class _LLMClient:
    """简易 OpenAI 兼容 LLM 客户端。"""

    def __init__(self, config: Dict[str, Any]):
        self.base_url = config.get("base_url", "http://localhost:1234/v1")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "qwen2.5-1.5b")
        self.timeout_s = config.get("timeout_s", 30)
        self.max_tokens = config.get("max_tokens", 512)
        self.temperature = config.get("temperature", 0.7)
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import openai
                self._client = openai.OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=self.timeout_s,
                )
            except ImportError:
                raise RuntimeError("openai library not installed. Run: pip install openai")
        return self._client

    def chat(self, messages: List[Dict[str, str]]) -> Tuple[str, bool]:
        """发送 chat completion 请求。

        Returns:
            (text, success)
        """
        try:
            client = self._get_client()
            resp = client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                timeout=self.timeout_s,
            )
            text = resp.choices[0].message.content or ""
            return text, True
        except Exception as e:
            logger.warning(f"LLM chat failed: {e}")
            return f"[LLM 不可用: {e}]", False

    def health_check(self) -> bool:
        """快速探测 LLM 可用性。"""
        try:
            client = self._get_client()
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
                temperature=0,
                timeout=5,
            )
            return bool(resp.choices[0].message.content)
        except Exception:
            return False


# ── OnboardingAgent ──────────────────────────────────────────────

class OnboardingAgent:
    """引导 Agent：帮助用户了解 Discourse Block Tree 系统。

    使用 DiscoursePipeline 管理自身对话上下文（dogfooding），
    通过 LLM API 生成回复，支持工具调用。
    """

    def __init__(
        self,
        session_id: str = "onboarding",
        use_llm: bool = True,
        llm_config: Optional[Dict[str, Any]] = None,
    ):
        self.session_id = session_id
        self.use_llm = use_llm
        self.llm_config = llm_config or _load_llm_config()
        self.llm = _LLMClient(self.llm_config) if use_llm else None
        self._llm_available: Optional[bool] = None

        # 使用 DiscoursePipeline 管理自身对话（dogfooding）
        self.pipeline = None
        if DiscoursePipeline is not None:
            try:
                self.pipeline = DiscoursePipeline(session_id=session_id, hot_turns=5)
            except Exception as e:
                logger.warning(f"Failed to initialize DiscoursePipeline: {e}")

        # 会话历史（用于 LLM 上下文）
        self._history: List[Dict[str, str]] = []
        self._turn_index = 0

        logger.info(f"OnboardingAgent initialized (session={session_id}, use_llm={use_llm})")

    # ── 公共接口 ──────────────────────────────────────────────────

    def greet(self) -> str:
        """返回欢迎语和系统介绍。"""
        return self._generate_reply("你好，请介绍一下系统", force_topic="default")

    def respond(self, user_input: str) -> str:
        """处理用户输入，返回回复。"""
        return self._generate_reply(user_input)

    def check_health(self) -> Dict[str, Any]:
        """运行系统健康检查并返回结构化结果。"""
        if HealthChecker is None:
            return {"error": "HealthChecker not available"}
        try:
            checker = HealthChecker()
            status = checker.check_all()
            return status.to_dict()
        except Exception as e:
            return {"error": str(e)}

    def preload_models(self) -> Dict[str, Any]:
        """预加载模型，返回进度信息。"""
        if self.pipeline is None:
            return {"success": False, "error": "DiscoursePipeline not available"}
        try:
            self.pipeline.preload(blocking=True)
            return {"success": True, "message": "模型预加载完成"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def download_model(self, model_name: str) -> Dict[str, Any]:
        """下载指定模型。

        Args:
            model_name: "bge" | "ner" | "all"
        """
        script = Path(project_root) / "scripts" / "download_models.py"
        if not script.exists():
            return {"success": False, "error": f"Script not found: {script}"}

        cmd = [sys.executable, str(script)]
        if model_name == "bge":
            cmd.append("--bge-only")
        elif model_name == "ner":
            cmd.append("--ner-only")
        elif model_name != "all":
            return {"success": False, "error": f"Unknown model: {model_name}"}

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(project_root),
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_config(self) -> Dict[str, Any]:
        """获取当前配置。"""
        if get_discourse_config is None:
            return {"error": "Config system not available"}
        try:
            cfg = get_discourse_config()
            return {
                "encoder": {
                    "model_path": cfg.encoder.model_path,
                    "device": cfg.encoder.device,
                    "max_length": cfg.encoder.max_length,
                },
                "segmenter": {
                    "threshold": cfg.segmenter.threshold,
                    "macro_weight": cfg.segmenter.macro_weight,
                    "micro_weight": cfg.segmenter.micro_weight,
                },
                "manager": {
                    "hot_turns": cfg.manager.hot_turns,
                    "cooling_turns": cfg.manager.cooling_turns,
                    "cold_turns": cfg.manager.cold_turns,
                    "merge_threshold": cfg.manager.merge_threshold,
                },
                "summary": {
                    "v3_trigger_turn_count": cfg.summary.v3_trigger_turn_count,
                },
                "pipeline": {
                    "enabled": cfg.pipeline.enabled,
                    "hot_turns": cfg.pipeline.hot_turns,
                },
                "model_download": {
                    "bge_model_id": cfg.model_download.bge_model_id,
                    "ner_model_id": cfg.model_download.ner_model_id,
                    "cache_dir": cfg.model_download.cache_dir,
                },
            }
        except Exception as e:
            return {"error": str(e)}

    def update_config(self, key: str, value: Any) -> Dict[str, Any]:
        """更新配置并热重载。

        Args:
            key: 点分隔路径，如 "segmenter.threshold" 或 "manager.hot_turns"
            value: 新值
        """
        if ConfigLoader is None:
            return {"success": False, "error": "Config system not available"}
        try:
            config_file = ConfigLoader.CONFIG_DIR / "discourse.yaml"
            config_file.parent.mkdir(parents=True, exist_ok=True)

            # 读取现有配置
            current = {}
            if config_file.exists():
                try:
                    import yaml
                    with open(config_file, "r", encoding="utf-8") as f:
                        current = yaml.safe_load(f) or {}
                except ImportError:
                    pass

            # 更新嵌套值
            parts = key.split(".")
            d = current
            for p in parts[:-1]:
                if p not in d:
                    d[p] = {}
                d = d[p]
            d[parts[-1]] = value

            # 写回
            try:
                import yaml
                with open(config_file, "w", encoding="utf-8") as f:
                    yaml.dump(current, f, allow_unicode=True, sort_keys=False)
            except ImportError:
                return {"success": False, "error": "PyYAML not installed"}

            # 热重载
            if reload_discourse_config is not None:
                reload_discourse_config()

            return {"success": True, "message": f"已更新 {key} = {value}，配置已热重载"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def show_example(self, scenario: str = "basic") -> str:
        """返回使用示例代码。"""
        examples = {
            "basic": """```python
from core.agent.v3_common.discourse_integration import DiscoursePipeline

# 初始化管道
pipeline = DiscoursePipeline(session_id="demo", hot_turns=5)

# 预加载模型
pipeline.preload(blocking=True)

# 处理单轮输入
context = pipeline.process_turn(
    raw_query="你好，请介绍一下系统",
    session_history=[],
    turn_index=0,
)
print(context)
```
""",
            "multi_turn": """```python
from core.agent.v3_common.discourse_integration import DiscoursePipeline

pipeline = DiscoursePipeline(session_id="chat", hot_turns=5)
pipeline.preload(blocking=True)

history = []
for i, query in enumerate(["问题1", "问题2", "问题3"]):
    ctx = pipeline.process_turn(query, history, i)
    history.append({"role": "user", "content": query})
    # 将 ctx 附加到 LLM messages
    print(f"Turn {i}: {ctx[:200]}...")
```
""",
            "config": """```python
from core.agent.config.discourse_config import get_discourse_config, reload_discourse_config

# 获取当前配置
cfg = get_discourse_config()
print(f"threshold={cfg.segmenter.threshold}, hot_turns={cfg.manager.hot_turns}")

# 修改后调用 reload 热重载
reload_discourse_config()
```
""",
            "health": """```python
from core.agent.v3_common.health_check import HealthChecker

checker = HealthChecker()
status = checker.check_all()
print(f"Healthy: {status.is_healthy}")
for c in status.checks:
    print(f"  {c.name}: {c.status} — {c.message}")
```
""",
        }
        return examples.get(scenario, examples["basic"])

    def get_system_state(self) -> Dict[str, Any]:
        """获取当前系统状态（用于嵌入提示词）。"""
        health = self.check_health()
        config = self.get_config()
        return {
            "health": health,
            "config": config,
            "session_id": self.session_id,
            "pipeline_initialized": self.pipeline is not None,
            "llm_available": self._is_llm_available(),
        }

    def _is_llm_available(self) -> bool:
        """检查 LLM 是否可用（缓存结果）。"""
        if self.llm is None:
            return False
        if self._llm_available is not None:
            return self._llm_available
        self._llm_available = self.llm.health_check()
        return self._llm_available

    # ── 核心生成逻辑 ──────────────────────────────────────────────

    def _generate_reply(self, user_input: str, force_topic: Optional[str] = None) -> str:
        """生成回复（LLM 优先，规则回退）。"""
        # 1. 尝试使用 DiscoursePipeline 处理上下文（dogfooding）
        discourse_ctx = ""
        if self.pipeline is not None:
            try:
                discourse_ctx = self.pipeline.process_turn(
                    raw_query=user_input,
                    session_history=list(self._history),
                    turn_index=self._turn_index,
                )
            except Exception as e:
                logger.debug(f"DiscoursePipeline processing failed: {e}")
                discourse_ctx = ""

        # 2. 尝试 LLM
        if self.use_llm and self.llm is not None and self._is_llm_available():
            try:
                reply = self._llm_chat(user_input, discourse_ctx)
                self._record_turn(user_input, reply)
                return reply
            except Exception as e:
                logger.warning(f"LLM generation failed: {e}")

        # 3. 规则回退
        topic = force_topic or self._detect_topic(user_input)
        kwargs: Dict[str, Any] = {}
        if topic == "health":
            kwargs["health_status"] = json.dumps(self.check_health(), ensure_ascii=False, indent=2)
        reply = get_rule_fallback(topic, **kwargs)
        self._record_turn(user_input, reply)
        return reply

    def _llm_chat(self, user_input: str, discourse_ctx: str) -> str:
        """使用 LLM 生成回复。"""
        system_state = self.get_system_state()
        system_prompt = format_system_prompt(system_state)

        # 如果 discourse_ctx 非空，附加到 system prompt
        if discourse_ctx:
            system_prompt += f"\n\n## 当前对话上下文（DiscoursePipeline 输出）\n\n{discourse_ctx}"

        messages = [
            {"role": "system", "content": system_prompt},
        ]
        # 附加历史（最多 10 轮）
        for h in self._history[-10:]:
            messages.append(h)
        messages.append({"role": "user", "content": user_input})

        text, success = self.llm.chat(messages)
        if not success:
            raise RuntimeError(text)
        return text

    def _detect_topic(self, user_input: str) -> str:
        """基于关键词检测用户意图（用于规则回退）。"""
        u = user_input.lower()
        keywords = {
            "health": ["健康", "状态", "检查", "check", "health", "status"],
            "download": ["下载", "模型", "download", "model", "缺失", "missing"],
            "config": ["配置", "参数", "设置", "config", "threshold", "hot_turns", "参数"],
            "example": ["示例", "例子", "代码", "example", "sample", "code"],
            "architecture": ["架构", "原理", "设计", "architecture", "原理", "编译器", "stage"],
        }
        for topic, words in keywords.items():
            if any(w in u for w in words):
                return topic
        return "default"

    def _record_turn(self, user_input: str, assistant_reply: str):
        """记录对话轮次。"""
        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": assistant_reply})
        self._turn_index += 1

    def reset(self):
        """重置对话状态。"""
        self._history.clear()
        self._turn_index = 0
        if self.pipeline is not None:
            try:
                self.pipeline.reset()
            except Exception:
                pass


# ── CLI 测试入口 ─────────────────────────────────────────────────

def main():
    """命令行测试引导 Agent。"""
    import argparse

    parser = argparse.ArgumentParser(description="Onboarding Agent CLI")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM, use rule fallback")
    parser.add_argument("--model", type=str, help="Override model name")
    parser.add_argument("--base-url", type=str, help="Override base URL")
    args = parser.parse_args()

    llm_config = _load_llm_config()
    if args.model:
        llm_config["model"] = args.model
    if args.base_url:
        llm_config["base_url"] = args.base_url

    agent = OnboardingAgent(
        session_id="cli",
        use_llm=not args.no_llm,
        llm_config=llm_config,
    )

    print("=" * 50)
    print("Onboarding Agent CLI")
    print(f"LLM: {llm_config['base_url']} / {llm_config['model']}")
    print(f"LLM available: {agent._is_llm_available()}")
    print("=" * 50)
    print(agent.greet())
    print()

    while True:
        try:
            user_input = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye", "再见"):
            print("再见！")
            break
        reply = agent.respond(user_input)
        print(f"Momo > {reply}")
        print()


if __name__ == "__main__":
    main()
