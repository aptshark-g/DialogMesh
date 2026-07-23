"""Predicate classifier with MAX_RULES=50 enforcement."""
from typing import Optional


class PredicateClassifier:
    """Map verbs to predicate classes (extracted from legacy PredicateMapper).
    Enforces MAX_RULES = 50.
    """

    MAX_RULES = 50

    def __init__(self):
        self._map: dict = {}
        self._build()

    def _build(self):
        data = [
            ("debug", "debug"), ("diagnose", "debug"), ("trace", "debug"),
            ("compile", "build"), ("build", "build"), ("assemble", "build"),
            ("deploy", "deploy"), ("release", "deploy"), ("install", "deploy"),
            ("write", "write"), ("compose", "write"), ("implement", "write"),
            ("set up", "config"), ("set", "config"), ("adjust", "modify"),
            ("increase", "modify"), ("reduce", "modify"), ("improve", "modify"),
            ("restart", "restart"), ("reboot", "restart"), ("reload", "restart"),
            ("execute", "execute"), ("run", "execute"), ("launch", "execute"), ("start", "execute"),
            ("configure", "config"), ("initialize", "config"),
            ("scan", "scan"), ("enumerate", "scan"), ("probe", "scan"),
            ("test", "test"), ("validate", "test"), ("verify", "test"),
            ("check", "check"), ("inspect", "check"), ("examine", "check"),
            ("monitor", "monitor"), ("watch", "monitor"), ("track", "monitor"),
            ("enable", "enable"), ("activate", "enable"),
            ("disable", "disable"), ("deactivate", "disable"),
            ("schedule", "schedule"), ("plan", "schedule"),
            ("backup", "backup"), ("save", "backup"), ("archive", "backup"),
            ("restore", "restore"), ("recover", "restore"), ("revert", "restore"),
            ("update", "update"), ("upgrade", "update"), ("patch", "update"),
            ("show", "show"), ("display", "show"), ("print", "show"),
            ("list", "list"), ("catalog", "list"),
            ("analyze", "analyze"), ("investigate", "analyze"), ("study", "analyze"),
            ("compare", "compare"), ("contrast", "compare"),
            ("predict", "predict"), ("forecast", "predict"),
            ("document", "document"), ("record", "document"),
            ("query", "query"), ("search", "query"), ("find", "query"),
            ("create", "create"), ("generate", "create"), ("produce", "create"),
            ("modify", "modify"), ("change", "modify"), ("edit", "modify"),
            ("delete", "delete"), ("remove", "delete"), ("erase", "delete"),
            ("explain", "explain"), ("describe", "explain"), ("clarify", "explain"),
            ("fix", "fix"), ("repair", "fix"),
            ("connect", "connect"), ("attach", "connect"),
            ("stop", "stop"), ("halt", "stop"),
            ("clean", "clean"), ("purge", "clean"),
            ("affirm", "affirm"), ("agree", "affirm"), ("confirm", "affirm"),
            ("answer", "answer"), ("respond", "answer"), ("reply", "answer"),
            ("greet", "greet"),
        ]
        for k, v in data:
            self._map[k] = v
        # Chinese mappings
        for k, v in [
            ("调试", "debug"), ("诊断", "debug"),
            ("编译", "build"), ("构建", "build"),
            ("部署", "deploy"), ("发布", "deploy"),
            ("重启", "restart"),
            ("运行", "execute"), ("执行", "execute"), ("启动", "execute"),
            ("配置", "config"), ("设置", "config"),
            ("扫描", "scan"),
            ("测试", "test"), ("验证", "test"),
            ("检查", "check"),
            ("监控", "monitor"),
            ("启用", "enable"), ("激活", "enable"),
            ("禁用", "disable"),
            ("备份", "backup"),
            ("恢复", "restore"), ("还原", "restore"),
            ("更新", "update"), ("升级", "upgrade"),
            ("查看", "show"), ("显示", "show"),
            ("列出", "list"),
            ("分析", "analyze"),
            ("比较", "compare"),
            ("预测", "predict"),
            ("创建", "create"), ("建立", "create"),
            ("修改", "modify"), ("编辑", "modify"),
            ("删除", "delete"), ("移除", "delete"),
            ("说明", "explain"),
            ("修复", "fix"),
            ("停止", "stop"),
            ("清理", "clean"),
        ]:
            self._map[k] = v
        self._classes = sorted(set(self._map.values()))
        assert len(self._classes) <= self.MAX_RULES, f"Predicate classes {len(self._classes)} exceed MAX_RULES={self.MAX_RULES}"

    def classify(self, verb: str) -> Optional[str]:
        if not verb or not verb.strip():
            return None
        v = verb.strip().lower()
        return self._map.get(v)

    @property
    def classes(self):
        return self._classes

    @property
    def class_count(self):
        return len(self._classes)
