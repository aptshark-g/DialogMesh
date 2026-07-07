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
            ("deploy", "deploy"), ("release", "deploy"), ("install", "deploy"), ("write", "write"), ("compose", "write"), ("implement", "write"),
            ("set up", "config"), ("set", "config"), ("adjust", "modify"), ("increase", "modify"), ("reduce", "modify"), ("improve", "modify"),
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

# ?? BGE-small-zh Integration ??????????????????????????????????

BGE_MODEL_PATH = r"C:\Users\APTShark\PycharmProjects\DialogMesh\models\BAAI\bge-small-zh"
_bge_model = None

def get_bge_model():
    """Lazy-load BGE-small-zh model"""
    global _bge_model
    if _bge_model is None:
        from sentence_transformers import SentenceTransformer
        _bge_model = SentenceTransformer(BGE_MODEL_PATH, model_kwargs={"local_files_only": True})
    return _bge_model

# ?? Prototype Vector Store ??????????????????????????????????

class PrototypeVectorStore:
    """????????????????????????"""

    DIM = 512  # BGE-small-zh dimension

    def __init__(self):
        self.prototypes = {}  # pred_class -> numpy ndarray
        self._initialized = False
        self._fallback = np.zeros(self.DIM, dtype=np.float32)

    def initialize(self, mapper: PredicateMapper):
        """????????????"""
        model = get_bge_model()
        for pc in mapper.classes:
            standard_texts = self._get_standard_texts(pc)
            if standard_texts:
                embeddings = model.encode(standard_texts)
                self.prototypes[pc] = np.mean(embeddings, axis=0)
            else:
                self.prototypes[pc] = self._fallback.copy()
        self._initialized = True

    def _get_standard_texts(self, pred_class: str) -> list:
        """??????????"""
        texts = {
            "execute": ["execute program", "run script", "launch service", "执行程序", "运行脚本"],
            "debug":   ["debug process", "trace execution", "调试程序", "跟踪执行"],
            "build":   ["build project", "compile source", "编译项目", "构建源码"],
            "deploy":  ["deploy service", "release version", "部署服务", "发布版本"],
            "restart": ["restart service", "reboot system", "重启服务", "重新启动"],
            "config":  ["configure settings", "initialize parameters", "配置参数", "设置选项"],
            "scan":    ["scan network", "enumerate devices", "扫描网络", "探测设备"],
            "test":    ["test function", "validate output", "测试功能", "验证输出"],
            "check":   ["check status", "inspect logs", "检查状态", "查看日志"],
            "monitor": ["monitor performance", "track metrics", "监控性能", "跟踪指标"],
            "show":    ["show details", "display result", "查看详情", "显示结果"],
            "list":    ["list files", "catalog items", "列出文件", "展示列表"],
            "analyze": ["analyze data", "investigate issue", "分析数据", "调查问题"],
            "compare": ["compare versions", "benchmark performance", "比较版本", "基准测试"],
            "predict": ["predict outcome", "forecast trend", "预测结果", "预估趋势"],
            "create":  ["create project", "generate code", "创建项目", "生成代码"],
            "modify":  ["modify config", "edit settings", "修改配置", "编辑设置"],
            "delete":  ["delete file", "remove entry", "删除文件", "移除项目"],
            "fix":     ["fix bug", "repair error", "修复错误", "更正缺陷"],
            "disable": ["disable service", "deactivate module", "禁用服务", "停用模块"],
            "enable":  ["enable feature", "activate plugin", "启用功能", "激活插件"],
            "stop":    ["stop process", "halt service", "停止进程", "终止服务"],
            "clean":   ["clean cache", "purge temp", "清理缓存", "清除临时"],
            "backup":  ["backup data", "save state", "备份数据", "保存状态"],
            "restore": ["restore backup", "recover data", "恢复备份", "还原数据"],
            "update":  ["update version", "upgrade system", "更新版本", "升级系统"],
            "query":   ["query database", "search records", "查询数据", "搜索记录"],
            "explain": ["explain concept", "describe process", "解释概念", "描述过程"],
            "schedule": ["schedule task", "plan job", "安排任务", "计划作业"],
            "document": ["document changes", "record results", "记录变更", "文档结果"],
            "answer":  ["answer question", "respond query", "回答问题", "回复查询"],
            "affirm":  ["affirm action", "confirm choice", "确认操作", "肯定选择"],
            "greet":   ["greet user", "say hello", "打招呼", "问候"],
            "connect": ["connect server", "attach device", "连接服务器", "接入设备"],
        }
        return texts.get(pred_class, [])

    def get(self, pred_class):
        return self.prototypes.get(pred_class, self._fallback)

    def cosine_sim(self, vec_a, vec_b):
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a < 1e-10 or norm_b < 1e-10:
            return 0.0
        return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


PROTOTYPES = PrototypeVectorStore()

# ?? Semantic Query ??????????????????????????????????????????

class SemanticQuery:
    """????: (1) ???? (2) ???? (3) ????"""

    def __init__(self, cosine_threshold=0.6):
        self.cosine_threshold = cosine_threshold
        self._mapper = PredicateMapper()
        self._weights = weights
        self._bge = None

    def encode(self, text):
        """BGE encode with lazy load"""
        if self._bge is None:
            self._bge = get_bge_model()
        return self._bge.encode(text)

    def embed_action_pair(self, from_action, to_action):
        """????????"""
        v_from = self.encode(from_action)
        v_to = self.encode(to_action)
        combined = np.concatenate([v_from, v_to])
        return combined

    def predicate_vector(self, verb, arg):
        """??-????????"""
        pred_class = self._mapper.map_verb(verb)
        if pred_class is None:
            return self.encode(f"{verb} {arg}")
        w_pred, w_arg = self._weights.get(pred_class, (0.5, 0.5))
        prot = PROTOTYPES.get(pred_class)
        arg_vec = self.encode(arg)
        return w_pred * prot + w_arg * arg_vec

    def find_neighbors(self, query_vec, target_vectors, top_k=3):
        """? Top-K ????"""
        scores = [(PROTOTYPES.cosine_sim(query_vec, tv), i)
                  for i, tv in enumerate(target_vectors)]
        scores.sort(key=lambda x: -x[0])
        results = []
        for score, idx in scores:
            if score < self.cosine_threshold:
                break
            results.append((score, idx))
        return results[:top_k]


# ?? Entry ??????????????????????????????????????????????????


class HardBoundaryQuery:
    """Predicate class hard boundary + AdaptiveParameter integration"""

    SAME_CLASS = 1.0
    DIFF_CLASS_PENALTY = 0.30

    def __init__(self, base_query):
        self._base = base_query
        self._candidates = 0
        self._rejected = 0
        self._missed = 0

    def find_neighbors(self, from_verb, from_arg, to_verb, to_arg, top_k=3):
        """With predicate class hard boundary: different class = low similarity"""
        from_class = self._base._mapper.map_verb(from_verb)
        to_class = self._base._mapper.map_verb(to_verb)

        query_vec = self._base.predicate_vector(from_verb, from_arg)
        target_vec = self._base.predicate_vector(to_verb, to_arg)

        penalty = self.DIFF_CLASS_PENALTY
        if from_class and to_class and from_class == to_class:
            penalty = self.SAME_CLASS

        raw_sim = PROTOTYPES.cosine_sim(query_vec, target_vec)
        return raw_sim * penalty

    def batch_find(self, query_verb, query_arg, targets, top_k=3):
        """Batch find with threshold filtering"""
        results = []
        for tv, ta in targets:
            sim = self.find_neighbors(query_verb, query_arg, tv, ta)
            results.append((sim, (tv, ta)))
        results.sort(key=lambda x: -x[0])
        self._candidates = len(results)
        threshold = self._get_threshold()
        above = [(s, t) for s, t in results if s >= threshold]
        return above[:top_k], [t for s, t in results if s < threshold]

    def record_feedback(self, hit=True, correction=False):
        """Adaptive signal: correction = false positive, miss = too strict"""
        from core.agent.v3_2.adaptive_parameter import CALIBRATOR
        if correction:
            self._rejected += 1
            CALIBRATOR.update("sim_threshold", -0.005)
        elif not hit and self._candidates > 0:
            self._missed += 1
            CALIBRATOR.update("sim_threshold", 0.005)

    def _get_threshold(self):
        from core.agent.v3_2.adaptive_parameter import CALIBRATOR
        return CALIBRATOR.value("sim_threshold")

    @property
    def stats(self):
        return {"candidates": self._candidates, "rejected": self._rejected,
                "missed": self._missed, "threshold": self._get_threshold()}


EMBEDDER = SemanticQuery()
HARD_BOUNDARY = HardBoundaryQuery(EMBEDDER)

def init_embeddings(mapper=None):
    """Initialize prototypes and warm up BGE model"""
    m = mapper or PredicateMapper()
    PROTOTYPES.initialize(m)
    threshold = HARD_BOUNDARY._get_threshold()
    dim = PROTOTYPES.DIM
    print(f"[Embedding] Initialized: {m.class_count} classes, {dim}d, threshold={threshold:.3f} (adaptive)")

def get_embedding_stats():
    """Return current embedding system state"""
    thr = HARD_BOUNDARY._get_threshold()
    return {"classes": PredicateMapper().class_count,
            "dim": PROTOTYPES.DIM,
            "threshold": thr,
            "bge_loaded": _bge_model is not None,
            "same_class_boost": HardBoundaryQuery.SAME_CLASS,
            "diff_class_penalty": HardBoundaryQuery.DIFF_CLASS_PENALTY}
