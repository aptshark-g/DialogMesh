"""JiebaRelationParser — fast Chinese relation extraction via jieba segmentation.

Zero model downloads. < 10ms per sentence. Extracts entity-verb-entity tuples
for definition and relation detection.
"""
import jieba, re
from typing import List, Dict

class JiebaRelationParser:
    RELATION_VERBS = {"依赖","依赖于","基于","调用","触发","生成","创建","产生","实现","继承","扩展","引用","约束","限制","控制"}
    DEFINITION_VERBS = {"是","指","负责","用于","定义为","指的是","作用是"}
    ALL = RELATION_VERBS | DEFINITION_VERBS
    _CAMEL = re.compile(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+')

    def extract(self, text: str) -> List[Dict]:
        words = list(jieba.cut(text))
        entities = [w for w in words if self._CAMEL.search(w)]
        if not entities:
            entities = [w for w in words if 2 <= len(w) <= 6 and all(c >= '\u4e00' and c <= '\u9fff' for c in w)]
        results = []
        for i, w in enumerate(words):
            if w not in self.ALL: continue
            subj = None
            for j in range(i-1, -1, -1):
                if words[j] in entities: subj = words[j]; break
            if not subj and i > 0: subj = words[i-1]
            obj = None
            for j in range(i+1, min(i+5, len(words))):
                if words[j] in entities: obj = words[j]; break
            if not obj and i+1 < len(words):
                rest = ''.join(words[i+1:i+4])
                if len(rest) >= 3: obj = rest[:40]
            if subj and obj:
                pm = {"依赖":"depends_on","依赖于":"depends_on","基于":"depends_on","调用":"calls","触发":"triggers","生成":"produces","创建":"produces","实现":"implements","继承":"extends","扩展":"extends","引用":"references","约束":"constrains","控制":"controls"}
                pred = pm.get(w,"references")
                etype = "definition" if w in self.DEFINITION_VERBS else "relation"
                results.append({"subject":subj,"predicate":pred,"object":obj,"type":etype,"confidence":0.7})
        return results
