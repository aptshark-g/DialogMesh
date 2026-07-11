#!/usr/bin/env python3
'''DialogMesh v3.2 API Server - single-user production entry point.

Usage:
  python scripts/api_v32.py                          # mock mode
  python scripts/api_v32.py --provider deepseek       # DeepSeek
  python scripts/api_v32.py --port 8080 --save-dir data  # custom
'''
import sys, os, json, asyncio, time, logging, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('v32_api')

from core.agent.v3_2 import V32Pipeline, DeepSeekProvider, MockLLM, DEFAULT_COMPILER_RESPONSE
from core.agent.v3_2.persistence import PersistenceManager

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse, StreamingResponse
    import uvicorn
except ImportError:
    logger.error('FastAPI/uvicorn not installed. Install: pip install fastapi uvicorn')
    sys.exit(1)

app = FastAPI(title='DialogMesh v3.2', version='3.2.0')
pipe = None

# --- Middleware ---
@app.middleware('http')
async def log_requests(request, call_next):
    t0 = time.time()
    response = await call_next(request)
    ms = (time.time() - t0) * 1000
    logger.info(f'{request.method} {request.url.path} -> {response.status_code} ({ms:.0f}ms)')
    return response

# --- Endpoints ---

@app.on_event('startup')
async def startup():
    global pipe
    provider = app.state.provider
    save_dir = app.state.save_dir
    logger.info(f'Starting v3.2 pipeline (provider={type(provider).__name__}, save_dir={save_dir})')
    pipe = V32Pipeline(provider, save_dir=save_dir)
    if save_dir:
        pm = PersistenceManager(pipe, save_dir=save_dir)
        restored = await pm.restore()
        pm.start_auto_save()
        app.state.pm = pm
        if restored:
            logger.info('Session profile restored')

@app.on_event('shutdown')
async def shutdown():
    global pipe
    logger.info('Shutting down...')
    if pipe and hasattr(pipe, 'close'):
        await pipe.close()
    if hasattr(app.state, 'pm') and app.state.pm:
        app.state.pm.close()
    logger.info('Shutdown complete')

@app.get('/v3/health')
async def health():
    stats = {}
    if pipe:
        stats['turn'] = pipe.turn
        stats['graph_nodes'] = len(pipe.graph.nodes) if pipe.graph else 0
    if hasattr(app.state, 'pm') and app.state.pm:
        stats['persistence'] = app.state.pm.get_stats()
    return {'status': 'ok', 'version': '3.2.0', **stats}

@app.post('/v3/process')
async def process(body: dict):
    global pipe
    if not pipe:
        raise HTTPException(503, 'Pipeline not ready')
    query = body.get('query', '')
    wait = body.get('wait', True)
    if not query.strip():
        raise HTTPException(400, 'Empty query')
    try:
        result = await pipe.process(query)
        f = result['fusion']
        p = result['parse']
        return {
            'turn': result['turn'],
            'stability': p.stability,
            'slots': p.to_dict().get('slots', {}) if hasattr(p, 'to_dict') else {},
            'fusion_confidence': f.confidence,
            'dominant_track': str(getattr(f.dominant_track, 'value', f.dominant_track)),
            'clarify': f.ask_clarification,
            'block_tree_summary': result.get('block_tree', {}).get('summary', {}),
            'kb_blocked': result.get('kb_blocked', False),
        }
    except Exception as e:
        logger.error(f'Process error: {e}')
        raise HTTPException(500, str(e))

@app.get('/v3/status')
async def status():
    global pipe
    if not pipe:
        return {'status': 'initializing'}
    s = pipe.get_status()
    if hasattr(app.state, 'pm') and app.state.pm:
        s['persistence'] = app.state.pm.get_stats()
    return s

@app.get('/v3/sessions')
async def list_sessions():
    if hasattr(app.state, 'pm') and app.state.pm:
        sessions = list(app.state.pm.session_dir.glob('*.jsonl'))
        return {'sessions': [{'file': s.name, 'size': s.stat().st_size} for s in sessions]}
    return {'sessions': []}

@app.get('/v3/stream')
async def stream(query: str = ''):
    from fastapi.responses import StreamingResponse
    async def event_stream():
        global pipe
        if not pipe:
            yield 'data: {"error":"Pipeline not ready"}\n\n'
            return
        import json
        yield f'data: {json.dumps({"event":"start","query":query})}\n\n'
        try:
            result = await pipe.process(query)
            p = result.get('parse'); f = result.get('fusion')
            data = {'turn': result['turn'], 'stability': getattr(p, 'stability', 0), 'fusion_confidence': getattr(f, 'confidence', 0) if f else 0}
            yield f'data: {json.dumps({"event":"result",**data})}\n\n'
        except Exception as e:
            yield f'data: {json.dumps({"event":"error","message":str(e)})}\n\n'
        yield 'data: {"event":"done"}\n\n'
    return StreamingResponse(event_stream(), media_type='text/event-stream')

@app.post('/v3/assess')
async def assess(body: dict):
    from core.agent.v3_2.metacognition import MetaCognitionAdapter
    if not app.state.provider:
        return {'confidence': 0.5}
    mc = MetaCognitionAdapter(app.state.provider)
    result = await mc.assess(body.get('query',''), body.get('response',''))
    return {'confidence': result.confidence, 'uncertainties': result.uncertainties, 'clarification': result.clarification_question, 'latency_ms': result.latency_ms}

def main():
    ap = argparse.ArgumentParser(description='DialogMesh v3.2 API Server')
    ap.add_argument('--provider', default='mock', choices=['mock', 'deepseek'])
    ap.add_argument('--save-dir', default='', help='Persistence save directory')
    ap.add_argument('--port', type=int, default=9100, help='Server port')
    ap.add_argument('--host', default='127.0.0.1')
    args = ap.parse_args()

    if args.provider == 'deepseek':
        api_key = os.environ.get('DEEPSEEK_API_KEY', '')
        if not api_key:
            logger.error('DEEPSEEK_API_KEY not set')
            sys.exit(1)
        provider = DeepSeekProvider(api_key=api_key)
        logger.info('Using DeepSeek provider')
    else:
        provider = MockLLM(DEFAULT_COMPILER_RESPONSE)
        logger.info('Using Mock provider')

    save_dir = args.save_dir or os.environ.get('V32_SAVE_DIR', '')
    if not save_dir:
        save_dir = f'v32_data_{int(time.time())}'

    app.state.provider = provider
    app.state.save_dir = save_dir

    logger.info(f'Starting server on {args.host}:{args.port}, save_dir={save_dir}')
    uvicorn.run(app, host=args.host, port=args.port, log_level='info')

if __name__ == '__main__':
    main()
