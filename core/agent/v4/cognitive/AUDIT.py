# v4/cognitive module audit — class names + method availability + integration readiness

import sys, os, re, ast

base = 'core/agent/v4/cognitive'
modules = {}
for fname in sorted(os.listdir(base)):
    if not fname.endswith('.py') or fname.startswith('__'):
        continue
    path = f'{base}/{fname}'
    with open(path, encoding='utf-8') as f:
        text = f.read()
    classes = re.findall(r'^class (\w+)', text, re.MULTILINE)
    tree = ast.parse(text)
    funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and not n.name.startswith('_')]
    lines = text.count('\n')
    modules[fname] = {'classes': classes, 'funcs': funcs, 'lines': lines}

print("MODULE AUDIT")
print("=" * 80)
for name, info in modules.items():
    cls_str = ', '.join(info['classes'][:3]) or 'none'
    func_str = ', '.join(info['funcs'][:6]) or 'none'
    print(f"{name:30s} {info['lines']:>4}L  classes=[{cls_str}]")
    print(f"{'':30s}      methods=[{func_str}]")
    print()

# Now compare with bridge expectations
print("=" * 80)
print("BRIDGE MISMATCHES (class names)")
print("=" * 80)
bridge_map = {
    'ocean_profile':        'OceanProfile',
    'bfi_calibrator':       'BFICalibrator',
    'behavior_discovery':   'BehaviorDiscovery',
    'pattern_learner':      'PatternLearner',
    'correction_journal':   'CorrectionJournal',
    'fusion':               'CognitiveFusion',
    'belief_map':           'BeliefMap',
    'tag_layer':            'TagLayer',
    'memory_extractor':     'MemoryExtractor',
    'mind':                 'Mind',
    'metacognition':        'Metacognition',
    'internal_monitor':     'InternalMonitor',
    'dynamics':             'InertiaDynamics',
}

mismatches = 0
for mod_name, expected in bridge_map.items():
    fname = f'{mod_name}.py'
    if fname in modules:
        actual = modules[fname]['classes']
        if expected in actual:
            print(f"  ✅ {mod_name} → {expected}")
        else:
            correct = actual[0] if actual else '???'
            print(f"  ❌ {mod_name} → expect={expected}, correct={correct}")
            mismatches += 1

print(f"\nMismatches: {mismatches}/13")
print(f"Modules that actually loaded: {13 - mismatches}/13")
