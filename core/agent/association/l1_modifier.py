"""L1 Modifier Extractor — config-driven dependency relation classification.

Design: docs/v5/ASSOCIATION_CHAIN_GAPS.md, L1
Config: config/deprel_config.json
Tests: tests/test_data_l1_modifiers.json
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import json, logging
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Modifier:
    text: str
    deprel: str
    role: str  # from config mapping
    head_word: str
    position: int


class DepRelClassifier:
    """Classifies dependency relations using config-driven mapping.
    Zero hardcoded deprel names — all from config/deprel_config.json.
    """
    
    _config: Optional[dict] = None
    _modifier_roles: set = set()
    _core_roles: set = set()
    _label_map: Dict[str, str] = {}  # deprel → role name
    
    @classmethod
    def _load_config(cls):
        if cls._config is not None:
            return
        config_path = Path(__file__).parent.parent.parent.parent / "config" / "deprel_config.json"
        cls._config = json.loads(open(config_path, encoding='utf-8').read())
        cls._label_map = cls._config["deprel_roles"]
        cls._modifier_roles = set(cls._config["modifier_roles"])
        cls._core_roles = set(cls._config["core_roles"])
    
    @classmethod
    def classify(cls, deprel: str) -> str:
        """Classify a dependency relation label into its role type."""
        cls._load_config()
        # Direct match
        if deprel in cls._label_map:
            role = cls._label_map[deprel]
        else:
            # Fuzzy: try prefix match (e.g., "nmod:unknown" → "nmod")
            base = deprel.split(":")[0] if ":" in deprel else deprel
            role = cls._label_map.get(base, "other")
        return role
    
    @classmethod
    def is_modifier(cls, role: str) -> bool:
        return role in cls._modifier_roles
    
    @classmethod
    def is_core(cls, role: str) -> bool:
        return role in cls._core_roles


class ModifierExtractor:
    """Extracts modifiers from Stanza dependency parse output.
    
    Usage:
        extractor = ModifierExtractor()
        doc = stanza_pipeline(text)
        modifiers, core = extractor.extract(doc)
    """
    
    def extract(self, stanza_doc) -> tuple:
        """Extract modifiers and core arguments from a stanza Document.
        
        Returns:
            modifiers: Dict[str, List[Modifier]]  # head_word → modifiers
            core: Dict[str, str]  # role → word_text
        """
        modifiers: Dict[str, List[Modifier]] = {}
        core: Dict[str, str] = {}
        
        for sent in stanza_doc.sentences:
            for word in sent.words:
                if word.deprel in ("punct", "root", "_"):
                    continue
                
                role = DepRelClassifier.classify(word.deprel)
                
                if DepRelClassifier.is_core(role):
                    key = role.replace("_", "_")
                    if key not in core:
                        core[key] = word.text
                    elif role == "subject":  # prefer first subject
                        pass
                    else:
                        core[key] = word.text
                
                elif DepRelClassifier.is_modifier(role):
                    # Skip short modifiers — noise filter, threshold from config
                    min_len = 2  # config/l2_config.json modifier_filter.min_length
                    if len(word.text) < min_len:
                        continue
                    head_text = sent.words[word.head - 1].text if word.head > 0 else "ROOT"
                    mod = Modifier(
                        text=word.text,
                        deprel=word.deprel,
                        role=role,
                        head_word=head_text,
                        position=word.id,
                    )
                    modifiers.setdefault(head_text, []).append(mod)
        
        return modifiers, core
    
    def modifiers_for_word(self, modifiers: dict, word: str) -> List[Modifier]:
        """Get all modifiers for a specific word."""
        return modifiers.get(word, [])
    
    def modifier_context(self, modifiers: dict, word: str) -> str:
        """Build a flattened context string from modifiers of a word.
        Used as query input for L1.5 candidate search."""
        mods = self.modifiers_for_word(modifiers, word)
        if not mods:
            return ""
        parts = []
        for m in mods:
            role_label = m.role.replace("_modifier", "").replace("_", " ")
            parts.append(f"[{role_label}]{m.text}")
        return " ".join(parts)
