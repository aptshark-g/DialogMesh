"""冷启动种子管理"""
import time
from .models import ColdStartSeed


class ColdStartManager:
    MAX_SEEDS = 15
    DEPRECATION_INTERVAL = 50
    SAMPLE_THRESHOLD = 10

    def __init__(self):
        self.seeds: list[ColdStartSeed] = []
        self.turn_count = 0
        self.load_default_seeds()

    def load_default_seeds(self):
        self.seeds = [
            ColdStartSeed("执行", "查看结果", "TOOL_EXEC", "LOG_CHECK", 0.7),
            ColdStartSeed("查看日志", "分析错误", "LOG_CHECK", "ENTITY_ANALYZE", 0.8),
            ColdStartSeed("分析错误", "修改代码", "ENTITY_ANALYZE", "CODE_RUN", 0.7),
            ColdStartSeed("修改代码", "运行测试", "CODE_RUN", "CODE_RUN", 0.8),
            ColdStartSeed("运行测试", "查看结果", "CODE_RUN", "LOG_CHECK", 0.9),
            ColdStartSeed("搜索文档", "查看结果", "EXPLORATION", "LOG_CHECK", 0.6),
            ColdStartSeed("配置环境", "运行程序", "CONFIG_MODIFY", "TOOL_EXEC", 0.7),
            ColdStartSeed("查看结果", "修改代码", "LOG_CHECK", "CODE_RUN", 0.6),
            ColdStartSeed("查看结果", "分析错误", "LOG_CHECK", "ENTITY_ANALYZE", 0.5),
            ColdStartSeed("监控指标", "查看日志", "LOG_CHECK", "LOG_CHECK", 0.6),
        ][:self.MAX_SEEDS]
        for s in self.seeds:
            s.created_at = time.time()

    def get_weight(self, from_summary: str, to_summary: str):
        for seed in self.seeds:
            if seed.is_usable() and seed.from_summary == from_summary and seed.to_summary == to_summary:
                return seed.initial_weight
        return None

    def on_turn_completed(self):
        self.turn_count += 1
        if self.turn_count % self.DEPRECATION_INTERVAL == 0:
            self._check_deprecation()

    def _check_deprecation(self):
        for seed in self.seeds:
            if not seed.is_deprecated and seed.sample_count >= self.SAMPLE_THRESHOLD:
                seed.is_deprecated = True

    def mark_seed_used(self, from_summary: str, to_summary: str):
        for seed in self.seeds:
            if seed.from_summary == from_summary and seed.to_summary == to_summary:
                seed.sample_count += 1

    def get_active_seeds(self) -> list[ColdStartSeed]:
        return [s for s in self.seeds if s.is_usable()]

    @property
    def deprecated_count(self) -> int:
        return sum(1 for s in self.seeds if s.is_deprecated)
