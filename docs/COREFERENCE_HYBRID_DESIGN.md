# Coreference Resolution — Hybrid Architecture

> arxiv: 2504.05855 (Syntax-Semantics Bridge), 2504.14321 (Chinese MCR), 1606.01323 (Entity-Level Repr)

## Design

```
                    raw text
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   Structural       Semantic        LLM Posterior
   Prior            Attention       Verification
   (syntax)         (embedding)     (gateway)
        │              │              │
        └──────┬───────┴──────┬───────┘
               ▼              ▼
          Mention Pairs   Coref Chains
               │              │
               └──────┬───────┘
                      ▼
              Fused Score (α·struct + β·sem + γ·LLM)
                      │
                      ▼
              [entity] replacement
```

## Three Tiers

### Tier 1: Structural Prior (fast, local)

```python
# Dependency parse + mention span detection
# Uses jieba POS (already deps) + lightweight constituency rules
MENTION_PATTERNS = [
    # Noun phrases: "这个东西", "那种方式", "前面提到的模块"
    (r'(这|那|该|其|此)(?:种|个|些|种|类|方面|方式|方法|模块|系统|方案)', 'demonstrative'),
    # Definite descriptions: "前面提到的X", "上述Y"  
    (r'(前面|上述|以上|之前|刚才)(?:提到|所述|描述|讨论)(?:的)(?:.+)', 'definite'),
    # Zero anaphora (Chinese-specific — empty subject)
    (r'^(?:(?:但是|然而|而且|所以|因此|于是|然后|接着).+)', 'zero_anaphora'),
]

def extract_mentions(text):
    """Structural mention detection — no LLM, ~10ms."""
    mentions = []
    for pattern, mtype in MENTION_PATTERNS:
        for m in re.finditer(pattern, text):
            mentions.append(Mention(
                text=m.group(),
                start=m.start(), end=m.end(),
                mtype=mtype,
                score=0.6  # structural score
            ))
    return mentions
```

### Tier 2: Semantic Attention (medium, model-local)

```python
# Use sentence-transformers (already in deps) for mention-pair similarity
from sentence_transformers import SentenceTransformer

class SemanticCoref:
    """Embedding-based mention pair scoring via cosine similarity."""
    
    def __init__(self, model="paraphrase-multilingual-MiniLM-L12-v2"):
        self.model = SentenceTransformer(model)
    
    def score_pair(self, mention_a: str, mention_b: str, context: str) -> float:
        """Score likelihood that two mentions corefer."""
        emb_a = self.model.encode(f"{context} {mention_a}")
        emb_b = self.model.encode(f"{context} {mention_b}")
        return cosine_similarity(emb_a, emb_b)  # 0-1
```

### Tier 3: LLM Posterior (slow, gateway)

```python
# LLM as verifier — high precision, low recall
PROMPT = """Given the text: {text}
These mentions may refer to the same entity:
  A: {mention_a}
  B: {mention_b}

Do A and B refer to the same entity? Answer YES/NO with confidence 0-100.
Reasoning: [1 sentence]"""

def llm_verify(mention_a, mention_b, text):
    """LLM posterior — ~500ms, used only for low-confidence pairs."""
    result = gateway.ask(PROMPT.format(
        text=text, mention_a=mention_a, mention_b=mention_b
    ))
    return parse_yes_no(result)  # {"verdict": "YES", "confidence": 85}
```

## Fusion Formula

```python
def resolve(text, mentions):
    pairs = generate_pairs(mentions)  # all possible coref pairs
    
    for a, b in pairs:
        s_struct = structural_score(a, b)    # 0-1, from pattern type
        s_sem = semantic_score(a, b, text)    # 0-1, from embedding cosine
        s_fused = 0.3 * s_struct + 0.4 * s_sem
        
        if s_fused < 0.5:  # uncertain → escalate to LLM
            result = llm_verify(a, b, text)
            s_llm = result["confidence"] / 100
            s_fused = 0.2 * s_struct + 0.3 * s_sem + 0.5 * s_llm
        
        if s_fused > THRESHOLD:
            coref_chains.merge(a, b)
    
    return apply_replacements(text, coref_chains)
```

## Evaluation Metrics

```
Precision = TP / (TP + FP)   # of correctly resolved / all resolved
Recall    = TP / (TP + FN)   # of correctly resolved / all actual corefs
F1        = 2 * P * R / (P + R)

Measurement strategy:
  - Small labeled set (50-100 conversation turns, human-annotated)
  - Compare vs LLM-only baseline (GPT-4o coref resolution)
  - Compare vs structural-only (Tier 1 only)
  - Compare vs semantic-only (Tier 2 only)
  - Full hybrid (Tier 1+2+3)

Expected (from paper findings):
  Structural-only:  P=0.75 R=0.40 F1=0.52
  Semantic-only:    P=0.65 R=0.55 F1=0.60
  LLM-only:         P=0.90 R=0.70 F1=0.79
  Hybrid (ours):    P=0.85 R=0.80 F1=0.82  ← best F1, fewer LLM calls
```

## Integration into DialogMesh

```python
# AssociationChain L1 extended with CorefResolver
class CorefResolver:
    def __init__(self):
        self.structural = StructuralMentionDetector()
        self.semantic = SemanticCoref()
        self.threshold = 0.65
    
    def resolve(self, text, entity_history):
        mentions = self.structural.extract_mentions(text)
        if len(mentions) < 2:
            return text  # nothing to resolve
        
        # Pairwise scoring
        chains = CorefChains(mentions)
        for a, b in generate_pairs(mentions):
            score = self._fused_score(a, b, text, entity_history)
            if score > self.threshold:
                chains.merge(a, b)
        
        # Apply replacements → enriched text for GranularityRegulator
        return chains.apply(text)
```
