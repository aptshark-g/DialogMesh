from dataclasses import asdict
from .models import L1SummaryEntry, L1MetaInfo, ContentCategory
from .content_classifier import ContentClassifier
from .meta_extractor import MetaInfoExtractor
from .summary_generator import SummaryGenerator


class L1Summary:
    L2_TRIGGER = 5

    def __init__(self, classifier=None, extractor=None, generator=None):
        self.classifier = classifier or ContentClassifier()
        self.extractor = extractor or MetaInfoExtractor()
        self.generator = generator or SummaryGenerator()
        self.entries = []
        self.consecutive_det = 0
        self.topic_counts = {}

    async def process(self, turn, prev_type, prediction=None):
        cat = self.classifier.classify(turn, self.consecutive_det)
        if cat == ContentCategory.DETERMINISTIC:
            self.consecutive_det += 1
        else:
            self.consecutive_det = 0
        meta = self.extractor.extract(turn, prev_type, prediction)
        core = self.generator.generate(cat, turn, meta)
        entry = L1SummaryEntry(turn.get("turn_id", ""), cat.value, core, asdict(meta))
        self.entries.append(entry)
        tid = meta.topic_id
        self.topic_counts[tid] = self.topic_counts.get(tid, 0) + 1
        if self.topic_counts[tid] >= self.L2_TRIGGER:
            self.topic_counts[tid] = 0
        return entry
