"""Multi-Intent Split — data contracts.

Agent-native design: LLM is the coordinator, chains are LLM-driven verifiers.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class SubIntent:
    """One split sub-intent from multi-intent decomposition."""
    id: str
    text: str
    category: str = ""                    # 诊断/修复/探索/吐槽/信息查询
    entities: List[str] = field(default_factory=list)
    confidence: float = 0.5
    chain_votes: Dict[str, float] = field(default_factory=dict)  # {profile:0.8, association:0.6,...}
    ambiguity_score: float = 0.0
    needs_clarification: bool = False
    clarification_question: str = ""
    dependencies: List[str] = field(default_factory=list)         # 依赖的其他 sub_intent.id


@dataclass
class ChainVote:
    """One chain's verification result."""
    chain: str                            # profile/association/discourse/literal/engineering
    confidence: float                     # 0-1
    decision: str = "pass"                # accept/reject/pass(undecided)
    reason: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChainVotes:
    """Aggregated votes from all chains."""
    votes: Dict[str, ChainVote] = field(default_factory=dict)
    
    @property
    def active_count(self) -> int: return len(self.votes)
    
    @property
    def accept_count(self) -> int:
        return sum(1 for v in self.votes.values() if v.decision == "accept")
    
    @property
    def reject_count(self) -> int:
        return sum(1 for v in self.votes.values() if v.decision == "reject")
    
    @property
    def mean_confidence(self) -> float:
        if not self.votes: return 0.0
        return sum(v.confidence for v in self.votes.values()) / len(self.votes)
    
    @property
    def consensus_level(self) -> float:
        """0=total disagreement, 1=unanimous. Uses accept/reject counts."""
        n = self.active_count
        if n == 0: return 0.0
        majority = max(self.accept_count, self.reject_count)
        return majority / n


@dataclass
class AmbiguityDecision:
    """Ambiguity gate output."""
    trigger: str = ""
    score: float = 0.0
    action: str = "pass"                  # pass/auto_resolve/llm_resolve/ask_user
    fallback: str = ""


@dataclass
class MultiIntentResult:
    """Complete multi-intent split result."""
    sub_intents: List[SubIntent] = field(default_factory=list)
    is_multi: bool = False
    split_confidence: float = 0.0
    fusion_method: str = ""               # vote_consensus/weighted_mix/llm_adjudicate
    ambiguities: List[AmbiguityDecision] = field(default_factory=list)
    trace: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FilterResult:
    """Algorithm pre-filter result from LLMDrivenChain._algorithm_filter()."""
    outcome: str                          # accept/reject/pass/skip
    reason: str = ""
    hints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerifyContext:
    """Context passed to each chain during verification."""
    profile: Any = None                   # OCEANProfile
    association: Any = None               # L1+L1.5+L2 substrate
    discourse: Any = None                 # DiscourseBlockTree context
    literal: Any = None                   # Stanza dependency parse
    engineering: Any = None               # EngineeringContext (nullable)
    pcr: Any = None                       # PCR zone/routing info
    history: List[str] = field(default_factory=list)


@dataclass  
class EngineeringContext:
    """Engineering chain context — interface, implementation pending."""
    tools_available: List[str] = field(default_factory=list)
    env_state: Dict[str, str] = field(default_factory=dict)
    resource_constraints: Dict[str, bool] = field(default_factory=dict)
