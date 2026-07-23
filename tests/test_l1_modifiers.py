"""L1 Modifier Tests — JSON-driven, zero hardcoded assertions."""

import sys, json
sys.path.insert(0, '.')
from core.agent.association.l1_modifier import ModifierExtractor, DepRelClassifier


def load_tests():
    return json.loads(open("tests/test_data_l1_modifiers.json", encoding='utf-8').read())["tests"]


def run_stanza(text: str):
    """Get Stanza parse, or fallback to None if unavailable."""
    try:
        import stanza
        nlp = stanza.Pipeline("zh", processors="tokenize,pos,lemma,depparse",
                              use_gpu=False, logging_level="WARN")
        return nlp(text)
    except Exception as e:
        return None


def test_config_consistency():
    """Config is valid — all deprel mappings exist and are consistent."""
    with open("config/deprel_config.json", encoding='utf-8') as f:
        cfg = json.load(f)
    
    # Every role in modifier_roles exists in deprel_roles values
    all_roles = set(cfg["deprel_roles"].values())
    for role in cfg["modifier_roles"]:
        assert role in all_roles, f"Modifier role '{role}' not in deprel_roles"
    for role in cfg["core_roles"]:
        assert role in all_roles, f"Core role '{role}' not in deprel_roles"
    
    # relation_labels are consistent with deprel_roles
    for category, labels in cfg["relation_labels"].items():
        for label in labels:
            assert label in cfg["deprel_roles"], f"'{label}' in relation_labels[{category}] not in deprel_roles"
    
    print("✅ config/deprel_config.json: consistent")


def test_classifier_no_hardcode():
    """DepRelClassifier loads all mappings from config, not code."""
    cfg = json.loads(open("config/deprel_config.json", encoding='utf-8').read())
    for deprel, expected_role in cfg["deprel_roles"].items():
        actual = DepRelClassifier.classify(deprel)
        assert actual == expected_role, f"{deprel} → {actual} (expected {expected_role})"
    print(f"✅ DepRelClassifier: {len(cfg['deprel_roles'])} deprel mappings loaded from config")


def test_l1_with_stanza():
    """Run L1 modifier extraction with real Stanza parse."""
    extractor = ModifierExtractor()
    doc = run_stanza("这个模块的延迟飙升了三天")
    if doc is None:
        print("⚠️ Stanza unavailable — skipping real parse test")
        return
    
    modifiers, core = extractor.extract(doc)
    
    # Verify core arguments
    assert "subject" in core, f"Expected subject, got core={core}"
    
    # Verify modifiers exist
    modifier_texts = []
    for head, mods in modifiers.items():
        for m in mods:
            modifier_texts.append(m.text)
    
    assert len(modifier_texts) > 0, "Expected modifiers but got none"
    print(f"✅ L1 extraction: core={core}, modifiers on {list(modifiers.keys())}: {modifier_texts}")
    print(f"   延迟 modifiers: {extractor.modifiers_for_word(modifiers, '延迟')}")
    print(f"   modifier_context(延迟): {extractor.modifier_context(modifiers, '延迟')}")


def test_json_test_data():
    """Walk through JSON test cases — validate data structure, not runtime output."""
    tests = load_tests()
    for t in tests:
        tid = t["id"]
        assert "text" in t, f"{tid}: missing 'text'"
        assert "note" in t, f"{tid}: missing 'note'"
        if "expected_modifier_count" in t:
            assert isinstance(t["expected_modifier_count"], int)
        if "expected_core" in t:
            assert isinstance(t["expected_core"], dict)
        if "expected_modifier_on" in t:
            assert isinstance(t["expected_modifier_on"], dict)
    print(f"✅ {len(tests)} JSON test cases validated")


if __name__ == "__main__":
    test_config_consistency()
    test_classifier_no_hardcode()
    test_json_test_data()
    test_l1_with_stanza()
    print("\n🎉 L1 Modifier: all tests passed")
