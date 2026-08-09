#!/usr/bin/env python3
'''DialogMesh v3.2 CLI - full pipeline with DeepSeek or mock.
Usage:
  python scripts/cli_v32.py 'write a Python function'
  python scripts/cli_v32.py --mock 'test query'
  python scripts/cli_v32.py --interactive
'''
import sys, os, json, asyncio, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.agent.v3_2 import V32Pipeline, DeepSeekProvider, MockLLM, DEFAULT_COMPILER_RESPONSE

def main():
    ap = argparse.ArgumentParser(description='DialogMesh v3.2 CLI')
    ap.add_argument('query', nargs='?', help='Single query')
    ap.add_argument('--mock', action='store_true', help='Use mock LLM (default if no DEEPSEEK_API_KEY)')
    ap.add_argument('--json', action='store_true', help='JSON output')
    ap.add_argument('--graph', action='store_true', help='Show graph stats')
    ap.add_argument('--bridge', action='store_true', help='Show bridge/v3.0 Orchestrator status')
    ap.add_argument('--profile', action='store_true', help='Show cognitive profile')
    ap.add_argument('--blocks', action='store_true', help='Show block tree summary')
    ap.add_argument('--demo', action='store_true', help='Auto-run 3 queries to demonstrate pipeline')
    ap.add_argument('--interactive', '-i', action='store_true', help='Interactive mode')
    ap.add_argument('--save-dir', default='', help='Persistence save directory')
    args = ap.parse_args()

    # Auto-detect provider
    if args.mock or not os.environ.get('DEEPSEEK_API_KEY'):
        provider = MockLLM(DEFAULT_COMPILER_RESPONSE)
        mode = 'mock'
    else:
        provider = DeepSeekProvider()
        mode = 'deepseek'

    pipe = V32Pipeline(provider, save_dir=args.save_dir)

    async def process_once(q):
        try:
            r = await pipe.process(q)
            return r
        except Exception as e:
            return {'error': str(e)}

    def show(r):
        if args.json:
            p = r.get('parse')
            out = {'turn': r.get('turn'), 'stability': getattr(p, 'stability', 0),
                   'slots': getattr(p, 'to_dict', lambda: {})().get('slots', {}) if hasattr(p, 'to_dict') else {}}
            print(json.dumps(out, ensure_ascii=False))
            return
        p = r.get('parse'); f = r.get('fusion')
        kb = r.get('kb_blocked', False)
        tag = ' [BLOCKED]' if kb else ''
        print(f"\n[Turn {r.get('turn', '?')}] Stability: {getattr(p, 'stability', 0):.3f}{tag}")
        if hasattr(p, 'slots'):
            for name, slot in p.slots.items():
                print(f'  {name}: {slot.value} (conf={slot.confidence:.2f}, src={slot.source})')
        print(f'  Utterance: {getattr(p, "utterance_type", "?")} | Degraded: {getattr(p, "degraded", False)}')
        if f:
            dt = str(getattr(f.dominant_track, 'value', f.dominant_track))
            print(f'  Fusion: {f.confidence:.3f} (track: {dt}, clarify: {f.ask_clarification})')
        if args.bridge:
            bs = pipe.get_bridge_status()
            print(f'  Bridge: enabled={bs.get(chr(34)+"enabled"+chr(34))}, v30_healthy={bs.get(chr(34)+"v30_healthy"+chr(34))}')
        if args.profile and hasattr(pipe, '_profile_updater'):
            p2 = pipe._profile_updater.profile
            print(f'  Profile: meta={p2.metacognition:.2f}, conf={p2.confidence:.2f}, div={p2.divergence:.2f}')
        if args.blocks:
            bt = pipe.block_tree.get_tree_summary()
            print(f'  Block Tree: {bt.get(chr(34)+"total_blocks"+chr(34),0)} blocks')
        if args.graph and hasattr(pipe, 'graph'):
            st = pipe.graph.get_statistics()
            print(f'  Graph: {st.node_count} nodes, {st.edge_count} edges')

    if args.interactive or (not args.query):
        print(f'DialogMesh v3.2 CLI ({mode} mode). Type "exit" to quit, "/json" toggle JSON.')
        json_mode = args.json
        while True:
            try:
                q = input('> ').strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not q: continue
            if q.lower() in ('exit', 'quit'): break
            if q == '/json': json_mode = not json_mode; print(f'JSON mode: {json_mode}'); continue
            r = asyncio.run(process_once(q))
            if json_mode:
                print(json.dumps({k: str(v)[:200] for k, v in r.items()}, ensure_ascii=False))
            else:
                show(r)
    elif args.demo:
        demo_queries = ['write a python function', 'scan memory 0x004000', 'configure firewall']
        for i, q in enumerate(demo_queries):
            import time
            t0 = time.time()
            r = asyncio.run(process_once(q))
            print(f'  [{i+1}] \"{q}\" -> {time.time()-t0:.2f}s | stability={getattr(r.get(chr(34)+"parse"+chr(34)),"stability",0):.2f}')
    elif args.query:
        r = asyncio.run(process_once(args.query))
        show(r)

if __name__ == '__main__':
    main()
