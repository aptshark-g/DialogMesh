# tests/test_50_rounds.py
"""50 轮对话模拟测试：观察 DiscourseBlock Tree 构建效果。"""

import sys
import os
import importlib.util
import time

root = os.getcwd()
# 确保项目根目录在 sys.path 中，支持模块内部绝对导入
sys.path.insert(0, root)

def load_module_from_path(module_name, rel_path):
    abs_path = os.path.join(root, rel_path)
    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# 加载核心模块
_ = load_module_from_path("discourse_models", "core/agent/discourse_block_tree/models.py")
_ = load_module_from_path("segmenter", "core/agent/discourse_block_tree/segmenter.py")
_ = load_module_from_path("manager", "core/agent/discourse_block_tree/manager.py")
_ = load_module_from_path("summary_engine", "core/agent/discourse_block_tree/summary_engine.py")
_ = load_module_from_path("context_builder", "core/agent/discourse_block_tree/context_builder.py")
_ = load_module_from_path("indexer", "core/agent/discourse_block_tree/indexer.py")

hi = load_module_from_path("header_injector", "core/agent/compiler/header_injector.py")
sd = load_module_from_path("syntactic_decomposer", "core/agent/compiler/syntactic_decomposer.py")
mm = load_module_from_path("macro_micro_quantizer", "core/agent/compiler/macro_micro_quantizer.py")

discourse_int = load_module_from_path(
    "discourse_integration", "core/agent/discourse_integration.py"
)

EDU = sys.modules["discourse_models"].EDU
DiscourseBlock = sys.modules["discourse_models"].DiscourseBlock
BlockState = sys.modules["discourse_models"].BlockState
DiscoursePipeline = discourse_int.DiscoursePipeline


# ═══════════════════════════════════════════════════════════════════
# 50 轮对话语料（设计多话题切换、回跳、指代、多子句等场景）
# ═══════════════════════════════════════════════════════════════════

DIALOGUE_50 = [
    # Round 0-4: Python 编程话题（持续）
    "帮我写一个 Python 脚本",
    "我想用 Python 做数据分析",
    "Python 的 pandas 库怎么导入",
    "这个库很强大，帮我scan一下内存",
    "数据分析需要用到 numpy 和 matplotlib",

    # Round 5-9: 饮料话题（切换）
    "我喜欢喝汽水",
    "这个很甜，那个很呛",
    "汽水含有很多糖分",
    "碳酸饮料对健康不太好",
    "我想喝矿泉水",

    # Round 10-14: Java 编程话题（切换）
    "Java 和 Python 有什么区别",
    "Java 的语法更严格",
    "帮我写一个 Java 类",
    "这个类需要继承父类",
    "Java 的内存管理是自动的",

    # Round 15-19: 回到 Python（话题回跳）
    "Python 也有类继承",
    "帮我scan Python 的内存地址",
    "Python 的 dict 和 Java 的 HashMap 类似",
    "我想用 Python 做机器学习",
    "TensorFlow 和 PyTorch 哪个好",

    # Round 20-24: 多子句复杂轮次
    "我喜欢 Python。但是 Java 也很强大。帮我分析一下。",
    "数据分析需要 pandas，机器学习需要 PyTorch，帮我做推荐。",
    "这个框架很强大，那个框架很灵活，我该怎么选？",
    "我不喜欢 Java 的语法，因为它太冗长了。",
    "Python 简单，Java 复杂，C++ 更难。",

    # Round 25-29: 疑问与命令混合
    "Python 是什么？",
    "帮我查一下 Python 的文档。",
    "为什么 Python 这么流行？",
    "给我推荐一个 Python 教程。",
    "Python 的 GIL 是什么？",

    # Round 30-34: 生活话题（再次切换）
    "我想吃辣椒",
    "这个很辣，那个很苦",
    "辣椒和咖啡一起喝怎么样",
    "我不喜欢苦味",
    "帮我推荐一种饮料",

    # Round 35-39: 回到技术话题（编程语言对比）
    "C++ 和 Python 哪个性能好",
    "C++ 的指针很难理解",
    "帮我scan C++ 的内存地址",
    "Python 的 list 和 C++ 的 vector 区别",
    "我想学 C++ 编程",

    # Round 40-44: 深度学习话题
    "神经网络怎么训练",
    "CNN 和 LSTM 有什么区别",
    "帮我写一个 CNN 模型",
    "这个模型需要很多数据",
    "PyTorch 的 DataLoader 怎么用",

    # Round 45-49: 混合与总结
    "Python、Java、C++ 三选一",
    "数据分析用 Python，后端用 Java",
    "机器学习需要 Python 和数学",
    "帮我总结一下这些编程语言",
    "我想深入学习 Python 和机器学习",
]


def run_50_rounds_test():
    """运行 50 轮对话测试。"""
    print("=" * 70)
    print("  DiscourseBlock Tree 50 轮对话测试")
    print("=" * 70)
    
    # 预加载模型（避免首次加载计入延迟）— 必须在 DiscoursePipeline 之前
    from core.agent.compiler.semantic_encoder import get_encoder
    enc = get_encoder()
    enc.encode("预加载")  # 强制触发模型初始化（延迟加载仅在首次 encode 时触发）
    
    # 预加载 NER 模型（避免首次加载计入延迟）
    from core.agent.compiler.semantic_parser import SemanticParser
    _ = SemanticParser(use_ner=True, use_bge_filter=False)
    
    pipe = DiscoursePipeline(session_id="test_50_rounds")
    
    total_time = 0.0
    results = []
    
    for turn_idx, query in enumerate(DIALOGUE_50):
        t0 = time.time()
        
        # 构建历史（模拟真实会话）
        history = []
        for i, r in enumerate(results):
            history.append({"role": "user", "content": r["query"]})
            history.append({"role": "assistant", "content": f"[Response for turn {i}]"})
        
        ctx = pipe.process_turn(query, history, turn_idx)
        elapsed_ms = (time.time() - t0) * 1000
        total_time += elapsed_ms
        
        # 记录统计
        mgr = pipe.manager
        blocks = mgr.get_blocks()
        hot = len(mgr.get_hot_blocks())
        warm = len(mgr.get_warm_blocks())
        cold = len(mgr.get_cold_blocks())
        
        results.append({
            "turn": turn_idx,
            "query": query,
            "latency_ms": elapsed_ms,
            "block_count": mgr.block_count,
            "hot": hot,
            "warm": warm,
            "cold": cold,
            "context_preview": ctx[:120] + "..." if len(ctx) > 120 else ctx,
        })
        
        print(f"\n[Turn {turn_idx:02d}] {query[:50]}")
        print(f"  Latency: {elapsed_ms:.2f}ms | Blocks: {mgr.block_count} (H:{hot} W:{warm} C:{cold})")
        if ctx:
            print(f"  Context: {ctx[:100]}...")
    
    # 最终统计
    print("\n" + "=" * 70)
    print("  最终统计")
    print("=" * 70)
    
    avg_latency = total_time / len(DIALOGUE_50)
    print(f"\n  总轮次: {len(DIALOGUE_50)}")
    print(f"  总耗时: {total_time:.2f}ms")
    print(f"  平均延迟: {avg_latency:.2f}ms")
    print(f"  最终 Block 数: {mgr.block_count}")
    print(f"  Hot/Warm/Cold: {len(mgr.get_hot_blocks())}/{len(mgr.get_warm_blocks())}/{len(mgr.get_cold_blocks())}")
    
    # 每个 Block 的详细信息
    print("\n  --- Block 详情 ---")
    for block in mgr.get_blocks():
        print(f"\n  [{block.id}] State={block.state.value} Turns={block.start_turn}-{block.end_turn} EDUs={block.edu_count}")
        if block.summary:
            print(f"    v1: {block.summary.v1}")
            print(f"    v2: {block.summary.v2}")
            if block.summary.v3:
                print(f"    v3: {block.summary.v3}")
        print(f"    Entities: {block.entity_signature}")
    
    # 索引统计
    print("\n  --- 索引统计 ---")
    indexer = pipe.segmenter  # 注意：实际索引器在 pipeline 中未直接暴露，这里用 manager 的 blocks 统计
    all_entities = set()
    for block in mgr.get_blocks():
        for edu in block.edus:
            all_entities.update(edu.raw_entities)
    print(f"  提取实体总数: {len(all_entities)}")
    print(f"  实体列表: {sorted(all_entities)[:20]}...")
    
    # 性能评估
    print("\n  --- 性能评估 ---")
    if avg_latency < 5:
        print(f"  [OK] 平均延迟 {avg_latency:.2f}ms < 5ms (优秀)")
    elif avg_latency < 10:
        print(f"  [OK] 平均延迟 {avg_latency:.2f}ms < 10ms (良好)")
    else:
        print(f"  [WARN] 平均延迟 {avg_latency:.2f}ms > 10ms (需优化)")
    
    return results


if __name__ == "__main__":
    run_50_rounds_test()
