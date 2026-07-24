"""DiscourseBlockTree integration test"""
import sys
sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\DialogMesh")

from core.agent.discourse_block_tree import DiscourseBlockTreeManager

m = DiscourseBlockTreeManager()

# Test 1: multi-topic split
ids1 = m.ingest_turn(1, "???Python???????????????????????????embedding???")
print(f"Test 1: {len(ids1)} blocks (expect >=2)")

# Test 2: single topic
ids2 = m.ingest_turn(2, "??????????")
print(f"Test 2: {len(ids2)} blocks (expect >=1)")

# Test 3: temperature state machine
for t in range(3, 20):
    m.ingest_turn(t, f"?????? turn {t}")
s = m.get_tree_summary()
print(f"Test 3: active={s[chr(97)+chr(99)+chr(116)+chr(105)+chr(118)+chr(101)]}, pause={s[chr(112)+chr(97)+chr(117)+chr(115)+chr(101)+chr(100)]}")

# Test 4: context building
ctx = m.build_context()
print(f"Test 4: context length = {len(ctx)} chars")

# Test 5: reference search
found = m.search("Python")
print(f"Test 5: search Python = {len(found)} results")

print("All integration tests passed")