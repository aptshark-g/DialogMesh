"""降级管理器 — 三态切换 + 纯规则降级"""
from .models import SlotValue, ParseContext


class DegradationManager:
    MODE_FULL = "full"
    MODE_RULE = "rule"
    MODE_NONE = "none"

    def __init__(self, max_retries: int = 1, threshold: int = 3):
        self.mode = self.MODE_FULL
        self.max_retries = max_retries
        self.fails = 0
        self.threshold = threshold

    def on_success(self):
        self.fails = 0
        if self.mode != self.MODE_FULL:
            self.mode = self.MODE_FULL

    def on_failure(self):
        self.fails += 1
        if self.fails >= self.threshold:
            self.mode = self.MODE_RULE

    def should_use_llm(self) -> bool:
        return self.mode == self.MODE_FULL

    def force_rule_mode(self):
        self.mode = self.MODE_RULE

    def get_status(self) -> dict:
        return {"mode": self.mode, "consecutive_failures": self.fails}

    @staticmethod
    def rule_parse(sentence: str, library) -> dict[str, SlotValue]:
        import jieba
        words = jieba.lcut(sentence)
        tagged = _simple_pos_tag(words)
        slots: dict[str, SlotValue] = {}
        for word, pos in tagged:
            if pos == "v":
                conf = 0.72
                if library:
                    rules = library.query("action", word)
                    if rules:
                        conf = 0.80
                slots["action"] = SlotValue(value=word, confidence=conf, source="rule")
            elif pos == "n":
                if "agent" not in slots:
                    sname, conf = "agent", 0.65
                else:
                    sname, conf = "patient", 0.60
                if library:
                    rules = library.query(sname, word)
                    if rules:
                        conf = max(conf, 0.78)
                slots[sname] = SlotValue(value=word, confidence=conf, source="rule")
        return slots


def _simple_pos_tag(words: list[str]) -> list[tuple[str, str]]:
    VERBS = {"运行", "修改", "删除", "查看", "执行", "分析", "调试",
             "喝", "吃", "写", "读", "启动", "停止", "创建"}
    NOUNS = {"程序", "日志", "配置", "文件", "数据", "系统", "代码",
             "饮料", "水", "食物", "脚本", "服务", "进程", "端口",
             "网络", "内存", "磁盘", "报表", "报告"}
    result = []
    for w in words:
        if w in VERBS:
            result.append((w, "v"))
        elif w in NOUNS:
            result.append((w, "n"))
        else:
            result.append((w, "x"))
    return result
