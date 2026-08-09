# -*- coding: utf-8 -*-
"""SPO 抽象关系类型集 + 谓词映射表（双语两阶段设计, A12 约束空间投影）。

阶段2 映射层: 开放谓词 → 抽象关系类型。对齐从"字面谓词"升级为
"关系类型匹配"（语义归一）。白盒可查（A19）: 任何动词可查映射。

2026-08-08 软编码升级: 硬编码表 = 种子缓存; 未命中收集 + LLM 判定兜底。
"""

# 关系类型集（A12 约束空间投影, 15+ 类）
RELATION_TYPES = {
    "is_a":       "归属",      # 是/属于/源于
    "part_of":    "组成",      # 包含/具有/由...组成
    "cause":      "因果",      # 导致/决定/引发/锚定
    "transform":  "转化",      # 变成/转为/升为
    "depend":     "依赖",      # 依赖/需要/基于
    "forbid":     "禁止",      # 禁止/不能/不可
    "allow":      "允许",      # 允许/可以/可
    "compare":    "比较",      # 优于/高于/区别于
    "oppose":     "对立",      # 对立/矛盾/相反
    "purpose":    "目的",      # 为了/用于/旨在
    "inherit":    "继承",      # 继承/沿用/承接
    "trigger":    "触发",      # 触发/激活/启动
    "regulate":   "调节",      # 调节/控制/抑制
    "produce":    "产生",      # 产生/生成/造成
    "measure":    "衡量",      # 衡量/决定程度/相关于
}

# 中文谓词 → 关系类型（规则映射表, 起步覆盖常见动词）
ZH_MAP = {
    "是": "is_a", "属于": "is_a", "源于": "is_a", "在于": "is_a",
    "就是": "is_a", "本质是": "is_a", "叫做": "is_a", "为": "is_a",
    "包含": "part_of", "具有": "part_of", "拥有": "part_of",
    "由": "part_of", "包括": "part_of", "含有": "part_of",
    "导致": "cause", "决定": "cause", "引发": "cause", "造成": "cause",
    "锚定": "cause", "影响": "cause", "使得": "cause", "让": "cause",
    "产生": "produce", "生成": "produce", "形成": "produce", "带来": "produce",
    "变成": "transform", "转为": "transform", "转化为": "transform",
    "升为": "transform", "转化为": "transform",
    "依赖": "depend", "需要": "depend", "基于": "depend", "依靠": "depend",
    "禁止": "forbid", "不能": "forbid", "不可": "forbid", "无法": "forbid",
    "不允许": "forbid",
    "允许": "allow", "可以": "allow", "可": "allow", "能够": "allow",
    "优于": "compare", "高于": "compare", "区别于": "compare",
    "不同": "compare", "对比": "compare", "相比": "compare",
    "对立": "oppose", "矛盾": "oppose", "相反": "oppose",
    "为了": "purpose", "用于": "purpose", "旨在": "purpose",
    "用来": "purpose", "以便": "purpose",
    "继承": "inherit", "沿用": "inherit", "承接": "inherit",
    "触发": "trigger", "激活": "trigger", "启动": "trigger", "引发": "trigger",
    "调节": "regulate", "控制": "regulate", "抑制": "regulate",
    "决定": "regulate", "主导": "regulate",
}

# 英文谓词 → 关系类型
EN_MAP = {
    "is": "is_a", "are": "is_a", "be": "is_a", "means": "is_a",
    "refers": "is_a", "defined": "is_a", "derives": "is_a",
    "contains": "part_of", "have": "part_of", "has": "part_of",
    "include": "part_of", "consist": "part_of", "comprise": "part_of",
    "causes": "cause", "lead": "cause", "determine": "cause",
    "drives": "cause", "anchors": "cause", "influences": "cause",
    "affects": "cause", "results": "cause",
    "produces": "produce", "generates": "produce", "creates": "produce",
    "become": "transform", "turn": "transform", "converts": "transform",
    "depends": "depend", "requires": "depend", "based": "depend",
    "relies": "depend", "needs": "depend",
    "forbids": "forbid", "cannot": "forbid", "must not": "forbid",
    "prohibits": "forbid",
    "allows": "allow", "can": "allow", "permits": "allow",
    "better": "compare", "differ": "compare", "unlike": "compare",
    "oppose": "oppose", "contradict": "oppose", "vs": "compare",
    "for": "purpose", "aims": "purpose", "used": "purpose",
    "inherits": "inherit", "triggers": "trigger", "activates": "trigger",
    "regulates": "regulate", "controls": "regulate", "suppresses": "regulate",
}

# 未命中谓词池（软编码: 离线补表原料）
UNKNOWN_POOL = set()
# 会话内 LLM 判定缓存
LLM_CACHE = {}
# LLM 判定器（由 RecallService 注入）
_llm = None


def set_llm(llm):
    """注入 LLM 判定器（网关 provider）。"""
    global _llm
    _llm = llm


def map_predicate(pred: str) -> str:
    """开放谓词 → 关系类型。归一化后查表, 无匹配返回原谓词（字面兜底）。"""
    if not pred:
        return pred
    p = pred.strip().lower()
    # 英文: 取第一个动词词元
    first = p.split()[0] if p else p
    if first in EN_MAP:
        return EN_MAP[first]
    if p in EN_MAP:
        return EN_MAP[p]
    # 中文: 取前 2-3 字匹配最长条目
    best = ""
    for k in ZH_MAP:
        if p.startswith(k) and len(k) > len(best):
            best = k
    if best:
        return ZH_MAP[best]
    # 软编码: LLM 判定缓存
    if p in LLM_CACHE:
        return LLM_CACHE[p]
    if _llm is not None:
        rel = _llm_judge(_llm, p)
        if rel:
            LLM_CACHE[p] = rel
            return rel
    UNKNOWN_POOL.add(p)
    return pred


def _llm_judge(llm, pred: str) -> str:
    """LLM 判定: 未覆盖谓词 → 关系类型。失败返回 "". """
    try:
        from core.agent.llm_providers.base import GenerateRequest
        types_desc = "、".join("%s(%s)" % (k, v) for k, v in RELATION_TYPES.items())
        prompt = (
            "把下面的中文/英文动词归入最合适的抽象关系类型, "
            "只输出类型 id, 不要其他文字。\n"
            "可选类型: %s\n动词: %s" % (types_desc, pred)
        )
        res = llm.generate(GenerateRequest(
            prompt=prompt, max_tokens=16, temperature=0.1,
            timeout_ms=20000))
        text = (res.text if res is not None else "").strip().lower()
        if text in RELATION_TYPES:
            return text
        # 容错: 输出含类型 id
        for k in RELATION_TYPES:
            if k in text:
                return k
        return ""
    except Exception:
        return ""


def unknown_pool() -> list:
    """未覆盖谓词池（白盒查看 + 离线补表原料）。"""
    return sorted(UNKNOWN_POOL)


def learn_map(pairs: dict) -> int:
    """离线补表: {谓词: 关系类型} 并入硬编码表。返回新增数。"""
    added = 0
    for pred, rel in (pairs or {}).items():
        p = (pred or "").strip()
        if not p or rel not in RELATION_TYPES:
            continue
        if p in ZH_MAP or p in EN_MAP or p in LLM_CACHE:
            continue
        ZH_MAP[p] = rel
        UNKNOWN_POOL.discard(p.lower())
        added += 1
    return added


def relation_label(rel: str) -> str:
    """关系类型 → 中文标签（白盒展示）。"""
    return RELATION_TYPES.get(rel, rel)
