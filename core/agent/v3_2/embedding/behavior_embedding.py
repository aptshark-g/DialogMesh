# DialogMesh v3.2 Behavior Semantic Embedding Layer
import numpy as np

class PredicateMapper:
    """Map verbs to predicate classes (<50 rules)"""

    def __init__(self):
        self.map = {}
        self._build()

    def _build(self):
        data = [
            ("debug", "debug"), ("diagnose", "debug"), ("trace", "debug"),
            ("compile", "build"), ("build", "build"), ("assemble", "build"),
            ("deploy", "deploy"), ("release", "deploy"), ("install", "deploy"),
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
            self.map[k] = v
        # Chinese mappings
        for k, v in [
            ("\u8c03\u8bd5","debug"),("\u8bca\u65ad","debug"),
            ("\u7f16\u8bd1","build"),("\u6784\u5efa","build"),
            ("\u90e8\u7f72","deploy"),("\u53d1\u5e03","deploy"),
            ("\u91cd\u542f","restart"),
            ("\u8fd0\u884c","execute"),("\u6267\u884c","execute"),("\u542f\u52a8","execute"),
            ("\u914d\u7f6e","config"),("\u8bbe\u7f6e","config"),
            ("\u626b\u63cf","scan"),
            ("\u6d4b\u8bd5","test"),("\u9a8c\u8bc1","test"),
            ("\u68c0\u67e5","check"),
            ("\u76d1\u63a7","monitor"),
            ("\u542f\u7528","enable"),("\u6fc0\u6d3b","enable"),
            ("\u7981\u7528","disable"),
            ("\u5907\u4efd","backup"),
            ("\u6062\u590d","restore"),("\u8fd8\u539f","restore"),
            ("\u66f4\u65b0","update"),("\u5347\u7ea7","upgrade"),
            ("\u67e5\u770b","show"),("\u663e\u793a","show"),
            ("\u5217\u51fa","list"),
            ("\u5206\u6790","analyze"),
            ("\u6bd4\u8f83","compare"),
            ("\u9884\u6d4b","predict"),
            ("\u521b\u5efa","create"),("\u5efa\u7acb","create"),
            ("\u4fee\u6539","modify"),("\u7f16\u8f91","modify"),
            ("\u5220\u9664","delete"),("\u79fb\u9664","delete"),
            ("\u8bf4\u660e","explain"),
            ("\u4fee\u590d","fix"),
            ("\u505c\u6b62","stop"),
        ]:
            self.map[k] = v
        self._classes = sorted(set(self.map.values()))

    def map_verb(self, verb):
        if not verb or not verb.strip(): return None
        v = verb.strip().lower()
        return self.map.get(v)

    @property
    def classes(self): return self._classes

    @property
    def class_count(self): return len(self._classes)

weights = {
    "execute": (0.7, 0.3), "debug": (0.3, 0.7),
    "build": (0.7, 0.3), "deploy": (0.7, 0.3),
    "restart": (0.7, 0.3), "config": (0.5, 0.5),
    "scan": (0.7, 0.3), "test": (0.7, 0.3),
    "check": (0.4, 0.6), "monitor": (0.4, 0.6),
    "enable": (0.5, 0.5), "disable": (0.5, 0.5),
    "schedule": (0.7, 0.3), "backup": (0.7, 0.3),
    "restore": (0.7, 0.3), "update": (0.5, 0.5),
    "show": (0.3, 0.7), "list": (0.3, 0.7),
    "analyze": (0.3, 0.7), "compare": (0.3, 0.7),
    "predict": (0.3, 0.7), "document": (0.3, 0.7),
    "query": (0.3, 0.7), "create": (0.7, 0.3),
    "modify": (0.7, 0.3), "delete": (0.7, 0.3),
    "explain": (0.2, 0.8), "fix": (0.7, 0.3),
    "connect": (0.5, 0.5), "stop": (0.7, 0.3),
    "clean": (0.7, 0.3), "greet": (0.2, 0.8),
    "affirm": (0.2, 0.8), "answer": (0.2, 0.8),
    "trace": (0.3, 0.7), "search": (0.3, 0.7),
    "find": (0.3, 0.7), "locate": (0.3, 0.7),
    "install": (0.7, 0.3),
}

print("PredicateMapper classes:", __import__("json").dumps(PredicateMapper().classes, ensure_ascii=False))
print("Total predicate classes:", PredicateMapper().class_count)
print("Module loaded OK")
