# -*- coding: utf-8 -*-
"""核查全局 encoder 模型与维度（2026-08-12）。"""
import os
import sys

sys.path.insert(0, ".")


def main():
    from core.agent.compiler.semantic_encoder import get_encoder, SemanticEncoder
    enc = get_encoder()
    out = []
    out.append("use_bge_m3: %s" % enc.use_bge_m3)
    out.append("model_id: %s" % getattr(enc, "MODEL_ID", "?"))
    out.append("dim: %s" % enc.embedding_dim)
    out.append("max_length: %s" % getattr(enc, "max_length", "?"))
    out.append("M3 路径存在: %s" % os.path.exists(SemanticEncoder.BGE_M3_PATH))
    v = enc.encode(["执行层怎么分层"], batch_size=1)
    out.append("query 编码 shape: %s" % str(v.shape))
    with open("_enc_dim.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")


if __name__ == "__main__":
    main()
